"""New listings join discovery five months after the official listing date (user decision 2026-10-15).

The official date comes from the public FnGuide company overview linked from Npay.
Companies whose saved price history already starts at the history window start were
listed before that window, so only short or missing histories need the official date.
"""
import calendar
from copy import deepcopy
from datetime import date, datetime
import json
from pathlib import Path
import re
import time

from .naver_universe import WISE, _code, _get, _now, _session

SEASONING_MONTHS = 5
SCHEMA = 'listing-dates-1'
FILE = 'listing-dates.json'
SOURCE = 'FnGuide 기업개요 (Npay 증권 연결)'


def add_months(day, months):
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def parse_listing_date(html):
    match = re.search(r'상장일:\s*(\d{4})/(\d{2})/(\d{2})', html)
    if not match:
        return None
    try:
        return date(*map(int, match.groups()))
    except ValueError:
        return None


def overview_url(code):
    return WISE + '/v2/company/c1020001.aspx?cmp_cd=' + _code(code)


def fetch_listing_date(code, session=None):
    session, owned = _session(session)
    try:
        url = overview_url(code)
        listed = parse_listing_date(_get(session, url, html=True, headers={'User-Agent': 'Mozilla/5.0'}))
        if listed is None:
            raise ValueError('상장일 표기 없음')
        return dict(listed_on=listed.isoformat(), source=SOURCE, url=url, retrieved_at=_now())
    finally:
        if owned:
            session.close()


def read_listing_dates(folder):
    path = Path(folder)/FILE
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('schema_version') != SCHEMA or not isinstance(value.get('companies'), dict):
        raise ValueError('상장일 캐시 형식 오류')
    for code, item in value['companies'].items():
        _code(code)
        date.fromisoformat(item['listed_on'])
    return value['companies']


def _first_session(history):
    sessions = (history or {}).get('calendar', {}).get('sessions') or []
    return sessions[0] if sessions else None


def codes_needing_dates(rows, history, known):
    """Candidates whose saved history cannot prove a listing before the window start."""
    first = _first_session(history)
    histories = (history or {}).get('histories', {})
    result = []
    for row in rows:
        if row.get('eligibility') != 'candidate' or row['code'] in known:
            continue
        prices = histories.get(row['code'], {}).get('prices') or []
        if first is None or not prices or prices[0].get('date') != first:
            result.append(row['code'])
    return result


def collect_listing_dates(folder, codes, *, fetch=fetch_listing_date, pace=.3):
    """Explicit collection of missing official dates; cached dates never change."""
    folder = Path(folder)
    known = dict(read_listing_dates(folder))
    collected, failures = 0, []
    for code in codes:
        if code in known:
            continue
        try:
            known[code] = fetch(code)
            collected += 1
        except Exception as exc:
            failures.append(dict(code=code, reason=type(exc).__name__))
        time.sleep(pace)
    path = folder/FILE
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(dict(schema_version=SCHEMA, updated_at=_now(), companies=known),
                               ensure_ascii=False), encoding='utf-8')
    temp.replace(path)
    return dict(collected=collected, failed=len(failures), failures=failures, known=len(known))


def apply_seasoning(rows, dates, history, as_of):
    """Return copies; candidates younger than five months or with an unproven date are excluded."""
    first = _first_session(history)
    if first is None:
        return rows
    histories = history.get('histories', {})
    result = []
    for row in rows:
        if row.get('eligibility') != 'candidate':
            result.append(row)
            continue
        official = dates.get(row['code'])
        prices = histories.get(row['code'], {}).get('prices') or []
        if official:
            listed = date.fromisoformat(official['listed_on'])
            eligible = add_months(listed, SEASONING_MONTHS)
            if as_of >= eligible:
                result.append(row)
                continue
            reason = f'신규 상장 {SEASONING_MONTHS}개월 미경과 · 상장 {listed} · 편입 가능 {eligible}'
            seasoning = dict(status='seasoning', listed_on=listed.isoformat(), eligible_on=eligible.isoformat())
        elif prices and prices[0].get('date') == first:
            result.append(row)
            continue
        else:
            reason = '신규 상장 여부 확인 대기 · 공식 상장일 미확보'
            seasoning = dict(status='listing_date_pending')
        updated = deepcopy(row)
        updated.update(eligibility='excluded', seasoning=seasoning,
                       exclusion_reasons=list(row.get('exclusion_reasons') or []) + [reason])
        result.append(updated)
    return result


def today_kst():
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo('Asia/Seoul')).date()
