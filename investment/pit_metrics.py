"""Pure financial metrics from one annual PIT row, with completeness reasons.

Design: docs/review/design_financial_concepts_NICE_2026-11-04.md.
"""
from math import isfinite

METRIC_NAMES = (
    'total_debt', 'liquid_assets', 'net_debt', 'ebitda', 'fcf',
    'debt_ratio_pct', 'debt_to_assets_pct', 'debt_to_capital_pct',
    'ebit_margin_pct', 'ebitda_margin_pct', 'roa_op_pct', 'roe_pct',
    'debt_to_ebitda', 'net_debt_to_ebitda', 'ebitda_to_finance_costs',
    'ebitda_to_interest', 'ocf_to_debt_pct', 'fcf_to_debt_pct',
    'short_term_debt_ratio_pct',
)


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):return None
    try:value = float(value)
    except OverflowError:return None
    return value if isfinite(value) else None


def _result(value, reasons=()):
    return dict(value=None if value is None else float(value),
                status='unknown' if value is None else 'partial' if reasons else 'ok',
                reasons=sorted(set(reasons)))


def _raw(values, key):
    value = _number(values.get(key))
    return _result(value, [f'missing:{key}'] if value is None else [])


def _inherited(name, result):
    """Keep existing metric provenance when a derived input is reused."""
    reasons = [r if r.split(':')[0] in METRIC_NAMES else f'{name}:{r}'
               for r in result['reasons']]
    return _result(result['value'], reasons)


def _combine(inputs, operation, reasons=()):
    reasons = list(reasons) + [r for item in inputs for r in item['reasons']]
    values = [item['value'] for item in inputs]
    return _result(None if any(v is None for v in values) else operation(*values), reasons)


def _debt(values):
    current = _raw(values, 'borrowings_current')
    noncurrent = _raw(values, 'borrowings_noncurrent')
    total, lc, ln = (_number(values.get(k)) for k in ('lease_total', 'lease_current', 'lease_noncurrent'))
    reasons = []
    if total is not None:
        lease = total
        if lc is not None and ln is not None and abs(lc + ln - total) > abs(total) * .01:
            lease = None
            reasons = ['lease_inconsistent']
    elif lc is not None and ln is not None:lease = lc + ln
    else:
        lease = (lc if lc is not None else 0.0) + (ln if ln is not None else 0.0)
        reasons = ['lease_unconfirmed' if lc is None and ln is None else 'lease_incomplete']
    return _combine([current, noncurrent, _result(lease, reasons)], lambda a, b, c:a + b + c)


def _optional(values, key):
    """An input counted as 0 when absent, but flagged: the result is then a bound, not a confirmed value."""
    value = _number(values.get(key))
    return _result(0.0, [f'{key}_absent']) if value is None else _result(value)


def _liquid(values):
    """현금및현금성자산 + 단기금융상품 + 유동금융자산 (the confirmed definition)."""
    parts = [_raw(values, 'cash'), _optional(values, 'short_term_financial_instruments'), _optional(values, 'current_financial_assets')]
    return _combine(parts, lambda a, b, c:a + b + c)


def _ebitda(values):
    da = _number(values.get('da_total'))
    reasons = []
    if da is None:
        dep, amort, rou = (_number(values.get(k)) for k in ('depreciation', 'amortization', 'rou_depreciation'))
        if dep is None or amort is None:reasons = ['missing:da']
        else:
            da = dep + amort + (rou if rou is not None else 0.0)
            leases = [_number(values.get(k)) for k in ('lease_total', 'lease_current', 'lease_noncurrent')]
            if rou is None and any(v is not None and v > 0 for v in leases):reasons = ['rou_depreciation_absent']
    return _combine([_raw(values, 'op'), _result(da, reasons)], lambda a, b:a + b)


def _fcf(values):
    return _combine([_raw(values, 'ocf'), _raw(values, 'capex_tangible'), _optional(values, 'capex_intangible')], lambda a, b, c:a - b - c)


def _ratio(numerator, denominator, name, scale=1.0):
    if denominator['value'] is not None and denominator['value'] <= 0:
        denominator = _result(None, denominator['reasons'] + [f'non_positive_{name}'])
    return _combine([numerator, denominator], lambda a, b:a / b * scale)


def _short_debt(values):
    lease = _number(values.get('lease_current'))
    reasons = []
    if lease is None:
        lease = 0.0
        if _number(values.get('lease_total')) != 0:reasons = ['lease_current_absent']
    return _combine([_raw(values, 'borrowings_current'), _result(lease, reasons)], lambda a, b:a + b)


def compute_metrics(values):
    """Return ordered metrics without modifying the supplied value fields."""
    debt, liquid = _debt(values), _liquid(values)
    net = _combine([_inherited('total_debt', debt), _inherited('liquid_assets', liquid)], lambda a, b:a - b)
    metrics = dict(total_debt=debt, liquid_assets=liquid, net_debt=net, ebitda=_ebitda(values), fcf=_fcf(values))

    def get(name):
        return _inherited(name, metrics[name]) if name in metrics else _raw(values, name)

    capital = _combine([get('total_debt'), get('equity')], lambda a, b:a + b)
    ratios = (
        ('debt_ratio_pct', 'total_liabilities', 'equity', 100.0),
        ('debt_to_assets_pct', 'total_debt', 'total_assets', 100.0),
        ('debt_to_capital_pct', 'total_debt', 'capital', 100.0),
        ('ebit_margin_pct', 'op', 'revenue', 100.0),
        ('ebitda_margin_pct', 'ebitda', 'revenue', 100.0),
        ('roa_op_pct', 'op', 'total_assets', 100.0),
        ('roe_pct', 'net_income_total', 'equity', 100.0),
        ('debt_to_ebitda', 'total_debt', 'ebitda', 1.0),
        ('net_debt_to_ebitda', 'net_debt', 'ebitda', 1.0),
        ('ebitda_to_finance_costs', 'ebitda', 'finance_costs', 1.0),
        ('ebitda_to_interest', 'ebitda', 'interest_expense', 1.0),
        ('ocf_to_debt_pct', 'ocf', 'total_debt', 100.0),
        ('fcf_to_debt_pct', 'fcf', 'total_debt', 100.0),
    )
    derived = {name:_ratio(get(num), capital if den == 'capital' else get(den), den, scale)
               for name, num, den, scale in ratios}
    short = _ratio(_short_debt(values), get('total_debt'), 'total_debt', 100.0)
    return dict(metrics, **derived, short_term_debt_ratio_pct=short)
