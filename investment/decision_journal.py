"""Personal investment decision journal on the local Research Library DB.

Records are written before a buy/sell review and never rewritten. No orders, positions,
quantities, prices paid, balances or account data are accepted.
"""
from datetime import date, datetime, timezone, timedelta
import json
import math

from .research_library import day, fields, strings, text

REVIEW_TYPES = {'watch': '관찰', 'buy_review': '매수 검토', 'sell_review': '매도 검토'}
ASSESSMENTS = {'held': '가설 유지', 'refuted': '반증 발생', 'undecidable': '판단 불가'}
_DECISION = ('written_on', 'code', 'name', 'market', 'kind', 'review_type', 'hypothesis',
             'invalidation', 'source_ids', 'review_on')
_DECISION_OPTIONAL = ('score_snapshot', 'thesis_id', 'thesis_revision')
_REVIEW = ('decision_id', 'reviewed_on', 'outcome', 'assessment', 'reasoning')


def _iso(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError('ISO day required')
    return value


def _snapshot(value, limit_day):
    fields(value, ('as_of', 'model', 'values'))
    if day(value['as_of']) > limit_day: raise ValueError('Score snapshot must predate the record')
    text(value['model'], 200)
    values = value['values']
    if not isinstance(values, dict) or not 1 <= len(values) <= 30: raise ValueError('Score values required')
    for name, number in values.items():
        text(name, 100)
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number):
            raise ValueError('Numeric score values required')


def record(lib, key, value):
    """Store one immutable journal entry written before the review."""
    fields(value, _DECISION, _DECISION_OPTIONAL)
    written = day(value['written_on'])
    if _iso(value['review_on']) <= written: raise ValueError('Review date must follow the writing date')
    if not (isinstance(value['code'], str) and len(value['code']) == 6 and value['code'].isdigit()):
        raise ValueError('Domestic six-digit code required')
    if value['market'] not in ('KOSPI', 'KOSDAQ') or value['kind'] not in ('stock', 'etf'):
        raise ValueError('Domestic stock/listed ETF identity required')
    if value['review_type'] not in REVIEW_TYPES: raise ValueError('Known review type required')
    text(value['name'], 100); text(value['hypothesis']); strings(value['invalidation'])
    for sid in strings(value['source_ids']):
        if lib.get('source', sid)['accessed_on'] > written: raise ValueError('Source unavailable when written')
    if 'score_snapshot' in value: _snapshot(value['score_snapshot'], written)
    if 'thesis_id' in value or 'thesis_revision' in value:
        revisions = lib.history('thesis', text(value.get('thesis_id'), 100))
        revision = value.get('thesis_revision')
        if isinstance(revision, bool) or not isinstance(revision, int) or not 1 <= revision <= len(revisions):
            raise ValueError('Existing thesis revision required')
    if lib.history('decision', key): raise ValueError('Journal entries are immutable; add a review instead')
    return lib._put('decision', key, value, 0)


def review(lib, key, value):
    """Store one immutable after-the-fact review of an existing entry."""
    fields(value, _REVIEW, ('score_snapshot',))
    entry = lib.get('decision', text(value['decision_id'], 100))
    reviewed = day(value['reviewed_on'])
    if reviewed <= entry['written_on']: raise ValueError('Review must follow the journal entry')
    if value['assessment'] not in ASSESSMENTS: raise ValueError('Known assessment required')
    text(value['outcome']); text(value['reasoning'])
    if 'score_snapshot' in value: _snapshot(value['score_snapshot'], reviewed)
    if lib.history('decision_review', key): raise ValueError('Reviews are immutable; add a new review ID')
    return lib._put('decision_review', key, value, 0)


def due_from_rows(rows, today):
    """rows: (kind, id, payload) in revision order. Pure; usable on a read-only connection."""
    _iso(today)
    entries, reviewed = {}, {}
    for kind, key, payload in rows:
        value = json.loads(payload)
        if kind == 'decision': entries[key] = value
        elif kind == 'decision_review':
            last = reviewed.get(value['decision_id'], '')
            reviewed[value['decision_id']] = max(last, value['reviewed_on'])
    result = []
    for key, value in entries.items():
        if value['review_on'] > today or reviewed.get(key, '') >= value['review_on']: continue
        overdue = (date.fromisoformat(today) - date.fromisoformat(value['review_on'])).days
        result.append(dict(id=key, overdue_days=overdue, review_type_label=REVIEW_TYPES[value['review_type']], **value))
    result.sort(key=lambda r: (r['review_on'], r['id']))
    return result


def due(lib, today=None):
    today = today or datetime.now(timezone(timedelta(hours=9))).date().isoformat()
    with lib.connect() as db:
        rows = db.execute("SELECT kind,id,payload FROM records WHERE kind IN ('decision','decision_review') "
                          "ORDER BY revision").fetchall()
    return due_from_rows(rows, today)
