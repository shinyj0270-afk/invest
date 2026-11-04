"""Point-in-time Q, G, C, B factors and their separately ranked score."""
from datetime import date
from statistics import median
from .core import continuous, num, percentile, select_vintage
from .pit_metrics import compute_metrics
from .pit_quality import partial_factors


LIQUID_UNDERSTATEMENT = frozenset({
    'liquid_assets:current_financial_assets_absent',
    'liquid_assets:short_term_financial_instruments_absent',
    'current_financial_assets_absent',
    'short_term_financial_instruments_absent',
})


def _validate_tolerated(tolerated):
    if not isinstance(tolerated, (set, frozenset)) or not all(isinstance(r, str) for r in tolerated):
        raise TypeError('tolerated must be a set or frozenset of strings')


def _net_debt(row, tolerated):
    metric = compute_metrics(row)['net_debt']
    usable = metric['value'] is not None and (metric['status'] == 'ok' or
             (metric['status'] == 'partial' and set(metric['reasons']) <= tolerated))
    if not usable:return None, [f'net_debt:{r}' for r in metric['reasons']], []
    return metric['value'], [], metric['reasons'] if metric['status'] == 'partial' else []


def _equity(row):
    value = row.get('equity')
    return (value, []) if num(value) else (None, ['missing:equity'])


def _balance(row, debt):
    equity, reasons = _equity(row)
    net, errors, approximations = debt
    reasons = reasons + errors
    if equity is not None and equity <= 0:reasons = reasons + ['non_positive_equity']
    value = -net / equity if not reasons else None
    return value, reasons, approximations


def _nopat(row):
    op, pretax, tax = (row.get(k) for k in ('op', 'pretax_income', 'income_tax_expense'))
    reasons = [f'missing:{k}' for k, v in (('op', op), ('pretax_income', pretax)) if not num(v)]
    if not num(pretax):return None, reasons, []
    if pretax <= 0:return (op if num(op) else None), reasons, ['tax_rate_zero_for_loss']
    if not num(tax):return None, reasons + ['missing:income_tax_expense'], []
    rate = tax / pretax
    if not 0 <= rate <= 1:return None, reasons + ['tax_rate_unusable'], []
    return (op * (1 - rate) if num(op) else None), reasons, []


def _quality(rows, debts):
    capitals, reasons, approximations = [], [], []
    for row, (net, errors, used) in zip(rows, debts):
        equity, missing = _equity(row)
        capitals.append(equity + net if equity is not None and net is not None else None)
        reasons.extend(errors + missing)
        approximations.extend(used)
    roics = []
    for prev, cur, row in zip(capitals, capitals[1:], rows[1:]):
        nopat, errors, used = _nopat(row)
        reasons.extend(errors)
        approximations.extend(used)
        average = (prev + cur) / 2 if prev is not None and cur is not None else None
        if average is not None and average <= 0:reasons.append('non_positive_invested_capital')
        roics.append(nopat / average if nopat is not None and average is not None and average > 0 else None)
    value = median(roics) if all(v is not None for v in roics) else None
    return value, reasons, approximations


def compute_factors(pit_rows, as_of, *, tolerated=frozenset()):
    """Use visible annual vintages, retaining completeness and approximation reasons."""
    _validate_tolerated(tolerated)
    base = partial_factors(pit_rows, as_of)
    selected = select_vintage(pit_rows, as_of)
    annual = select_vintage([r for r in selected if r.get('ambiguous') is not True], as_of)
    enough = continuous(annual, 4, annual=True)
    rows = annual[-4:] if enough else annual[-1:]
    debts = [_net_debt(r, tolerated) for r in rows]
    q = _quality(rows, debts) if enough else (None, ['not_enough_years'], [])
    b = _balance(rows[-1], debts[-1]) if rows else (None, ['no_annual_row'], [])
    extra = {'Q': q, 'B': b}
    reasons = {k: sorted(set(errors + (['ambiguous_period'] if base['ambiguous_periods'] else [])))
               for k, (value, errors, used) in extra.items() if value is None}
    approximations = {k: sorted(set(used)) for k, (value, errors, used) in extra.items() if used and value is not None}
    factors = dict(G=base['G'], C=base['C'], Q=q[0], B=b[0])
    return dict(base, **factors, missing=sorted(k for k, v in factors.items() if v is None),
                reasons={**base['reasons'], **reasons}, scope='G,C,Q,B', not_computed=['V'],
                tolerated=sorted(tolerated), approximations=approximations, latest_period=annual[-1]['period_end'] if annual else None)


def _is_date(text):
    try:date.fromisoformat(text)
    except ValueError:return False
    return True


def _stale(result, as_of, limit):
    """True when the latest visible annual period is older than `limit` days: the company has no current data (e.g. delisted)."""
    return bool(limit is not None and result['latest_period'] and (date.fromisoformat(as_of) - date.fromisoformat(result['latest_period'])).days > limit)


def _score(result, pools, minimum):
    if result['stale']:return dict(result, S_pit_QGCB=None, reasons={**result['reasons'], 'S_pit_QGCB': ['parse_failed' if result['parse_failed'] else 'stale_period']})
    ps = {k: percentile(result[k], pools[k], minimum) for k in pools}
    complete = all(v is not None for v in ps.values())
    score = 100 * (.30 * ps['Q'] + .25 * ps['G'] + .20 * ps['C'] + .10 * ps['B']) / .85 if complete else None
    reasons = []
    if not complete:
        if result['missing']:reasons.append('factor_missing')
        if any(result[k] is not None and len(pools[k]) < minimum for k in pools):reasons.append('pool_too_small')
    return dict(result, S_pit_QGCB=score, reasons={**result['reasons'], 'S_pit_QGCB': reasons})


def pit_scores(companies, as_of, *, minimum=5, tolerated=frozenset(), max_staleness_days=460, newer_periods=None):
    """Rank factors independently and combine their weighted percentiles; stale companies stay out of every pool.
    `newer_periods` maps a code to the latest annual period_end its filing inventory shows: a stale company with a newer one failed to parse (`parse_failed`), it is not gone."""
    if not isinstance(companies, dict) or not companies:raise ValueError('companies must be a non-empty dict')
    if type(minimum) is not int or minimum < 1:raise ValueError('minimum must be an integer >= 1')
    if not all(isinstance(code, str) for code in companies):raise ValueError('codes must be strings')
    _validate_tolerated(tolerated)
    if max_staleness_days is not None and (type(max_staleness_days) is not int or max_staleness_days < 1):raise ValueError('max_staleness_days must be None or an integer >= 1')
    newer = {} if newer_periods is None else newer_periods
    if not isinstance(newer, dict) or not all(isinstance(k, str) and (v is None or isinstance(v, str) and _is_date(v)) for k, v in newer.items()):raise ValueError('newer_periods must map codes to ISO dates or None')
    results = []
    for code, rows in sorted(companies.items()):
        factors = compute_factors(rows, as_of, tolerated=tolerated)
        if any(r['company'] != code for r in rows):raise ValueError('code must match each row company')
        stale = _stale(factors, as_of, max_staleness_days)
        results.append(dict(factors, code=code, stale=stale, parse_failed=bool(stale and newer.get(code) and newer[code] > factors['latest_period'])))
    pools = {k: [r[k] for r in results if r[k] is not None and not r['stale']] for k in ('G', 'C', 'Q', 'B')}
    return [_score(r, pools, minimum) for r in results]
