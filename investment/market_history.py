"""Bounded, resumable Naver public daily charts with explicit evidence limits.

The endpoint is used by Naver's own chart JavaScript. Its historical stock prices
show split adjustment (Samsung's April/May 2018 50:1 split was sampled), but the
provider does not return a complete adjustment specification. Preserve that
distinction rather than declaring all prices independently split-verified.
"""
from datetime import date, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import re
from uuid import uuid4
from zoneinfo import ZoneInfo

import requests

from .core import num

KST = ZoneInfo('Asia/Seoul')
BASE = 'https://api.stock.naver.com/chart/domestic/'
SCRIPT_SOURCE = 'https://financial-vn.pstatic.net/client-chart/pc/live/4.4.15/js/chartiq.js'
ADJUSTMENT_NOTE = ('네이버 제공 차트 가격: 삼성전자 2018년 50:1 액면분할 구간 보정 표본 확인. '
                   '전 종목·권리변동별 세부 보정식 미공개, 총수익률 아님. 거래량은 가격과 동일하게 보정됐다고 가정하지 않음.')
MAX_BYTES = 8*1024*1024


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('날짜는 YYYY-MM-DD 형식 필요')
    return date.fromisoformat(value)


def _request(symbol, kind, start, end):
    if kind not in ('item', 'index') or not isinstance(symbol, str) or not (
        re.fullmatch(r'[0-9A-Z]{6}', symbol) if kind == 'item' else symbol in ('KOSPI', 'KOSDAQ')):
        raise ValueError('국내 종목코드 또는 KOSPI/KOSDAQ 지수 필요')
    first, last = _date(start), _date(end)
    if first > last or (last-first).days > 3700:
        raise ValueError('요청 이력은 순서가 맞는 최대 3700일 범위 필요')
    params = dict(startDateTime=first.strftime('%Y%m%d')+'0000',
                  endDateTime=last.strftime('%Y%m%d')+'2359')
    return BASE+kind+'/'+symbol+'/day', params


def _now(value=None):
    value = value or datetime.now(KST)
    if value.tzinfo is None:
        raise ValueError('조회 시각에 시간대 필요')
    return value.astimezone(KST)


def parse_history(payload, *, symbol, kind, start, end, fetched_at):
    """Parse exact source bytes; exclude today's still-revisable session entirely."""
    url, params = _request(symbol, kind, start, end)
    fetched = _now(fetched_at)
    if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_BYTES:
        raise ValueError('일봉 응답 크기 제한')
    data = json.loads(payload)
    if not isinstance(data, list) or len(data) > 4000:
        raise ValueError('일봉 배열/행수 확인 필요')
    cutoff = min(_date(end), fetched.date()-timedelta(days=1)).isoformat()
    prices = []; prior = ''; excluded = 0
    for item in data:
        if not isinstance(item, dict) or not re.fullmatch(r'\d{8}', str(item.get('localDate', ''))):
            raise ValueError('일봉 날짜 형식 오류')
        day = datetime.strptime(item['localDate'], '%Y%m%d').date().isoformat()
        if day <= prior:
            raise ValueError('일봉 날짜 중복/정렬 오류')
        prior = day
        if day < start or day > cutoff:
            excluded += 1
            continue
        close = item.get('closePrice')
        if not num(close) or close <= 0:
            raise ValueError('일봉 양수 종가 확인 필요')
        ohl = {key: item.get(field) for key, field in (
            ('open', 'openPrice'), ('high', 'highPrice'), ('low', 'lowPrice'))}
        volume = item.get('accumulatedTradingVolume')
        if any(v is not None and (not num(v) or v < 0) for v in [volume, *ohl.values()]):
            raise ValueError('OHLCV 숫자 범위 확인 필요')
        # Naver may publish carried close with zero OHLC/volume during suspension.
        # Preserve close observations and missing tradable OHLC, never invent bars.
        zero_ohl = all(v == 0 for v in ohl.values())
        no_trade = volume == 0 and zero_ohl
        ohl_unavailable = zero_ohl
        ohl_inconsistent = False
        if zero_ohl:
            ohl = {key: None for key in ohl}
        elif all(num(v) for v in ohl.values()) and not 0 < ohl['low'] <= min(ohl['open'], close) <= max(ohl['open'], close) <= ohl['high']:
            # The provider's adjusted close occasionally differs from its
            # adjusted high/low by a small rounding amount around corporate
            # actions. Keep the valid close for return work, but do not repair
            # or invent OHLC. Material contradictions still fail closed.
            gap = max(0, max(ohl['open'], close)-ohl['high'], ohl['low']-min(ohl['open'], close))
            if gap / close > .002:
                raise ValueError('OHLC 가격 범위 모순')
            ohl = {key: None for key in ohl}
            ohl_inconsistent = True
        prices.append(dict(date=day, close=close, **ohl, volume=volume, turnover=None,
            final=True, venue='KRX', adjustment_basis='index_level' if kind == 'index' else 'naver_chart_adjusted',
            no_trade=no_trade, ohl_unavailable=ohl_unavailable, ohl_inconsistent=ohl_inconsistent))
    if not prices:
        raise ValueError('요청 범위의 완료된 일봉 없음')
    return dict(symbol=symbol, kind=kind, prices=prices, price_date=prices[-1]['date'],
        source=dict(provider='Naver public chart', url=url, parameters=params,
            fetched_at=fetched.isoformat(), sha256=sha256(payload).hexdigest(),
            endpoint_evidence=SCRIPT_SOURCE, requested_start=start, requested_end=end,
            excluded_outside_completed_window=excluded,
            adjustment_note='일반 KOSPI/KOSDAQ 가격지수 수준 · 총수익지수 아님' if kind == 'index' else ADJUSTMENT_NOTE,
            final_basis='KST 조회일 이전 날짜의 제공자 일봉 관측; 당일 제외, 사후 제공자 정정 가능'))


def _write(path, content):
    temporary = path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def fetch_history(symbol, *, kind='item', start, end, cache_dir, now=None, session=None, force=False):
    """Fetch one public series, or resume a hash-verified exact-range local cache.

    The caller paces batches. No implicit retries, credentials, DB writes, or
    fallback to invented observations. Transport/parse failures propagate.
    """
    url, params = _request(symbol, kind, start, end)
    now = _now(now)
    if _date(end) >= now.date():
        raise ValueError('당일을 제외한 완료일까지만 요청하세요')
    folder = Path(cache_dir)
    name = f'naver-{kind}-{symbol}-{start}-{end}'
    raw_path, meta_path = folder/(name+'.json'), folder/(name+'.meta.json')
    if not force and raw_path.exists() and meta_path.exists():
        try:
            payload = raw_path.read_bytes(); meta = json.loads(meta_path.read_bytes())
            fetched = datetime.fromisoformat(meta['fetched_at'])
            if (meta['sha256'] == sha256(payload).hexdigest() and meta['url'] == url
                and meta['parameters'] == params and fetched.tzinfo is not None
                and fetched <= now and fetched.astimezone(KST).date() > _date(end)):
                return parse_history(payload, symbol=symbol, kind=kind, start=start, end=end, fetched_at=fetched)
        except (ValueError, KeyError, TypeError, OSError):
            pass
    client = session or requests
    response = client.get(url, params=params, timeout=(5, 25),
                          headers={'User-Agent': 'Investment-local-research/1.0'}, stream=True)
    with response:
        response.raise_for_status()
        chunks = []; size = 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError('일봉 응답 크기 제한')
            chunks.append(chunk)
        payload = b''.join(chunks)
    result = parse_history(payload, symbol=symbol, kind=kind, start=start, end=end, fetched_at=now)
    folder.mkdir(parents=True, exist_ok=True)
    _write(raw_path, payload)
    _write(meta_path, json.dumps(result['source'], ensure_ascii=False).encode('utf-8'))
    return result


def benchmark_calendar(histories):
    """Consensus of both source index histories, explicitly not an official calendar."""
    if set(histories) != {'KOSPI', 'KOSDAQ'}:
        raise ValueError('KOSPI/KOSDAQ 두 지수 이력 필요')
    sessions = None; sources = []
    for symbol in ('KOSPI', 'KOSDAQ'):
        record = histories[symbol]
        if record.get('symbol') != symbol or record.get('kind') != 'index':
            raise ValueError('지수 식별정보 불일치')
        prices = record['prices']; dates = [p['date'] for p in prices]
        if len(dates) < 253 or dates != sorted(set(dates)) or any(
            p.get('final') is not True or p.get('venue') != 'KRX'
            or p.get('adjustment_basis') != 'index_level' or not num(p.get('close')) or p['close'] <= 0 for p in prices):
            raise ValueError('지수 완료 관측일 253개 이상 필요')
        if sessions is not None and sessions != dates:
            raise ValueError('KOSPI/KOSDAQ 관측일 불일치 · 교집합으로 누락을 숨기지 않음')
        sessions = dates; sources.append(record['source']['url'])
    return dict(sessions=sessions, calendar_basis='naver_index_sessions',
        calendar_source=sources, valid_from=sessions[0], valid_through=sessions[-1],
        note='네이버 양대 지수의 완료 일봉 관측일 일치 · 공식 KRX 휴장일 달력 검증과 구분')
