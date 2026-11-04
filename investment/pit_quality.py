"""Partial point-in-time quality factors and their separately ranked G,C score."""
import re
from datetime import date
from statistics import median
from .core import num, ratio, cagr, continuous, select_vintage, percentile


def _day(value):
    if not isinstance(value, str) or len(value) != 10 or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('날짜는 YYYY-MM-DD 형식이어야 합니다')
    try: date.fromisoformat(value)
    except ValueError as exc: raise ValueError('유효하지 않은 날짜입니다') from exc


def _validate(rows, as_of):
    _day(as_of)
    if not isinstance(rows, list): raise ValueError('PIT 행은 목록이어야 합니다')
    scopes = set()
    for r in rows:
        if not isinstance(r, dict): raise ValueError('PIT 행은 사전이어야 합니다')
        if not all(isinstance(r.get(k), str) for k in ('company', 'basis')):
            raise ValueError('회사와 회계 기준은 문자열이어야 합니다')
        for key in ('period_end', 'available_at'): _day(r.get(key))
        scopes.add((r['company'], r['basis']))
    if len(scopes) > 1: raise ValueError('한 회사와 한 회계 기준만 사용할 수 있습니다')


def _value_reasons(pairs):
    reasons = []
    if any(v is None for v, positive in pairs): reasons.append('missing_value')
    if any(v is not None and (not num(v) or (positive and v <= 0)) for v, positive in pairs):
        reasons.append('unusable_value')
    return reasons or ['unusable_value']


def partial_factors(pit_rows, as_of):
    """Compute G and C from the last four continuous, visible annual periods."""
    _validate(pit_rows, as_of)
    selected = select_vintage(pit_rows, as_of)
    ambiguous = [r['period_end'] for r in selected if r.get('ambiguous') is True]
    a = select_vintage([r for r in selected if r.get('ambiguous') is not True], as_of)
    out = dict(G=None, C=None, missing=[], reasons={}, ambiguous_periods=ambiguous,
               periods_used=[], pit=True, scope='G,C only', not_computed=['Q', 'V', 'B'])
    if continuous(a, 4, annual=True):
        a = a[-4:]
        out['periods_used'] = [r['period_end'] for r in a]
        out['G'] = cagr(a[0].get('revenue'), a[-1].get('revenue'), 3)
        cash = [ratio(r.get('ocf'), r.get('revenue')) for r in a[-3:]]
        out['C'] = median(cash) if all(v is not None for v in cash) else None
        if out['G'] is None:
            out['reasons']['G'] = _value_reasons([(r.get('revenue'), True) for r in (a[0], a[-1])])
        if out['C'] is None:
            out['reasons']['C'] = _value_reasons([(r.get(k), k == 'revenue') for r in a[-3:] for k in ('ocf', 'revenue')])
    else:
        for key in ('G', 'C'): out['reasons'][key] = ['not_enough_years']
    out['missing'] = sorted(k for k in ('G', 'C') if out[k] is None)
    if ambiguous:
        for key in out['missing']: out['reasons'][key].append('ambiguous_period')
    return out


def partial_scores(companies, as_of, *, minimum=5):
    """Rank each available factor independently, then renormalize its weight."""
    if not isinstance(companies, dict) or not companies:
        raise ValueError('회사는 비어 있지 않은 사전이어야 합니다')
    if type(minimum) is not int or minimum < 1: raise ValueError('최소 표본 수는 1 이상의 정수여야 합니다')
    if not all(isinstance(code, str) for code in companies): raise ValueError('종목 코드는 문자열이어야 합니다')
    results = []
    for code, rows in sorted(companies.items()):
        factors = partial_factors(rows, as_of)
        if any(r['company'] != code for r in rows): raise ValueError('종목 코드와 행의 회사가 일치해야 합니다')
        results.append(dict(factors, code=code, S_pit_GC=None))
    pools = {k: [r[k] for r in results if r[k] is not None] for k in ('G', 'C')}
    for r in results:
        ps = {k: percentile(r[k], pools[k], minimum) for k in pools}
        reasons = []
        if all(v is not None for v in ps.values()):
            r['S_pit_GC'] = 100 * (0.25 * ps['G'] + 0.20 * ps['C']) / 0.45
        else:
            if r['missing']: reasons.append('factor_missing')
            if any(r[k] is not None and len(pools[k]) < minimum for k in pools): reasons.append('pool_too_small')
        r['reasons']['S_pit_GC'] = reasons
    return results
