"""Domestic exchange trading and US fund flows, observed on separate calendars."""
import json
import re
from datetime import date, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import requests

from .company_financials import acquire_lock
from .dart_statements import Tables
from .market_history import KST, completed_cutoff
from .market_refresh import write_json

INSTRUMENTS = {
    '069500': 'KODEX 200', '091160': 'KODEX 반도체',
    '114260': 'KODEX 국고채3년', '148070': 'KIWOOM 국고채10년',
    '005930': '삼성전자', '000660': 'SK하이닉스',
}
ICI = 'https://www.ici.org/research/stats/combined_flows'
NAVER = 'https://m.stock.naver.com/api/stock/{}/trend'
ACTORS = {'foreign': 'foreignerPureBuyQuant', 'institution': 'organPureBuyQuant'}
# Minimum net purchases as a percentage of traded volume on each leg.
THRESHOLD = 1.0


def integer(value):
    text = str(value).strip()
    if not re.fullmatch(r'[+-]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)', text):
        raise ValueError('수치 형식 확인 필요')
    return int(text.replace(',', ''))


def parse_trades(code, payload, cutoff):
    if not isinstance(payload, list) or not 1 <= len(payload) <= 40:
        raise ValueError('일별 행 수 확인 필요')
    result = {}
    previous = None
    for row in payload:
        if not isinstance(row, dict) or row.get('itemCode') != code:
            raise ValueError('종목코드 불일치')
        day = datetime.strptime(row['bizdate'], '%Y%m%d').date()
        if day.strftime('%Y%m%d') != row['bizdate'] or (previous and day >= previous):
            raise ValueError('거래일 중복 또는 순서 오류')
        previous = day
        if day > cutoff + timedelta(days=1):
            raise ValueError('미래 거래일')
        if day > cutoff:
            continue
        close, volume = integer(row['closePrice']), integer(row['accumulatedTradingVolume'])
        if close <= 0 or volume < 0:
            raise ValueError('종가 또는 거래량 오류')
        bar = dict(close=close, volume=volume)
        for actor, field in ACTORS.items():
            raw = row.get(field)
            quantity = None if raw in (None, '', '-', 'N/A') else integer(raw)
            if quantity is not None and abs(quantity) > volume:
                raise ValueError('순매매 수량과 거래량 불일치')
            bar[actor] = quantity
        result[day.isoformat()] = bar
    if not result:
        raise ValueError('완료 관측 대기')
    return result


def window(series, days, actor):
    bars = [series.get(day) for day in days]
    if not bars or any(not bar or bar[actor] is None or bar['volume'] <= 0 for bar in bars):
        return None
    quantity = sum(bar[actor] for bar in bars)
    return dict(net=quantity, pct=100 * quantity / sum(bar['volume'] for bar in bars))


def direction(left, right):
    if left <= -THRESHOLD and right >= THRESHOLD:
        return 'to_bond'
    if left >= THRESHOLD and right <= -THRESHOLD:
        return 'to_equity'
    return 'mixed'


def episode(equity, bond, days, actor):
    # Use the reference ETF's dates. A missing leg never shortens a window.
    daily = []
    for i, day in enumerate(days):
        state, way = 'waiting', None
        if i >= 2:
            for n, minimum, label in ((3, 2, 'early'), (5, 3, 'persistent')):
                if i + 1 < n:
                    break
                dates = days[i-n+1:i+1]
                a, b = window(equity, dates, actor), window(bond, dates, actor)
                if a is None or b is None:
                    break
                candidate = direction(a['pct'], b['pct'])
                agree = sum((equity[d][actor] < 0 < bond[d][actor]) if candidate == 'to_bond'
                            else (bond[d][actor] < 0 < equity[d][actor]) for d in dates)
                if candidate == 'mixed' or agree < minimum:
                    if n == 3:
                        state = 'mixed'
                    break
                if n == 5 and candidate != way:
                    break
                way, state = candidate, label
        daily.append(dict(day=day, state=state, direction=way))
    return daily


def summarize_kr(data):
    series = data['series']
    days = sorted(series['069500'])
    output = {}
    for code, bars in series.items():
        close = bars.get(days[-1], {}).get('close')
        prior = bars.get(days[-21], {}).get('close') if len(days) >= 21 else None
        metrics = {actor: {n: window(bars, days[-n:], actor) if len(days) >= n else None
                           for n in (3, 5, 20)} for actor in ACTORS}
        output[code] = dict(name=INSTRUMENTS[code], metrics=metrics, close=close,
                            price20=(close / prior - 1) * 100 if close and prior else None)
    pairs = {f'{eq}/{bond}/{actor}': episode(series[eq], series[bond], days, actor)
             for eq in ('069500', '091160') for bond in ('114260', '148070') for actor in ACTORS}
    return dict(as_of=days[-1], days=days, instruments=output, pairs=pairs,
                checked_at=data['checked_at'])


def ici_table(rows, published, today):
    """Official table in millions of US dollars, newest week first."""
    if not rows or not rows[0]:
        raise ValueError('ICI 주간 표 누락')
    dates = [datetime.strptime(v, '%m/%d/%Y').date() for v in rows[0] if v.strip()]
    if (not 1 <= len(dates) <= 12 or published > today or dates[0] > published
        or any(not 4 <= (a-b).days <= 10 for a, b in zip(dates, dates[1:]))):
        raise ValueError('ICI 발표일·관측주 확인 필요')
    values = {}
    for row in rows[1:]:
        if row and row[0].strip() in ('Equity', 'Bond'):
            label = row[0].strip()
            if label in values or len(row) != len(dates) + 1:
                raise ValueError('ICI 주식·채권 열 확인 필요')
            values[label] = [integer(v) for v in row[1:]]
    if set(values) != {'Equity', 'Bond'}:
        raise ValueError('ICI 주식·채권 행 확인 필요')
    return dict(published=published.isoformat(), as_of=dates[0].isoformat(),
                weeks=[dict(day=d.isoformat(), equity=values['Equity'][i], bond=values['Bond'][i])
                       for i, d in enumerate(dates)])


def parse_ici_release(raw, today):
    html = raw.decode('utf-8')
    plain = re.sub(r'<[^>]+>', ' ', html)
    if ('Millions of dollars' not in plain or 'Combined Estimated Long-Term' not in plain):
        raise ValueError('ICI 표 제목·단위 확인 필요')
    match = re.search(r'Washington,\s*DC\s*;\s*([A-Za-z]+ \d{1,2}, \d{4})', plain)
    if not match:
        raise ValueError('ICI 발표일 확인 필요')
    published = datetime.strptime(match[1], '%B %d, %Y').date()
    parser = Tables()
    parser.feed(html)
    for table in parser.tables:
        if any(row and row[0] == 'Equity' for row in table):
            return ici_table(table, published, today)
    raise ValueError('ICI 주간 표 누락')


def _fetch(url, params=None):
    with requests.get(url, params=params, timeout=(3, 6), stream=True) as response:
        response.raise_for_status()
        chunks = bytearray()
        for chunk in response.iter_content(65536):
            chunks.extend(chunk)
            if len(chunks) > 2_000_000:
                raise ValueError('공개자료 응답 크기 초과')
        return bytes(chunks)


def folder(root):
    return Path(root) / '.local' / 'market-flows'


def read(root, name):
    try:
        return json.loads((folder(root) / (name + '.json')).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None


def save(root, name, data):
    old = read(root, name)
    if old and (data['as_of'] < old['as_of'] or
                (name == 'us' and data['published'] < old['published'])):
        raise ValueError('원천 기준일 후퇴')
    write_json(folder(root) / (name + '.json'), data)


def import_ici(root, rows, published, now):
    data = ici_table(rows, published, now.date())
    folder(root).mkdir(parents=True, exist_ok=True)
    with acquire_lock(folder(root) / 'refresh.lock'):
        save(root, 'us', data)
    return data


def refresh(root, *, now=None, fetch=_fetch):
    now = now or datetime.now(KST)
    cutoff = completed_cutoff(now)
    folder(root).mkdir(parents=True, exist_ok=True)
    errors = {}
    with acquire_lock(folder(root) / 'refresh.lock'):
        try:
            series, hashes = {}, {}
            for code in INSTRUMENTS:
                raw = fetch(NAVER.format(code), {'page': 1, 'pageSize': 40})
                series[code] = parse_trades(code, json.loads(raw), cutoff)
                hashes[code] = sha256(raw).hexdigest()
            as_of = max(series['069500'])
            if any(max(bars) != as_of for bars in series.values()):
                raise ValueError('종목별 최근 완료일 불일치')
            save(root, 'kr', dict(as_of=as_of, checked_at=now.isoformat(timespec='seconds'),
                                  series=series, hashes=hashes))
        except (requests.RequestException, ValueError, KeyError, TypeError, OSError):
            errors['kr'] = '국내 조회·검증 실패'
        try:
            save(root, 'us', parse_ici_release(fetch(ICI), now.date()))
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError, OSError):
            errors['us'] = 'ICI 자동 조회·검증 실패'
        write_json(folder(root) / 'attempt.json', dict(checked_at=now.isoformat(timespec='seconds'), errors=errors))
    return errors


def view(root, now=None):
    now = now or datetime.now(KST)
    kr, us = read(root, 'kr'), read(root, 'us')
    previous = completed_cutoff(now)
    while previous.weekday() >= 5:
        previous -= timedelta(days=1)
    if kr:
        kr = summarize_kr(kr)
        kr['stale'] = date.fromisoformat(kr['as_of']) != previous
    if us:
        us['stale'] = (now.date() - date.fromisoformat(us['published'])).days > 8
    return dict(kr=kr, us=us, attempt=read(root, 'attempt'), viewed_on=now.date().isoformat())



def render_page(data, token=None):
    from .workspace_export import script_json
    template = Path(__file__).resolve().parents[1] / 'src' / 'market_flows.html'
    return template.read_text(encoding='utf-8').replace('/*FLOW_TOKEN*/', script_json(token)).replace(
        '/*FLOW_DATA*/', script_json(data))
