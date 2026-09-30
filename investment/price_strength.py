"""Saved-universe price strength; explicit interpretation, not a vendor RS clone."""
from collections import defaultdict
from bisect import bisect_left, bisect_right
from datetime import date

from .core import eligible, num

MODEL = 'saved-price-strength-quarterly-1.0'
FORMULA = '(2*q0 + q1 + q2 + q3) / 5; qj = P(t-63*j)/P(t-63*(j+1))-1'
MINIMUM = 5


def _dates(values):
    try:
        return all(isinstance(v, str) and date.fromisoformat(v).isoformat() == v for v in values) and all(
            a < b for a, b in zip(values, values[1:]))
    except ValueError:
        return False


def _venue(row):
    return row.get('trend_price_venue') if row.get('trend_prices') else row.get('price_venue')


def _window(row, snapshot):
    meta = snapshot['meta']; cutoff = meta['price_date']
    if row.get('suspended'):
        return None, '거래정지 기업 제외'
    if not (meta.get('calendar_basis') == 'verified_exchange_sessions' or (
        meta.get('data_mode') == 'fixture' and meta.get('calendar_basis') == 'synthetic_weekdays')):
        return None, '전체 거래일 캘린더 확인 필요'
    overlay = bool(row.get('trend_prices'))
    raw = row['trend_prices'] if overlay else row.get('prices', [])
    # A source's intersection of observed dates cannot certify the exchange
    # calendar. All ranked stocks must use the same verified canonical sessions.
    sessions = snapshot.get('sessions', [])
    if not _dates(sessions) or not _dates([b.get('date') for b in raw]):
        return None, '가격·거래일 날짜 정렬/중복/유효성 확인 필요'
    bars = [b for b in raw if b['date'] <= cutoff][-253:]
    expected = [d for d in sessions if d <= cutoff][-253:]
    if len(bars) < 253 or len(expected) < 253:
        return None, '252거래일 수익률에 확정 종가 253개 필요'
    if expected[-1] != cutoff or [b['date'] for b in bars] != expected:
        return None, '기준일까지 동일한 253거래일 종가 필요 · 누락/오래된 이력 확인'
    if overlay and 'trend_sessions' in meta:
        dates = meta['trend_sessions']
        if not _dates(dates) or [d for d in dates if d <= cutoff][-253:] != expected:
            return None, '추세 관측일과 검증된 거래일 캘린더 불일치'
    venue = _venue(row)
    if not venue or any(b.get('final') is not True or b.get('venue') != venue
        or b.get('adjustment_basis') != 'split_adjusted' or not num(b.get('close')) or b['close'] <= 0 for b in bars):
        return None, '확정·동일 거래소·분할수정 기준의 양수 종가 필요'
    return bars, None


def analyze_price_strength(snapshot):
    """Return code -> facts, ranking before any UI filters, separately by venue.

    universe_count counts saved eligible securities of the same venue;
    eligible_count counts valid price windows used in that venue's ranking.
    Quarter returns are independent 63-session intervals, newest first.
    """
    rows = [r for r in snapshot['companies'] if eligible(r)]
    pools = defaultdict(list); saved = defaultdict(int); results = {}
    for row in rows:
        venue = _venue(row); saved[venue] += 1
        result = dict(score=None, weighted_return_pct=None, quarter_returns_pct=None,
            universe_count=0, eligible_count=0, status='unknown', reason='',
            formula=FORMULA, model=MODEL, as_of=snapshot['meta']['price_date'], venue=venue)
        results[row['code']] = result
        bars, reason = _window(row, snapshot)
        if reason:
            result['reason'] = reason
            continue
        prices = [b['close'] for b in bars]
        quarters = [prices[-1-63*j]/prices[-1-63*(j+1)]-1 for j in range(4)]
        momentum = (2*quarters[0]+sum(quarters[1:]))/5
        if not all(num(v*100) for v in quarters+[momentum]):
            result['reason'] = '분기 수익률 계산 범위 확인 필요'
            continue
        result.update(weighted_return_pct=momentum*100, quarter_returns_pct=[v*100 for v in quarters])
        pools[venue].append((row['code'], momentum))
    sorted_values = {venue: sorted(value for _, value in pool) for venue, pool in pools.items()}
    by_code = {code: value for pool in pools.values() for code, value in pool}
    for row in rows:
        result = results[row['code']]; venue = result['venue']; pool = pools[venue]
        result.update(universe_count=saved[venue], eligible_count=len(pool))
        if result['weighted_return_pct'] is None:
            continue
        if len(pool) < MINIMUM:
            result['reason'] = f'저장 유효 {len(pool)}개 · 순위 산출은 같은 거래소 5개 이상 필요'
            continue
        value = by_code[row['code']]; ordered = sorted_values[venue]
        less = bisect_left(ordered, value); tied = bisect_right(ordered, value)-less
        result.update(score=min(99.99, 100*(less+.5*tied)/len(pool)), status='ready',
            reason=f'저장 유효 {len(pool)}개 내 순위 · {venue} · 전체 시장 순위 아님')
    return results


def benchmark_excess(row, snapshot):
    """Price-only companion to the existing 126/252-session index excess return."""
    empty = dict(rs126=None, rs252=None, rs126_pct=None, rs252_pct=None)
    bars, reason = _window(row, snapshot)
    if reason:
        return empty
    raw = snapshot.get('benchmarks', {}).get(row['market'], [])
    if not _dates([b.get('date') for b in raw]):
        return empty
    benchmark = {b['date']: b for b in raw if b['date'] <= snapshot['meta']['price_date']}
    if any(b['date'] not in benchmark or benchmark[b['date']].get('final') is not True
        or benchmark[b['date']].get('venue') != _venue(row)
        or benchmark[b['date']].get('adjustment_basis') != 'split_adjusted'
        or not num(benchmark[b['date']].get('close')) or benchmark[b['date']]['close'] <= 0 for b in bars):
        return empty
    for n in (126, 252):
        end, start = bars[-1], bars[-1-n]
        value = end['close']/start['close']-benchmark[end['date']]['close']/benchmark[start['date']]['close']
        if num(value*100):
            empty['rs'+str(n)] = value
            empty['rs'+str(n)+'_pct'] = value*100
    return empty
