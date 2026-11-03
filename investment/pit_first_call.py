"""The first live PIT step, as one small orchestrated run (plan: `pit_live.plan_first_call`; design: docs/review/design_PIT_collection_adapter_2026-11-03.md).

Order: (1) index calendar (KOSPI, KOSDAQ) through the same shared budget, (2) OpenDART corp-code zip, (3) the target company's annual
report list (at most 2 pages) and its latest ORIGINAL annual report document, (4) the delisted candidate's list (at most 2 pages) only if
its corp code is unique. Every response is stored as a hash-addressed artifact under `.local/pit-pilot/`. A quota signal, an exhausted budget
or any unexpected response ends the run at once, with what was collected kept and nothing retried. `client`, `store`, `budget` and
`calendar_fetch` are injected, so tests run on fakes; this module itself reads no key and prints nothing.
"""
import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from .pit_acquire import BudgetExceeded
from .pit_inventory import assemble, classify_title, parse_page
from .pit_live import QuotaStop, corp_candidates

TARGET = dict(name='효성중공업', stock_code='298040', bgn='20230101')
DELISTED = dict(name='도레이케미칼', bgn='20140101', end='20181231')
MAX_PAGES = 2


class ResponseRejected(ValueError):
    """A provider response that arrived fine but failed our validation (not a provider outage)."""


def _now():
    return datetime.now().astimezone().isoformat()


def _yyyymmdd(day):
    return day.replace('-', '')


def _collect(client, store, corp, bgn, end, stock_code, label, now, reused):
    """List pages for one company (at most MAX_PAGES), reusing a stored page instead of requesting it again. Returns dict(status, receipts, ...)."""
    pages = []
    page_no = 1
    pseudo, doc = '%014d' % int(corp['corp_code']), None
    while True:
        doc = f'list-{corp["corp_code"]}-{page_no}'
        stored = store.latest(pseudo, doc)
        if stored is not None:
            raw = json.loads(stored.decode('utf-8'));reused.append(doc)
        else:
            raw = client.list_page(corp['corp_code'], bgn, end, page_no)
            store.put(pseudo, doc, json.dumps(raw, ensure_ascii=False, sort_keys=True).encode(), observed_at=now, source_url='opendart:list.json')
        try:
            parsed = parse_page(raw, corp_code=corp['corp_code'], stock_code=stock_code)
        except ValueError as exc:
            raise ResponseRejected(f'{label} 목록 {page_no}쪽: {exc}') from exc
        pages.append(parsed)
        if parsed['total_page'] > MAX_PAGES:return dict(status='too_many_pages', receipts=[], excluded=[], uncertain=[], raw_count=parsed['total_count'])
        if page_no >= parsed['total_page']:break
        page_no += 1
    try:
        batch = assemble(pages, query=dict(corp_code=corp['corp_code'], bgn_de=bgn, end_de=end, label=label), collected_at=now)
    except ValueError as exc:
        raise ResponseRejected(f'{label} 목록 조립: {exc}') from exc
    return dict(status='listed', receipts=batch['receipts'], excluded=batch['excluded'], uncertain=batch['uncertain'], raw_count=batch['raw_count'])


def _latest_original_annual(receipts):
    cands = [r for r in receipts if r['correction'] == 'none' and (r['title_period'] or '').endswith('-12')]
    return max(cands, key=lambda r: (r['rcept_dt'], r['rcept_no'])) if cands else None


def run_first_call(*, client, store, budget, root, today, calendar_fetch):
    now = _now()
    summary = dict(status='completed', stop_reason=None, stop_detail=None, started_at=now, companies={}, calendar={}, requests_used=0, reused=[])
    out_dir = Path(root) / '.local/pit-pilot'
    out_dir.mkdir(parents=True, exist_ok=True)

    def finish():
        summary['requests_used'] = budget.count
        (out_dir / 'first-call-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
        return summary

    def stop(reason, detail=None):
        summary.update(status='stopped', stop_reason=reason, stop_detail=detail);return finish()

    yesterday = (datetime.fromisoformat(today) - timedelta(days=1)).date().isoformat()
    try:
        for symbol in ('KOSPI', 'KOSDAQ'):                                   # the calendar fetcher charges the budget itself, only when it really requests
            try:
                result = calendar_fetch(symbol, kind='index', start='2023-01-02', end=yesterday, cache_dir=out_dir / 'calendar')
            except (ValueError, OSError):
                return stop('calendar_failed')
            summary['calendar'][symbol] = dict(bars=len(result.get('prices', [])) if isinstance(result, dict) else None)
        zip_bytes = store.latest('00000000000000', 'corpcode-zip')
        if zip_bytes is None:
            zip_bytes = client.corp_code_zip()                                  # the real client charges the shared budget itself, once per request
        else:
            summary['reused'].append('corpcode-zip')
    except BudgetExceeded:
        return stop('budget')
    except QuotaStop:
        return stop('quota')
    except ValueError:
        return stop('provider_error')
    return _after_corp(client, store, budget, summary, zip_bytes, now, yesterday, finish, stop)


def _after_corp(client, store, budget, summary, zip_bytes, now, yesterday, finish, stop):
    try:
        if 'corpcode-zip' not in summary['reused']:store.put('00000000000000', 'corpcode-zip', zip_bytes, observed_at=now, source_url='opendart:corpCode.xml')
        end = _yyyymmdd(yesterday)
        plans = [(TARGET['name'], dict(stock_code=TARGET['stock_code']), TARGET['bgn'], end, TARGET['stock_code'], True),
                 (DELISTED['name'], dict(name=DELISTED['name']), DELISTED['bgn'], DELISTED['end'], None, False)]
        for label, query, bgn, stop_day, stock_code, want_document in plans:
            key = TARGET['stock_code'] if want_document else label
            candidates = corp_candidates(zip_bytes, **query)
            if len(candidates) != 1:
                summary['companies'][key] = dict(status='corp_code_not_unique', candidates=len(candidates));continue
            corp = candidates[0]
            result = _collect(client, store, corp, bgn, stop_day, stock_code if stock_code else (corp['stock_code'] or None), label, now, summary['reused'])
            entry = dict(status=result['status'], corp_code=corp['corp_code'], raw_count=result['raw_count'], document=None,
                receipts=[dict(rcept_no=r['rcept_no'], rcept_dt=r['rcept_dt'], report_nm=r['report_nm'], correction=r['correction'], title_period=r['title_period']) for r in result['receipts']],
                uncertain=[dict(rcept_no=u['rcept_no'], report_nm=u['report_nm']) for u in result['uncertain']])
            summary['companies'][key] = entry
            if want_document and result['status'] == 'listed':
                latest = _latest_original_annual(result['receipts'])
                if latest:
                    data = store.latest(latest['rcept_no'], 'document-zip')
                    if data is None:
                        data = client.document_zip(latest['rcept_no'])
                        artifact = store.put(latest['rcept_no'], 'document-zip', data, observed_at=now, source_url='opendart:document.xml')
                    else:
                        summary['reused'].append('document-zip');artifact = store.versions(latest['rcept_no'], 'document-zip')[-1]
                    entry['document'] = dict(rcept_no=latest['rcept_no'], sha256=artifact['sha256'], size=artifact['size'])
    except BudgetExceeded:
        return stop('budget')
    except QuotaStop:
        return stop('quota')
    except ResponseRejected as exc:
        return stop('response_rejected', str(exc))
    except ValueError as exc:
        return stop('provider_error', str(exc))
    return finish()


def run_delisted_list(*, client, store, budget, root, name, bgn, end):
    """Annual list for one exact name, using only the locally stored corp-code file."""
    now = _now()
    summary = dict(status='completed', stop_reason=None, stop_detail=None, name=name, corp_code=None, requests_used=0, reused=[],
        receipts=[], excluded=0, uncertain=[], fiscal_year_ends=[], december_only=False, consecutive_december_years=0)
    out_dir = Path(root) / '.local/pit-pilot'
    out_dir.mkdir(parents=True, exist_ok=True)

    def finish():
        summary['requests_used'] = budget.count
        (out_dir / ('delisted-' + re.sub(r'[\\/:*?"<>|\s]', '_', name) + '.json')).write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
        return summary

    def stop(reason, detail=None):
        summary.update(status='stopped', stop_reason=reason, stop_detail=detail);return finish()

    try:
        zip_bytes = store.latest('00000000000000', 'corpcode-zip')
        if zip_bytes is None:return stop('corp_code_file_missing')
        candidates = corp_candidates(zip_bytes, name=name)
        if len(candidates) != 1:return stop('corp_code_not_unique')
        corp = candidates[0];summary['corp_code'] = corp['corp_code']
        result = _collect(client, store, corp, _yyyymmdd(bgn), _yyyymmdd(end), corp['stock_code'] or None, name, now, summary['reused'])
        summary.update(status='too_many_pages' if result['status'] == 'too_many_pages' else 'completed',
            receipts=[dict(rcept_no=r['rcept_no'], rcept_dt=r['rcept_dt'], report_nm=r['report_nm'], correction=r['correction'], title_period=r['title_period']) for r in result['receipts']],
            excluded=len(result['excluded']), uncertain=[dict(rcept_no=r['rcept_no'], report_nm=r['report_nm']) for r in result['uncertain']])
        periods = sorted({r['title_period'] for r in result['receipts'] if r['title_period']})
        summary['fiscal_year_ends'] = periods
        summary['december_only'] = bool(periods) and all(p.endswith('-12') for p in periods)
        years = sorted({int(p[:4]) for p in periods if p.endswith('-12')})
        longest, run, previous = 0, 0, None
        for year in years:
            run = run + 1 if previous is not None and year == previous + 1 else 1
            longest = max(longest, run);previous = year
        summary['consecutive_december_years'] = longest
    except BudgetExceeded:
        return stop('budget')
    except QuotaStop:
        return stop('quota')
    except ResponseRejected as exc:
        return stop('response_rejected', str(exc))
    except ValueError as exc:
        return stop('provider_error', str(exc))
    return finish()


def _listed_annual_original(store, rcept_no):
    """True when a stored list page reports this receipt as an original (uncorrected) December annual report."""
    for entry in store.entries():
        if not entry['document_id'].startswith('list-') or not entry.get('sha256') or entry['status'] == 'resolved':continue
        try:raw = json.loads(store.read(entry).decode('utf-8'))
        except (ValueError, OSError):continue
        for item in raw.get('list', []) if isinstance(raw, dict) else []:
            if isinstance(item, dict) and item.get('rcept_no') == rcept_no:
                kind = classify_title(item.get('report_nm'))
                return kind['kind'] == 'annual' and kind['correction'] == 'none' and (kind['title_period'] or '').endswith('-12')
    return False


def run_fetch_document(*, client, store, budget, rcept_no):
    """Fetch ONE original annual report document (at most one request); only receipts a stored list page reports are allowed."""
    if not (isinstance(rcept_no, str) and re.fullmatch(r'\d{14}', rcept_no)):raise ValueError('접수번호 형식 오류')
    summary = dict(status='completed', stop_reason=None, rcept_no=rcept_no, sha256=None, size=None, reused=False, requests_used=0)

    def finish(reason=None):
        summary['requests_used'] = budget.count
        if reason:summary.update(status='stopped', stop_reason=reason)
        return summary

    if not _listed_annual_original(store, rcept_no):return finish('not_a_listed_annual_original')
    try:
        data = store.latest(rcept_no, 'document-zip')
        summary['reused'] = data is not None
        if data is None:
            data = client.document_zip(rcept_no)
            store.put(rcept_no, 'document-zip', data, observed_at=_now(), source_url='opendart:document.xml')
        summary.update(sha256=hashlib.sha256(data).hexdigest(), size=len(data))
    except BudgetExceeded:
        return finish('budget')
    except QuotaStop:
        return finish('quota')
    except ValueError:
        return finish('provider_error')
    return finish()
