"""Acceptance checks for a PIT projection (design: docs/review/design_PIT_collection_adapter_2026-11-03.md, criteria 2-7).

Pure functions over `pit_annual` receipts. `project_fn` is injectable so the checks themselves can be tested against deliberately
broken projections. A failed or skipped extraction of a known later receipt is reported as `unresolved`, because `pit_annual`
skips invalid receipts and the older value would otherwise stay selectable without any signal.
"""
from collections import Counter
from .core import select_vintage
from .pit_annual import project

NOTICE = '이 결과는 회사 단위 복원이며 시장 표본이 아니다(생존·폐지 기업 몇 곳의 접수번호 단위 재구성). 달력은 지수 관측일 기준이며 공식 휴장일 검증이 아니다.'
IDENTITY = ('company', 'period_end', 'basis')


def _identity(row):
    return tuple(row[k] for k in IDENTITY)


def _filing_day(rows):
    bad = []
    for row in rows:
        if row.get('ambiguous'):continue
        seen = select_vintage(rows, row['rcept_dt'])
        if any(r.get('rcept_no') == row['rcept_no'] for r in seen):bad.append(dict(rcept_no=row['rcept_no'], problem='visible_on_filing_day'))
        usable = [r for r in select_vintage(rows, row['available_at']) if _identity(r) == _identity(row)]
        chosen = usable[0] if usable else None   # this row, or a row of the same identity that legitimately supersedes it later
        if chosen is None or not (chosen['available_at'] > row['available_at'] or chosen.get('rcept_no') == row['rcept_no']):
            bad.append(dict(rcept_no=row['rcept_no'], problem='not_visible_when_usable'))
    return dict(ok=not bad, problems=bad)


def _replay(receipts, sessions, full_rows, project_fn):
    """At every cutoff, projecting only the receipts filed BEFORE it (by their real receipt dates) must give the same selection as projecting everything."""
    bad = []
    for cutoff in sorted({r['available_at'] for r in full_rows}):
        subset = [r for r in receipts if r['rcept_dt'] < cutoff]
        rows = project_fn(subset, sessions)['rows'] if subset else []
        if select_vintage(rows, cutoff) != select_vintage(full_rows, cutoff):bad.append(dict(cutoff=cutoff, problem='later_receipts_change_earlier_cutoff'))
    return dict(ok=not bad, problems=bad)


def verify(receipts, sessions, inventory=None, *, project_fn=project):
    receipts = [dict(r) for r in receipts]
    scopes = {(r.get('company'), r.get('basis')) for r in receipts}
    if len(scopes) > 1:
        return dict(ok=False, checks=dict(single_scope=dict(ok=False, scopes=sorted(map(str, scopes)))), counts={}, unresolved=[], notice=NOTICE)
    full = project_fn(receipts, sessions);rows = full['rows']
    checks = dict(single_scope=dict(ok=True), filing_day_exclusion=_filing_day(rows), correction_replay=_replay(receipts, sessions, rows, project_fn),
        order_independence=dict(ok=project_fn(list(reversed(receipts)), sessions) == full))
    counts = dict(rows=sum(1 for r in rows if not r.get('ambiguous')), ambiguous=sum(1 for r in rows if r.get('ambiguous')),
        blocked=dict(Counter(b['reason'] for b in full['blocked'])))
    unresolved = []
    if inventory:
        have = {r.get('rcept_no') for r in rows if 'rcept_no' in r} | {n for r in rows for n in r.get('rcept_nos', [])}
        latest = {}
        for item in inventory:
            key = item.get('title_period')
            if key is None:continue
            if key not in latest or (item['rcept_dt'], item['rcept_no']) > (latest[key]['rcept_dt'], latest[key]['rcept_no']):latest[key] = item
        unresolved = [dict(rcept_no=i['rcept_no'], rcept_dt=i['rcept_dt'], title_period=i['title_period'], problem='latest_receipt_without_usable_row')
            for i in sorted(latest.values(), key=lambda i: i['rcept_no']) if i['rcept_no'] not in have]
    return dict(ok=all(c['ok'] for c in checks.values()) and not unresolved, checks=checks, counts=counts, unresolved=unresolved, notice=NOTICE)
