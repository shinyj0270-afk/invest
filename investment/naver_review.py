"""Naver market observations for reviewed companies; financials remain untouched."""
from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from .core import digest, validate_snapshot
from .market_history import fetch_history
from .naver_reference import number, source_url
from .store import Store

ADAPTER = 'naver-reviewed-market-0.1'
FLOW_KEYS = ('foreign_net_20d_eok', 'institution_net_20d_eok',
             'foreign_net_turnover_20d_pct', 'institution_net_turnover_20d_pct')
MARKET_KEYS = ('price', 'market_cap_eok', 'avg_trading_value_20d_eok', *FLOW_KEYS)
BASE = 'https://stock.naver.com/api/stockSecurity/items/v2/domestic/'


def daily_values(payload, *, cutoff):
    """Explicit money values only; never approximate turnover from close * volume."""
    rows = payload.get('items')
    if not isinstance(rows, list) or not 20 <= len(rows) <= 100:
        raise ValueError('네이버 일별 거래자료 20~100행 필요')
    result = {}; prior = None
    for raw in rows:
        day = raw['tradingDateKst']
        if datetime.strptime(day, '%Y-%m-%d').date().isoformat() != day:
            raise ValueError('일별 거래일 형식 오류')
        if prior is not None and day >= prior:
            raise ValueError('일별 거래일 중복/내림차순 오류')
        prior = day
        if day > cutoff:
            continue
        close, volume, money = (number(raw.get(k)) for k in
                                ('closingPrice', 'tradingVolume', 'tradingValue'))
        if close is None or close <= 0 or volume is None or volume < 0 or money is None or money < 0:
            raise ValueError('가격·거래량·거래대금 숫자/단위 확인 필요')
        result[day] = dict(close=close, volume=volume, turnover=money)
    return result


def build_market(previous, histories, daily, details, sources, checked_at):
    validate_snapshot(previous)
    if previous['meta']['data_mode'] != 'user_input':
        raise ValueError('기존 실제 검토자료 필요')
    codes = {r['code'] for r in previous['companies']}
    if not codes or not codes == set(histories) == set(daily) == set(details) == set(sources):
        raise ValueError('네이버 종목 구성 불일치')
    cutoff = (checked_at.date()-timedelta(days=1)).isoformat()
    dates = None
    for code, record in histories.items():
        bars = record['prices']; days = [b['date'] for b in bars]
        if (record.get('symbol') != code or record.get('kind') != 'item' or len(days) < 20
                or days != sorted(set(days)) or days[-1] > cutoff
                or record['price_date'] != days[-1]
                or any(b.get('venue') != 'KRX' or b.get('final') is not True
                       or b.get('adjustment_basis') != 'naver_chart_adjusted' for b in bars)):
            raise ValueError('네이버 완료 가격 이력 확인 필요')
        if dates is not None and dates != days:
            raise ValueError('종목별 관측일 불일치')
        dates = days
    end = dates[-1]
    if end < previous['meta']['price_date']:
        raise ValueError('가격일 후퇴')
    result = deepcopy(previous)
    meta = result['meta']
    meta.setdefault('infomax_review_date', previous['meta']['price_date'])
    meta.update(price_date=end, as_of=checked_at.date().isoformat(),
                fetched_at=checked_at.isoformat(), adapter_version=ADAPTER,
                market_provider='naver', venue='KRX · 네이버 공개 시장자료',
                source_files=sources, price_venue='KRX',
                calendar_basis='naver_observed_dates_unverified')
    result['sessions'] = dates
    meta['warnings'] = list(dict.fromkeys(meta.get('warnings', []) + [
        '시장자료는 네이버 공개 응답 · 사후 정정 가능 · 공식 거래일 달력 미대조',
        '수급 금액은 기존 인포맥스 기준일 유지 · 네이버 수량을 금액으로 환산하지 않음']))
    for row in result['companies']:
        code = row['code']; record = histories[code]
        trade = daily_values(daily[code], cutoff=cutoff)
        window = dates[-20:]
        if not all(d in trade for d in window):
            raise ValueError('동일 최근20개 관측일 거래대금 누락')
        bars = deepcopy(record['prices'])
        for bar in bars:
            observed = trade.get(bar['date'])
            if observed:
                # Refuse to join a different venue or corporate-action price basis.
                if bar['close'] != observed['close']:
                    raise ValueError('네이버 일봉과 거래자료 가격 불일치')
                # The daily list may include later volume corrections. Keep its
                # volume and actual money together, with both response hashes.
                bar['volume'] = observed['volume']
                bar['turnover'] = observed['turnover']
        detail = details[code]
        if detail.get('itemcode') != code or detail.get('itemname') != row['name'] or detail.get('type') != 'ST':
            raise ValueError('네이버 종목 식별 불일치')
        stamp = datetime.strptime(detail['tradeTime'], '%Y%m%d%H%M%S').replace(tzinfo=checked_at.tzinfo)
        if stamp > checked_at:
            raise ValueError('미래 시가총액 관측')
        cap = number(detail.get('marketSum'))
        valid_cap = cap is not None and cap > 0 and stamp.date().isoformat() == end
        row['prices'] = bars  # Replace the full price basis; no mixed-source scale joins.
        row['price_venue'] = 'KRX'
        row['metrics'].update(price=bars[-1]['close'], market_cap_eok=cap/1e8 if valid_cap else None,
            avg_trading_value_20d_eok=sum(trade[d]['turnover'] for d in window)/20/1e8)
        reasons = row.setdefault('metric_missing_reasons', {})
        for key in ('price', 'market_cap_eok', 'avg_trading_value_20d_eok'):
            reasons.pop(key, None)
        if not valid_cap:
            reasons['market_cap_eok'] = '네이버 시가총액 관측일과 완료 가격일 불일치 또는 값 미확보'
        # Keep the original amount observations and their dates as evidence.
        # Withhold older window metrics so they cannot drive today's ranking.
        for key in FLOW_KEYS:
            if key.endswith('_pct') or meta['flow_end'] != end:
                row['metrics'][key] = None
                reasons[key] = ('수급 금액 기준 '+meta['flow_end']+
                    ' · 네이버 순매수금액 미연결; 수량×종가 추정 제외')
        row['market_metric_evidence'] = dict(provider='Naver public market', price_date=end,
            turnover_start=window[0], turnover_end=end, turnover_unit='KRW',
            market_cap_date=stamp.date().isoformat() if valid_cap else None,
            flow_amount_date=meta['flow_end'], flow_amount_source='기존 인포맥스 저장본',
            turnover_venue_note='KRX 차트 종가 대조; 거래량·거래대금은 일별 응답의 동시 관측. 공급자 집계 세부 정의 미검증')
        row['sources'] = list({digest(s): s for s in
            [dict(s, label=s.get('label') or s.get('provider') or '네이버 공개 시장자료') for s in
             row.get('sources', []) + [record['source'], *sources[code]]]}.values())
    return validate_snapshot(result)


def validate_candidate(previous, candidate):
    """Only the market fields above may change, including at the same price date."""
    validate_snapshot(candidate)
    allowed_meta = {'infomax_review_date', 'price_date', 'as_of', 'fetched_at', 'adapter_version',
                    'market_provider', 'venue', 'source_files', 'price_venue', 'calendar_basis', 'warnings'}
    for k, v in previous['meta'].items():
        if k not in allowed_meta and candidate['meta'].get(k) != v:
            raise ValueError('기존 메타데이터 변경: '+k)
    old = {r['code']: r for r in previous['companies']}
    if set(old) != {r['code'] for r in candidate['companies']}:
        raise ValueError('종목 구성 변경')
    for row in candidate['companies']:
        prior = old[row['code']]
        for k, v in prior.items():
            if k not in ('prices', 'price_venue', 'metrics', 'metric_missing_reasons', 'sources', 'market_metric_evidence') and row.get(k) != v:
                raise ValueError('기존 검토자료 변경: '+k)
        for k, v in prior['metrics'].items():
            if k not in MARKET_KEYS and row['metrics'].get(k) != v:
                raise ValueError('재무 지표 변경: '+k)
    return candidate


class NaverMarketProvider:
    def __init__(self, root, local):
        self.root, self.local = Path(root), local

    def fetch(self):
        now = datetime.now(ZoneInfo('Asia/Seoul'))
        store = Store(self.local['data_dir'], self.local['profile'], 'user_input')
        previous = store.latest()
        if previous is None:
            path = self.local.get('manual_snapshot_file')
            if not path:
                raise ValueError('기존 실제 검토 스냅샷 필요')
            previous = json.loads(Path(path).read_text(encoding='utf-8-sig'))
        validate_snapshot(previous)
        if not 1 <= len(previous['companies']) <= 30:
            raise ValueError('네이버 검토 갱신은 기존1~30종목 범위')
        folder = self.root/'.local/naver-review'
        folder.mkdir(parents=True, exist_ok=True)
        end = (now.date()-timedelta(days=1)).isoformat()
        first = (now.date()-timedelta(days=550)).isoformat()
        # Re-read the full horizon on each bounded refresh to handle adjustments.
        first = min([first] + [p['date'] for r in previous['companies'] for p in r.get('prices', [])])
        histories = {}; daily = {}; details = {}; sources = {}
        with requests.Session() as client:
            def get(url, params=None):
                with client.get(url, params=params, timeout=(5, 25), stream=True) as response:
                    response.raise_for_status()
                    chunks = []; size = 0
                    for chunk in response.iter_content(65536):
                        size += len(chunk)
                        if size > 2*1024*1024:
                            raise ValueError('네이버 응답 크기 초과')
                        chunks.append(chunk)
                    raw = b''.join(chunks)
                h = sha256(raw).hexdigest()
                path = folder/(h+'.json')
                if not path.exists():
                    with path.open('xb') as out:
                        out.write(raw)
                return json.loads(raw), dict(provider='Naver public market', url=url,
                    parameters=params or {}, sha256=h, fetched_at=now.isoformat())
            for row in previous['companies']:
                code = row['code']
                histories[code] = fetch_history(code, start=first, end=end,
                    cache_dir=folder/'history', now=now, session=client, force=True)
                daily[code], dsource = get(BASE+code+'/daily-prices/paged',
                                           dict(exchangeType='krx', size=100))
                details[code], qsource = get(source_url(code))
                sources[code] = [dsource, qsource]
        candidate = build_market(previous, histories, daily, details, sources, now)
        return candidate, dict(provider='naver', sources=sources,
            histories={c: r['source'] for c, r in histories.items()}), '네이버 공개 시장자료'
