"""Receipt inventory for the PIT pilot: parse OpenDART `list.json` pages and assemble a validated batch (design: docs/review/design_PIT_collection_adapter_2026-11-03.md).

Pure functions, no network. The response layout (`status`, `page_no`, `page_count`, `total_count`, `total_page`, `list[...]` with
`corp_code`, `stock_code`, `report_nm`, `rcept_no`, `rcept_dt`) follows the public API guide as documented in the design; it is
PROVISIONAL until a real response is checked at the first live call. Raw titles are always kept. Count and page checks use the RAW
rows, before any filtering, so a missing page cannot hide behind the filter. A title that mentions an annual report but does not
match the strict grammar is NOT dropped: it is listed as `uncertain` for review and counts as unresolved downstream.
"""
from datetime import date
import re

NO_DATA = '013'
OK = '000'
PREFIXES = ('기재정정', '첨부정정', '첨부추가')
TITLE = re.compile(r'^(?:\[(?P<prefix>[^\]]+)\]\s*)?(?P<name>사업보고서|반기보고서|분기보고서)\s*(?:\((?P<year>\d{4})\.(?P<month>\d{2})\))?$')
KINDS = {'사업보고서': 'annual', '반기보고서': 'half', '분기보고서': 'quarter'}


def classify_title(title):
    """kind (annual/half/quarter/other/uncertain), correction prefix (none / one of PREFIXES / 'unknown_prefix') and the title's period hint."""
    text = title.strip() if isinstance(title, str) else ''
    m = TITLE.match(text)
    if not m:
        return dict(kind='uncertain' if '사업보고서' in text else 'other', correction='none', title_period=None)
    prefix = m['prefix']
    correction = 'none' if prefix is None else prefix if prefix in PREFIXES else 'unknown_prefix'
    month_ok = m['month'] is None or 1 <= int(m['month']) <= 12
    period = f"{m['year']}-{m['month']}" if m['year'] and month_ok else None
    kind = KINDS[m['name']]
    if correction == 'unknown_prefix' or (m['year'] and not month_ok):kind = 'uncertain' if kind == 'annual' else 'other'
    return dict(kind=kind, correction=correction, title_period=period)


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _row(raw, corp_code, stock_code):
    if not isinstance(raw, dict):raise ValueError('목록 행 형식 오류')
    no, dt, title = raw.get('rcept_no'), raw.get('rcept_dt'), raw.get('report_nm')
    if not (isinstance(no, str) and re.fullmatch(r'\d{14}', no)):raise ValueError('접수번호 형식 오류')
    if not (isinstance(dt, str) and re.fullmatch(r'\d{8}', dt)) or dt != no[:8]:raise ValueError('접수일과 접수번호 불일치')
    try:iso = date(int(dt[:4]), int(dt[4:6]), int(dt[6:])).isoformat()
    except ValueError as exc:raise ValueError('접수일 형식 오류') from exc
    if raw.get('corp_code') != corp_code:raise ValueError('법인코드 불일치')
    if (raw.get('stock_code') or '') != (stock_code or ''):raise ValueError('종목코드 불일치')
    if not isinstance(title, str) or not title.strip():raise ValueError('보고서명 누락')
    return dict(rcept_no=no, rcept_dt=iso, report_nm=title, corp_code=corp_code, stock_code=stock_code or '', **classify_title(title))


def parse_page(page, *, corp_code, stock_code):
    """One response page -> dict(page_no, total_count, total_page, rows). `stock_code=None` expects a blank (delisted) code."""
    if not isinstance(page, dict) or not isinstance(page.get('status'), str):raise ValueError('응답 형식 오류')
    if page['status'] == NO_DATA:
        if page.get('list') or page.get('total_count') not in (None, 0):raise ValueError('자료 없음 응답이 자료를 담고 있습니다')
        return dict(page_no=_int(page.get('page_no')) or 1, total_count=0, total_page=1, rows=[])
    if page['status'] != OK:raise ValueError('OpenDART 응답 오류 ' + page['status'])
    number, total, pages, rows = _int(page.get('page_no')), _int(page.get('total_count')), _int(page.get('total_page')), page.get('list')
    if not number or number < 1 or total is None or total < 0 or not pages or pages < 1 or not isinstance(rows, list):raise ValueError('쪽 정보 오류')
    size = page.get('page_count')
    if size is not None:
        size = _int(size)
        if not size or size < 1:raise ValueError('쪽 크기 오류')
        if total and pages != -(-total // size):raise ValueError('total_page가 total_count와 쪽 크기에 맞지 않습니다')
        expected = size if number < pages else total - size * (pages - 1)
        if number <= pages and len(rows) != expected:raise ValueError('쪽의 행 수가 쪽 크기와 맞지 않습니다')
    return dict(page_no=number, total_count=total, total_page=pages, rows=[_row(r, corp_code, stock_code) for r in rows])


def assemble(pages, *, query, collected_at):
    """Validate a complete set of pages and select annual reports (corrections included, raw titles kept, doubtful titles listed as uncertain)."""
    pages = sorted(pages, key=lambda p: p['page_no'])
    if not pages:raise ValueError('쪽이 없습니다')
    totals = {(p['total_count'], p['total_page']) for p in pages}
    if len(totals) != 1:raise ValueError('쪽마다 합계가 다릅니다')
    total, last = totals.pop()
    if [p['page_no'] for p in pages] != list(range(1, last + 1)):raise ValueError('누락·중복된 쪽이 있습니다')
    rows = [r for p in pages for r in p['rows']]
    if len(rows) != total:raise ValueError('원본 행 수와 total_count가 다릅니다')
    numbers = [r['rcept_no'] for r in rows]
    if len(set(numbers)) != len(numbers):raise ValueError('접수번호 중복')
    keep = sorted((r for r in rows if r['kind'] == 'annual'), key=lambda r: (r['rcept_dt'], r['rcept_no']))
    skipped = sorted((dict(rcept_no=r['rcept_no'], reason='not_annual', report_nm=r['report_nm']) for r in rows if r['kind'] in ('half', 'quarter', 'other')), key=lambda r: r['rcept_no'])
    uncertain = sorted((dict(rcept_no=r['rcept_no'], rcept_dt=r['rcept_dt'], reason='uncertain_title', report_nm=r['report_nm'], title_period=None, kind='uncertain')
        for r in rows if r['kind'] == 'uncertain'), key=lambda r: r['rcept_no'])
    return dict(receipts=[dict(r) for r in keep], excluded=skipped, uncertain=uncertain, raw_count=total, query=dict(query), collected_at=collected_at)
