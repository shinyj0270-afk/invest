"""Acceptance checks for a PIT projection (design: docs/review/design_PIT_collection_adapter_2026-11-03.md, criteria 2-7).

Pure functions over `pit_annual` receipts. The main check is an INDEPENDENT oracle: validity, eligibility (first session strictly after the
receipt date) and the complete expected row set / selection at every cutoff are re-derived here from the receipts and the calendar with
their own validation rules, then compared with the projection by identity AND values. So a projection that returns nothing, blocks a valid
receipt, projects an invalid one, drops a correction, changes values, shifts dates, adds a transient or shadow row, or hides blocked records
fails. The validity rules are restated here on purpose (not imported from `pit_annual`), so a bug in production validation shows up as a disagreement.
`project_fn` is injectable so the checks themselves can be tested against deliberately broken projections.
`pit_annual` skips invalid receipts, so a known inventory receipt without a usable row is reported as `unresolved` with the cutoff interval it affects,
bound to the same company and to the receipt's actual fiscal period; an unknown company or period is reported as such, never ignored.
"""
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import date
from math import isfinite
import re
from .core import select_vintage
from .pit_annual import project, MAX_GAP_DAYS, _calendar

NOTICE = '이 결과는 회사 단위 복원이며 시장 표본이 아니다(생존·폐지 기업 몇 곳의 접수번호 단위 재구성). 달력은 지수 관측일 기준이며 공식 휴장일 검증이 아니다.'
IDENTITY = ('company', 'period_end', 'basis')
TOP_KEYS = {'company', 'period_end', 'basis', 'report_kind', 'rcept_no', 'rcept_dt', 'values'}
NUMERIC = dict(revenue=(0, None), op=(None, None), ocf=(None, None), equity=(None, None), debt=(0, None), cash=(0, None), dps=(0, None), effective_tax_rate=(0, 1),
               total_assets=(0, None), total_liabilities=(0, None), short_term_financial_instruments=(0, None),
               borrowings_current=(0, None), borrowings_noncurrent=(0, None), lease_current=(0, None),
               lease_noncurrent=(0, None), finance_costs=(0, None), interest_expense=(0, None),
               depreciation=(0, None), amortization=(0, None), rou_depreciation=(0, None),
               capex_tangible=(0, None), capex_intangible=(0, None), dividends_paid=(0, None),
               pretax_income=(None, None), income_tax_expense=(None, None), net_income_total=(None, None))
AMBIGUOUS = 'AMBIGUOUS'


def _iso(value):
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _next_session(day, sessions):
    i = bisect_right(sessions, day)
    return sessions[i] if i < len(sessions) else None


def _previous_session(day, sessions):
    i = bisect_left(sessions, day)
    return sessions[i - 1] if i else None


def _canon_values(raw):
    """Own restatement of the value rules: canonical floats/bools/strings, or None when anything is wrong."""
    if not isinstance(raw, dict) or not raw:return None
    out = {}
    for key, v in raw.items():
        if v is None:continue
        if key in NUMERIC:
            if isinstance(v, bool) or not isinstance(v, (int, float)):return None
            try:x = float(v)
            except OverflowError:return None
            low, high = NUMERIC[key]
            if not isfinite(x) or (low is not None and x < low) or (high is not None and x > high):return None
            out[key] = x
        elif key == 'tax_verified':
            if not isinstance(v, bool):return None
            out[key] = v
        elif key == 'special_dividend':
            if not (isinstance(v, bool) or v == 'unknown'):return None
            out[key] = v
        elif key == 'dps_basis':
            if not (isinstance(v, str) and v.strip()):return None
            out[key] = v
        else:return None
    return out or None


def _gap_days(no, dt):
    try:return (date.fromisoformat(dt) - date(int(no[:4]), int(no[4:6]), int(no[6:8]))).days
    except ValueError:return None


def _independent_valid(r):
    if not isinstance(r, dict) or set(r) - TOP_KEYS or r.get('report_kind') != 'annual':return None
    no, dt, period = r.get('rcept_no'), r.get('rcept_dt'), r.get('period_end')
    if not (isinstance(no, str) and re.fullmatch(r'\d{14}', no) and _iso(dt) and _gap_days(no, dt) is not None and 0 <= _gap_days(no, dt) <= 7):return None
    if not (_iso(period) and period.endswith('-12-31') and period < dt):return None
    if not (isinstance(r.get('company'), str) and re.fullmatch(r'[0-9A-Z]{6}', r['company']) and r.get('basis') in ('CFS', 'OFS')):return None
    return _canon_values(r.get('values'))


def _payload(values):
    return tuple(sorted(values.items()))


def _group_rows(valid):
    """(identity..., available) -> (rcept_no or AMBIGUOUS, payload): the exact row set a correct projection emits."""
    groups = {}
    for r in valid:groups.setdefault(tuple(r[k] for k in IDENTITY) + (r['available'],), []).append(r)
    out = {}
    for key, group in groups.items():
        payloads = {_payload(g['values']) for g in group}
        out[key] = (AMBIGUOUS, ()) if len(payloads) > 1 else (min(g['rcept_no'] for g in group), payloads.pop())
    return out


def _expected_selection(valid, cutoff):
    best = {}
    for r in valid:
        if r['available'] > cutoff or r['period_end'] > cutoff:continue
        key = tuple(r[k] for k in IDENTITY)
        if key not in best or r['available'] > best[key]:best[key] = r['available']
    rows = _group_rows(valid)
    return {key: rows[key + (when,)] for key, when in best.items()}


def _actual_row(r):
    return (AMBIGUOUS, ()) if r.get('ambiguous') else (r['rcept_no'], _payload({k: r[k] for k in r if k in NUMERIC or k in ('tax_verified', 'special_dividend', 'dps_basis')}))


def _oracle(receipts, sessions, rows, blocked):
    problems, valid = [], []
    blocked_numbers = {str(b.get('rcept_no')) for b in blocked if b.get('reason') != 'ambiguous_same_availability'}
    reported_numbers = {str(b.get('rcept_no')) for b in blocked}
    for r in receipts:
        values = _independent_valid(r)
        number = str(r.get('rcept_no')) if isinstance(r, dict) else None
        available = _next_session(r['rcept_dt'], sessions) if values is not None else None
        gap_ok = available is not None and (date.fromisoformat(available) - date.fromisoformat(r['rcept_dt'])).days <= MAX_GAP_DAYS
        if values is None or not gap_ok:
            if number in {str(x.get('rcept_no')) for x in rows if 'rcept_no' in x}:problems.append(dict(rcept_no=number, problem='invalid_receipt_projected'))
            if isinstance(r, dict) and number not in reported_numbers:problems.append(dict(rcept_no=number, problem='invalid_receipt_not_reported_blocked'))
            continue
        if number in blocked_numbers:problems.append(dict(rcept_no=number, problem='valid_receipt_blocked'))
        valid.append(dict(r, available=available, values=values))
    expected = _group_rows(valid)
    actual, seen = {}, set()
    for r in rows:
        key = tuple(r[k] for k in IDENTITY) + (r['available_at'],)
        if key in seen:problems.append(dict(problem='duplicate_row', identity=list(key)))
        seen.add(key);actual[key] = _actual_row(r)
    for key in sorted(set(expected) | set(actual)):
        if expected.get(key) != actual.get(key):problems.append(dict(problem='row_set_differs', identity=list(key), expected=expected.get(key), actual=actual.get(key)))
    cutoffs = {sessions[-1]} if sessions else set()
    for r in valid:cutoffs |= {c for c in (r['rcept_dt'], r['available'], _previous_session(r['available'], sessions)) if c}
    for cutoff in sorted(cutoffs):
        want = _expected_selection(valid, cutoff)
        got = {}
        for r in select_vintage(rows, cutoff):got[tuple(r[k] for k in IDENTITY)] = _actual_row(r)
        for key in sorted(set(want) | set(got)):
            if want.get(key) != got.get(key):problems.append(dict(problem='selection_differs_from_expectation', cutoff=cutoff, identity=list(key), expected=want.get(key), actual=got.get(key)))
    return dict(ok=not problems, problems=problems), valid


def _replay(receipts, sessions, full_rows, project_fn):
    """At every cutoff, projecting only the receipts filed BEFORE it (by their real receipt dates) must give the same selection as projecting everything."""
    bad = []
    for cutoff in sorted({r['available_at'] for r in full_rows}):
        subset = [r for r in receipts if isinstance(r, dict) and str(r.get('rcept_dt')) < cutoff]
        rows = project_fn(subset, sessions)['rows'] if subset else []
        if select_vintage(rows, cutoff) != select_vintage(full_rows, cutoff):bad.append(dict(cutoff=cutoff, problem='later_receipts_change_earlier_cutoff'))
    return dict(ok=not bad, problems=bad)


def _unresolved(inventory, valid, sessions):
    by_number = {r['rcept_no']: r for r in valid}
    out = []
    for item in sorted(inventory, key=lambda i: i['rcept_no']):
        company = item.get('company') or item.get('stock_code') or None
        period = item.get('title_period')
        base = dict(rcept_no=item['rcept_no'], rcept_dt=item['rcept_dt'], company=company, title_period=period,
            affects_from=_next_session(item['rcept_dt'], sessions) if _iso(item['rcept_dt']) else None, affects_until=None)
        hit = by_number.get(item['rcept_no'])
        if hit is not None:
            wrong = item['rcept_dt'] != hit['rcept_dt'] or (company and company != hit['company']) or (period and period != hit['period_end'][:7])
            if wrong:out.append(dict(base, problem='inventory_identity_mismatch'))
            continue
        later = sorted(r['available'] for r in valid if period is not None and company is not None and r['company'] == company
            and r['period_end'][:7] == period and r['rcept_dt'] > item['rcept_dt'])
        out.append(dict(base, problem='receipt_without_usable_row' if period is not None else 'unknown_period',
            company_unknown=company is None, affects_until=later[0] if later else None))
    return out


def verify(receipts, sessions, inventory=None, *, project_fn=project):
    receipts = [dict(r) if isinstance(r, dict) else r for r in receipts]
    sessions = _calendar(sessions)
    scopes = {(r.get('company'), r.get('basis')) for r in receipts if isinstance(r, dict)}
    if len(scopes) > 1:
        return dict(ok=False, checks=dict(single_scope=dict(ok=False, scopes=sorted(map(str, scopes)))), counts={}, unresolved=[], notice=NOTICE)
    full = project_fn(receipts, sessions);rows = full['rows']
    oracle, valid = _oracle(receipts, sessions, rows, full['blocked'])
    checks = dict(single_scope=dict(ok=True), eligibility_oracle=oracle, correction_replay=_replay(receipts, sessions, rows, project_fn),
        order_independence=dict(ok=project_fn(list(reversed(receipts)), sessions) == full))
    counts = dict(rows=sum(1 for r in rows if not r.get('ambiguous')), ambiguous=sum(1 for r in rows if r.get('ambiguous')),
        blocked=dict(Counter(b['reason'] for b in full['blocked'])))
    unresolved = _unresolved([dict(i) for i in inventory], valid, sessions) if inventory else []
    return dict(ok=all(c['ok'] for c in checks.values()) and not unresolved, checks=checks, counts=counts, unresolved=unresolved, notice=NOTICE)
