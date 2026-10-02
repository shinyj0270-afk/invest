"""Read-only, dated facts for the integrated dashboard; no recommendations."""
from datetime import date, timedelta
import re
from statistics import mean

from .core import eligible, num
from .market_events import safe_url
from .trend import MODEL, calculate
from .price_strength import analyze_price_strength, benchmark_excess
from .trend_diagnostics import diagnose, update_rank


METRICS = {'roe_pct': 'ROE', 'operating_margin_pct': '영업이익률',
           'revenue_growth_pct': '매출 증가율', 'debt_ratio_pct': '부채비율',
           'per': 'PER', 'pbr': 'PBR'}
RS_LABEL = '가격추세 순위(주) · 저장 유효 기업 내 순위 / 126·252거래일 지수 초과수익(보조)'


def _day(value):
    try:
        return date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _ordered(items):
    return all(_day(d) for d in items) and all(a < b for a, b in zip(items, items[1:]))


def _period_end(value):
    """Recognize the project's ISO, quarter, half-year and annual labels."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    iso = _day(value[:10])
    if iso is not None and (len(value) == 10 or value[10].isspace()):
        return iso
    match = re.fullmatch(r'(\d{4})-?(?:Q([1-4])|H([12]))', value)
    if match:
        year, quarter, half = match.groups()
        month = int(quarter)*3 if quarter else int(half)*6
        return date(int(year), month, 31 if month in (3, 12) else 30) if int(year) > 0 else None
    if re.fullmatch(r'\d{4}', value):
        return date(int(value), 12, 31) if int(value) > 0 else None
    return None


def _technical(row, snapshot):
    meta = snapshot['meta']; cutoff = meta['price_date']
    result = dict(status='unknown', reason='확정·동일 거래소·수정 기준의 연속 가격 이력 필요',
        model=MODEL, rs126=None, rs252=None, rs126_pct=None, rs252_pct=None,
        sma={str(n): None for n in (50, 150, 200)}, close=None, high_52w_close=None,
        gap_to_52w_high_pct=None, high_52w_reason='52주 전체 거래일과 확정 수정종가 필요',
        contraction=None, breakout=None, history_count=0, as_of=cutoff, series=[])
    overlay = bool(row.get('trend_prices'))
    raw = row.get('trend_prices') if overlay else row.get('prices', [])
    sessions = meta.get('trend_sessions', snapshot.get('sessions', [])) if overlay else snapshot.get('sessions', [])
    # Future observations are excluded, while duplicates/order defects fail closed.
    if not _ordered([b.get('date') for b in raw]) or not _ordered(sessions):
        result['reason'] = '가격·거래일 날짜 정렬/중복/유효성 확인 필요'
        return result
    bars = [b for b in raw if b['date'] <= cutoff]
    expected = [d for d in sessions if d <= cutoff]
    result['history_count'] = len(bars)
    if not bars or not expected or bars[-1]['date'] != cutoff or expected[-1] != cutoff:
        result['reason'] = '가격 이력이 기준일까지 도달하지 않음 · 재조회 필요'
        return result
    venue = row.get('trend_price_venue') if overlay else row.get('price_venue')
    if not venue or any(b.get('final') is not True or b.get('venue') != venue
            or b.get('adjustment_basis') != 'split_adjusted'
            or not num(b.get('close')) or b['close'] <= 0 for b in bars):
        return result
    if len(expected) < len(bars) or [b['date'] for b in bars] != expected[-len(bars):]:
        result['reason'] = '선택 가격 이력에 누락 거래일 또는 거래일 불일치가 있음'
        return result
    closes = [b['close'] for b in bars]
    result['close'] = closes[-1]
    result['sma'] = {str(n): mean(closes[-n:]) if len(closes) >= n else None for n in (20, 50, 150, 200)}
    result['series'] = [dict(date=bars[i]['date'], close=closes[i],volume=bars[i].get('volume'),
        **{'ma'+str(n): mean(closes[i-n+1:i+1]) if i+1 >= n else None for n in (20, 50, 150, 200)})
        for i in range(max(0, len(bars)-253), len(bars))]
    result['reason'] = '기존 추세 판정에 253거래일·확정 벤치마크·OHLCV 필요'
    lower = (_day(cutoff)-timedelta(weeks=52)).isoformat()
    calendar_ok = meta.get('calendar_basis') == 'verified_exchange_sessions' or (
        meta.get('data_mode') == 'fixture' and meta.get('calendar_basis') == 'synthetic_weekdays')
    canonical = snapshot.get('sessions', [])
    if calendar_ok:
        canonical = [d for d in canonical if d <= cutoff]
        calendar_ok = (_ordered(canonical) and bool(canonical) and canonical[0] <= lower
            and [b['date'] for b in bars if b['date'] > lower] == [d for d in canonical if d > lower])
    if not calendar_ok:
        result['high_52w_reason'] = '전체 거래일 캘린더 미확인 · 관측일만으로 52주 최고 확정 불가'
    elif bars[0]['date'] <= lower:
        window = [b['close'] for b in bars if b['date'] > lower]
        high = max(window)
        result['low_52w_close']=min(window)
        result.update(high_52w_close=high, gap_to_52w_high_pct=(closes[-1]/high-1)*100,
                      high_52w_reason='기준일 포함 직전 52주 수정종가 최고 · 장중 고가 기준 아님')
    benchmark = snapshot.get('benchmarks', {}).get(row['market'], [])
    if not _ordered([b.get('date') for b in benchmark]):
        return result
    bm = {b['date']: b for b in benchmark if b['date'] <= cutoff}
    window = bars[-253:]
    if len(window) < 253 or any(b['date'] not in bm or bm[b['date']].get('final') is not True
        or bm[b['date']].get('venue') != venue for b in window):
        return result
    if any(not num(b.get('high')) or not num(b.get('low')) or not 0 < b['low'] <= b['close'] <= b['high']
           for b in window):
        result['reason'] = '추세 OHLC 가격 범위 확인 필요'
        return result
    existing = calculate(row, benchmark, sessions, cutoff)
    for key in ('status', 'reason', 'rs126', 'rs252', 'contraction', 'breakout'):
        result[key] = existing[key]
    for n in (126, 252):
        value = result['rs'+str(n)]
        result['rs'+str(n)+'_pct'] = value*100 if num(value) else None
    result['trend_analysis']=diagnose(bars,result)
    return result


def _fundamental(row, snapshot):
    meta = snapshot['meta']; period = row.get('financial_period', meta.get('financial_period', ''))
    cutoff = meta['price_date']; period_day = _period_end(period)
    available = row.get('financial_available_on')
    valid = period_day is not None and period_day <= _day(cutoff) and (
        not available or (_day(available) is not None and available <= cutoff))
    metrics = {key: row.get('metrics', {}).get(key) if valid and num(row.get('metrics', {}).get(key)) else None
               for key in METRICS}
    # Valuation observations have independent dates and verified denominators.
    # Never pass through an unproven raw ratio, or hide a validated ratio because
    # a separate profitability period is missing.
    for key in ('per', 'pbr'):
        detail = row.get('valuation_details', {}).get(key, {})
        metrics[key] = detail.get('value') if detail.get('status') in ('observed', 'derived') and num(detail.get('value')) else None
    notes = [f'{label} {metrics[key]:,.2f}{"배" if key in ("per", "pbr") else "%"}'
             for key, label in METRICS.items() if metrics[key] is not None]
    if not valid:
        notes.insert(0, '재무 보고기간·공개 시점 확인 필요')
    elif not notes:
        notes = ['비교 가능한 재무 수치 입력 대기']
    return dict(period=period, basis=row.get('financial_basis', meta.get('financial_basis')),
        metrics=metrics, notes=notes,
        scope='스냅샷 보고기간의 관측 수치 · 현재 수익성/저평가 여부는 사용자 조건으로 판단')


def _events(items, code, cutoff, fixture):
    result = []
    for item in items:
        if not isinstance(item, dict) or item.get('code', code) != code:
            continue
        if fixture and item.get('data_mode') != 'fixture':
            continue
        if item.get('kind') not in ('news', 'disclosure'):
            continue
        published = item.get('published_on'); seen = item.get('first_seen_at')
        if not _day(published) or published > cutoff or (seen and (not _day(seen[:10]) or seen[:10] > cutoff)):
            continue
        if any(not isinstance(item.get(k), str) or not item[k].strip() or len(item[k]) > limit
               for k, limit in (('title', 1000), ('source', 200))):
            continue
        try:
            url = safe_url(item.get('url'))
        except ValueError:
            continue
        # Explicit public-field allowlist: review flags and personal notes stay local.
        result.append(dict(kind=item['kind'], title=item['title'], source=item['source'],
                           url=url, published_on=published))
    return sorted(result, key=lambda x: x['published_on'], reverse=True)[:20]


def build_research(snapshot, events=None):
    """Summarize a validated snapshot without filesystem, network or private state reads.

    ``events`` is an optional code -> list mapping of cached public event metadata.
    Ratios come from the caller's enriched valuation copy. A verified complete trading
    calendar is declared by meta.calendar_basis='verified_exchange_sessions'.
    """
    meta = snapshot['meta']; cutoff = meta['price_date']; events = events or {}
    rows = {}; strength = analyze_price_strength(snapshot)
    for row in snapshot['companies']:
        if not eligible(row):
            continue
        technical = _technical(row, snapshot)
        technical['price_strength'] = strength[row['code']]
        if technical.get('trend_analysis'):update_rank(technical['trend_analysis'],technical['price_strength']['score'])
        extra = benchmark_excess(row, snapshot)
        # Main and companion measures use the same canonical, verified dates.
        # Do not retain legacy RS values from an unverified source intersection.
        technical.update(extra)
        if technical['price_strength']['weighted_return_pct'] is None and not row.get('suspended'):
            technical.update(status='unknown', reason=technical['price_strength']['reason'])
        rows[row['code']] = dict(code=row['code'], fundamental=_fundamental(row, snapshot),
            technical=technical, events=_events(events.get(row['code'], []),
                row['code'], cutoff, meta['data_mode'] == 'fixture'))
    return dict(as_of=cutoff, data_mode=meta['data_mode'], rs_choice='price_primary_excess_secondary', rs_label=RS_LABEL, rows=rows)
