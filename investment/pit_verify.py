"""Acceptance checks for a PIT projection (design: docs/review/design_PIT_collection_adapter_2026-11-03.md, criteria 2-7).

Pure functions over `pit_annual` receipts. The main check is an INDEPENDENT oracle: expected eligibility (first session strictly after
the receipt date, computed here from the receipts and the calendar) and the expected selection at every cutoff around every receipt are
compared with the projection's selection by identity AND values, so a projection that returns nothing, drops a correction, changes
values or shifts dates fails. `project_fn` is injectable so the checks themselves can be tested against deliberately broken projections.
`pit_annual` skips invalid receipts, so a known inventory receipt without a usable row is reported as `unresolved` with the cutoff interval
it affects, per company and period; a missing or unreadable period is reported as unknown, never ignored.
"""
from bisect import bisect_left, bisect_right
from collections import Counter
from .core import select_vintage
from .pit_annual import project, VALUE_FIELDS, _calendar, _check, _values

NOTICE = '이 결과는 회사 단위 복원이며 시장 표본이 아니다(생존·폐지 기업 몇 곳의 접수번호 단위 재구성). 달력은 지수 관측일 기준이며 공식 휴장일 검증이 아니다.'
IDENTITY = ('company', 'period_end', 'basis')


def _identity(row):
    return tuple(row[k] for k in IDENTITY)


def _next_session(day, sessions):
    i = bisect_right(sessions, day)
    return sessions[i] if i < len(sessions) else None


def _previous_session(day, sessions):
    i = bisect_left(sessions, day)
    return sessions[i - 1] if i else None


def _payload(values):
    return tuple(sorted((k, v) for k, v in values.items()))


def _expected(valid, cutoff):
    """identity -> ('AMBIGUOUS', ()) or (rcept_no, payload) for what a correct projection selects at `cutoff`."""
    best = {}
    for r in valid:
        if r['available'] is None or r['available'] > cutoff or r['period_end'] > cutoff:continue
        key = tuple(r[k] for k in IDENTITY)
        if key not in best or r['available'] > best[key][0]:best[key] = (r['available'], [r])
        elif r['available'] == best[key][0]:best[key][1].append(r)
    out = {}
    for key, (_, group) in best.items():
        payloads = {_payload(g['values']) for g in group}
        out[key] = ('AMBIGUOUS', ()) if len(payloads) > 1 else (min(g['rcept_no'] for g in group), payloads.pop())
    return out


def _actual(rows, cutoff):
    out = {}
    for r in select_vintage(rows, cutoff):
        out[_identity(r)] = ('AMBIGUOUS', ()) if r.get('ambiguous') else (r['rcept_no'], _payload({k: r[k] for k in VALUE_FIELDS if k in r}))
    return out


def _oracle(receipts, sessions, rows):
    valid, problems = [], []
    for r in receipts:
        reason, when = _check(r, sessions)
        if reason:continue
        mine = _next_session(r['rcept_dt'], sessions)
        if mine != when:problems.append(dict(rcept_no=r['rcept_no'], problem='availability_computation_disagrees', expected=mine, projected=when))
        valid.append(dict(r, available=mine, values=_values(r['values'])))
    cutoffs = set()
    for r in valid:
        cutoffs |= {c for c in (r['rcept_dt'], r['available'], _previous_session(r['available'], sessions) if r['available'] else None) if c}
    if sessions:cutoffs.add(sessions[-1])
    for cutoff in sorted(cutoffs):
        want, got = _expected(valid, cutoff), _actual(rows, cutoff)
        for key in sorted(set(want) | set(got)):
            if want.get(key) != got.get(key):
                problems.append(dict(cutoff=cutoff, identity=list(key), problem='selection_differs_from_expectation', expected=want.get(key), actual=got.get(key)))
    return dict(ok=not problems, problems=problems), valid


def _replay(receipts, sessions, full_rows, project_fn):
    """At every cutoff, projecting only the receipts filed BEFORE it (by their real receipt dates) must give the same selection as projecting everything."""
    bad = []
    for cutoff in sorted({r['available_at'] for r in full_rows}):
        subset = [r for r in receipts if r['rcept_dt'] < cutoff]
        rows = project_fn(subset, sessions)['rows'] if subset else []
        if select_vintage(rows, cutoff) != select_vintage(full_rows, cutoff):bad.append(dict(cutoff=cutoff, problem='later_receipts_change_earlier_cutoff'))
    return dict(ok=not bad, problems=bad)


def _unresolved(inventory, represented, valid, sessions):
    known = {i['rcept_no']: i for i in inventory}
    out = []
    for item in sorted(inventory, key=lambda i: i['rcept_no']):
        if item['rcept_no'] in represented:continue
        period = item.get('title_period')
        later = sorted(r['available'] for r in valid if period is not None and r['available'] and r['rcept_dt'] > item['rcept_dt']
            and known.get(r['rcept_no'], {}).get('title_period') == period and item.get('company') in (None, r['company']))
        out.append(dict(rcept_no=item['rcept_no'], rcept_dt=item['rcept_dt'], company=item.get('company'), title_period=period,
            problem='receipt_without_usable_row' if period is not None else 'unknown_period',
            affects_from=_next_session(item['rcept_dt'], sessions), affects_until=later[0] if later else None))
    return out


def verify(receipts, sessions, inventory=None, *, project_fn=project):
    receipts = [dict(r) for r in receipts]
    sessions = _calendar(sessions)
    scopes = {(r.get('company'), r.get('basis')) for r in receipts}
    if len(scopes) > 1:
        return dict(ok=False, checks=dict(single_scope=dict(ok=False, scopes=sorted(map(str, scopes)))), counts={}, unresolved=[], notice=NOTICE)
    full = project_fn(receipts, sessions);rows = full['rows']
    oracle, valid = _oracle(receipts, sessions, rows)
    checks = dict(single_scope=dict(ok=True), eligibility_oracle=oracle, correction_replay=_replay(receipts, sessions, rows, project_fn),
        order_independence=dict(ok=project_fn(list(reversed(receipts)), sessions) == full))
    counts = dict(rows=sum(1 for r in rows if not r.get('ambiguous')), ambiguous=sum(1 for r in rows if r.get('ambiguous')),
        blocked=dict(Counter(b['reason'] for b in full['blocked'])))
    unresolved = []
    if inventory:
        unresolved = _unresolved([dict(i) for i in inventory], {r['rcept_no'] for r in valid}, valid, sessions)
    return dict(ok=all(c['ok'] for c in checks.values()) and not unresolved, checks=checks, counts=counts, unresolved=unresolved, notice=NOTICE)
