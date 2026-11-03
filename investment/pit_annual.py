"""Offline projection of dated annual-report receipts into research `annual` rows (design: docs/review/review_codex_PIT_path_2026-11-03.md).

Pure functions: no network, no files, nothing from the real data. Pilot scope: December year-end, one company and one
accounting basis (CFS or OFS) per `project()` call; `project_all()` partitions mixed input. Do not feed several companies
or bases into one research `annual` list: `select_vintage` and `continuous` do not check company or basis.

Rule: a receipt becomes usable on the first session of the SUPPLIED calendar strictly after its receipt date (`rcept_dt` is
date-only, so same-day use is never allowed). The caller must supply a validated exchange calendar; this module only checks
that the dates are canonical weekdays and that a session follows the receipt within `MAX_GAP_DAYS`, it cannot establish
holidays. This is a conservative eligibility rule, not an observed publication time.

Versions: each distinct receipt keeps its own row, so an earlier cutoff never sees a later correction. Receipts of the same
identity that become usable on the same session are collapsed when their values are identical and otherwise BLOCKED; a blocked
group emits a value-less `ambiguous` row on that session so the older original cannot silently stay selectable afterwards.
Rows are complete snapshots: values missing from a later receipt are not inherited. Missing values stay missing.
"""
from bisect import bisect_right
from datetime import date
from math import isfinite
import re

POLICY = 'next_session_after_rcept_dt_v1'
MAX_GAP_DAYS = 10
MAX_DATE_GAP_DAYS = 7      # rcept_dt may be later than the date inside the receipt number (seen in real data), never earlier
BASES = ('CFS', 'OFS')
IDENTITY = ('company', 'period_end', 'basis')
TOP_KEYS = frozenset(IDENTITY + ('report_kind', 'rcept_no', 'rcept_dt', 'values'))
NUMERIC = dict(revenue=(0, None), op=(None, None), ocf=(None, None), equity=(None, None), debt=(0, None), cash=(0, None),
               dps=(0, None), effective_tax_rate=(0, 1))
BOOLEAN = ('tax_verified',)
TEXT = ('dps_basis',)
SPECIAL = 'special_dividend'                      # bool or the literal 'unknown'
VALUE_FIELDS = tuple(NUMERIC) + BOOLEAN + TEXT + (SPECIAL,)


def _day(value):
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _calendar(sessions):
    days = list(sessions)
    if not days or not all(_day(d) for d in days) or any(date.fromisoformat(d).weekday() > 4 for d in days):
        raise ValueError('거래일 달력은 비어 있지 않은 ISO 평일 날짜 목록이어야 합니다')
    return sorted(set(days))


def _date_gap_ok(no, dt):
    """The receipt number's own date, then 0..MAX_DATE_GAP_DAYS days later: the later `rcept_dt` is the conservative date and drives eligibility."""
    try:number_day = date(int(no[:4]), int(no[4:6]), int(no[6:8]))
    except ValueError:return False
    return 0 <= (date.fromisoformat(dt) - number_day).days <= MAX_DATE_GAP_DAYS


def available_at(rcept_dt, sessions):
    """First session date strictly after `rcept_dt`, or None when the calendar ends first. `sessions` is sorted ISO dates."""
    i = bisect_right(sessions, rcept_dt)
    return sessions[i] if i < len(sessions) else None


def _number(v, low, high):
    if isinstance(v, bool) or not isinstance(v, (int, float)):return None
    try:
        x = float(v)
    except OverflowError:
        return None
    if not isfinite(x) or (low is not None and x < low) or (high is not None and x > high):return None
    return x


def _values(raw):
    """Validated, canonical (ints become floats) values, or None when anything is wrong or unknown."""
    if not isinstance(raw, dict) or not raw or set(raw) - set(VALUE_FIELDS):return None
    out = {}
    for key, v in raw.items():
        if v is None:continue
        if key in NUMERIC:
            x = _number(v, *NUMERIC[key])
            if x is None:return None
            out[key] = x
        elif key in BOOLEAN:
            if not isinstance(v, bool):return None
            out[key] = v
        elif key == SPECIAL:
            if not (isinstance(v, bool) or v == 'unknown'):return None
            out[key] = v
        elif not (isinstance(v, str) and v.strip()):return None
        else:out[key] = v
    return out or None


def _check(r, sessions):
    """(reason or None, available_at)."""
    if not isinstance(r, dict) or set(r) - TOP_KEYS:return 'unknown_field', None
    if r.get('report_kind') != 'annual':return 'not_annual', None
    no, dt = r.get('rcept_no'), r.get('rcept_dt')
    if not (isinstance(no, str) and re.fullmatch(r'\d{14}', no) and _day(dt)):return 'identity_format', None
    if not _date_gap_ok(no, dt):return 'identity', None
    period = r.get('period_end')
    if not _day(period):return 'bad_period', None
    if not (isinstance(r.get('company'), str) and re.fullmatch(r'[0-9A-Z]{6}', r['company'])):return 'bad_company', None
    if r.get('basis') not in BASES:return 'bad_basis', None
    if not period.endswith('-12-31'):return 'not_december', None
    if period >= dt:return 'period_after_receipt', None
    if _values(r.get('values')) is None:return 'bad_values', None
    when = available_at(dt, sessions)
    if not when or (date.fromisoformat(when) - date.fromisoformat(dt)).days > MAX_GAP_DAYS:return 'calendar_gap', None
    return None, when


def project(receipts, sessions):
    """-> dict(rows=[annual rows], blocked=[dict(rcept_no, reason)]). Raises ValueError for a bad calendar or mixed company/basis."""
    sessions = _calendar(sessions);receipts = list(receipts)
    scopes = {(r.get('company'), r.get('basis')) for r in receipts if isinstance(r, dict)}
    if len(scopes) > 1:raise ValueError('한 번에 한 회사·한 회계 기준만 투영할 수 있습니다(project_all 사용)')
    rows = [];blocked = []
    for r in receipts:
        reason, when = _check(r, sessions)
        if reason:
            blocked.append(dict(rcept_no=r.get('rcept_no') if isinstance(r, dict) else None, reason=reason));continue
        rows.append(dict({k: r[k] for k in IDENTITY}, available_at=when, rcept_no=r['rcept_no'], rcept_dt=r['rcept_dt'],
            policy=POLICY, **_values(r['values'])))
    groups = {}
    for row in rows:groups.setdefault(tuple(row[k] for k in IDENTITY) + (row['available_at'],), []).append(row)
    kept = []
    for key, group in groups.items():
        payloads = {tuple(sorted((k, v) for k, v in g.items() if k in VALUE_FIELDS)) for g in group}
        if len(payloads) == 1:
            kept.append(min(group, key=lambda g: g['rcept_no']))
        else:
            blocked += [dict(rcept_no=g['rcept_no'], reason='ambiguous_same_availability') for g in group]
            kept.append(dict(zip(IDENTITY, key[:3]), available_at=key[3], ambiguous=True, policy=POLICY,
                rcept_nos=sorted(g['rcept_no'] for g in group)))
    kept.sort(key=lambda g: (g['company'], g['period_end'], g['basis'], g['available_at'], g.get('rcept_no') or g['rcept_nos'][0]))
    blocked.sort(key=lambda b: (str(b['rcept_no']), b['reason']))
    return dict(rows=kept, blocked=blocked)


def project_all(receipts, sessions):
    """Partition by (company, basis) and project each separately: {(company, basis): project result}."""
    sessions = _calendar(sessions);parts = {}
    for r in receipts:
        parts.setdefault((r.get('company'), r.get('basis')) if isinstance(r, dict) else (None, None), []).append(r)
    return {key: project(group, sessions) for key, group in sorted(parts.items(), key=lambda kv: str(kv[0]))}
