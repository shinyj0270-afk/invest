"""The first live PIT step, as one small orchestrated run (plan: `pit_live.plan_first_call`; design: docs/review/design_PIT_collection_adapter_2026-11-03.md).

Order: (1) index calendar (KOSPI, KOSDAQ) through the same shared budget, (2) OpenDART corp-code zip, (3) the target company's annual
report list (at most 2 pages) and its latest ORIGINAL annual report document, (4) the delisted candidate's list (at most 2 pages) only if
its corp code is unique. Every response is stored as a hash-addressed artifact under `.local/pit-pilot/`. A quota signal, an exhausted budget
or any unexpected response ends the run at once, with what was collected kept and nothing retried. `client`, `store`, `budget` and
`calendar_fetch` are injected, so tests run on fakes; this module itself reads no key and prints nothing.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from .pit_acquire import BudgetExceeded
from .pit_inventory import assemble, parse_page
from .pit_live import QuotaStop, corp_candidates

TARGET = dict(name='효성중공업', stock_code='298040', bgn='20230101')
DELISTED = dict(name='도레이케미칼', bgn='20140101', end='20181231')
MAX_PAGES = 2


def _now():
    return datetime.now().astimezone().isoformat()


def _yyyymmdd(day):
    return day.replace('-', '')


def _collect(client, store, corp, bgn, end, stock_code, label, now):
    """List pages for one company (at most MAX_PAGES). Returns dict(status, receipts, excluded, uncertain, raw_count)."""
    pages = []
    page_no = 1
    while True:
        raw = client.list_page(corp['corp_code'], bgn, end, page_no)
        store.put(('%014d' % int(corp['corp_code'])), f'list-{corp["corp_code"]}-{page_no}', json.dumps(raw, ensure_ascii=False, sort_keys=True).encode(), observed_at=now, source_url='opendart:list.json')
        parsed = parse_page(raw, corp_code=corp['corp_code'], stock_code=stock_code)
        pages.append(parsed)
        if parsed['total_page'] > MAX_PAGES:return dict(status='too_many_pages', receipts=[], excluded=[], uncertain=[], raw_count=parsed['total_count'])
        if page_no >= parsed['total_page']:break
        page_no += 1
    batch = assemble(pages, query=dict(corp_code=corp['corp_code'], bgn_de=bgn, end_de=end, label=label), collected_at=now)
    return dict(status='listed', receipts=batch['receipts'], excluded=batch['excluded'], uncertain=batch['uncertain'], raw_count=batch['raw_count'])


def _latest_original_annual(receipts):
    cands = [r for r in receipts if r['correction'] == 'none' and (r['title_period'] or '').endswith('-12')]
    return max(cands, key=lambda r: (r['rcept_dt'], r['rcept_no'])) if cands else None


def run_first_call(*, client, store, budget, root, today, calendar_fetch):
    now = _now()
    summary = dict(status='completed', stop_reason=None, started_at=now, companies={}, calendar={}, requests_used=0)
    out_dir = Path(root) / '.local/pit-pilot'
    out_dir.mkdir(parents=True, exist_ok=True)

    def finish():
        summary['requests_used'] = budget.count
        (out_dir / 'first-call-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
        return summary

    def stop(reason):
        summary.update(status='stopped', stop_reason=reason);return finish()

    yesterday = (datetime.fromisoformat(today) - timedelta(days=1)).date().isoformat()
    try:
        for symbol in ('KOSPI', 'KOSDAQ'):
            budget.spend()
            try:
                result = calendar_fetch(symbol, kind='index', start='2023-01-02', end=yesterday, cache_dir=out_dir / 'calendar')
            except (ValueError, OSError):
                return stop('calendar_failed')
            summary['calendar'][symbol] = dict(bars=len(result.get('prices', [])) if isinstance(result, dict) else None)
        zip_bytes = client.corp_code_zip()                                      # the real client charges the shared budget itself, once per request
    except BudgetExceeded:
        return stop('budget')
    except QuotaStop:
        return stop('quota')
    except ValueError:
        return stop('provider_error')
    return _after_corp(client, store, budget, summary, zip_bytes, now, yesterday, finish, stop)


def _after_corp(client, store, budget, summary, zip_bytes, now, yesterday, finish, stop):
    try:
        store.put('00000000000000', 'corpcode-zip', zip_bytes, observed_at=now, source_url='opendart:corpCode.xml')
        end = _yyyymmdd(yesterday)
        plans = [(TARGET['name'], dict(stock_code=TARGET['stock_code']), TARGET['bgn'], end, TARGET['stock_code'], True),
                 (DELISTED['name'], dict(name=DELISTED['name']), DELISTED['bgn'], DELISTED['end'], None, False)]
        for label, query, bgn, stop_day, stock_code, want_document in plans:
            key = TARGET['stock_code'] if want_document else label
            candidates = corp_candidates(zip_bytes, **query)
            if len(candidates) != 1:
                summary['companies'][key] = dict(status='corp_code_not_unique', candidates=len(candidates));continue
            corp = candidates[0]
            result = _collect(client, store, corp, bgn, stop_day, stock_code if stock_code else (corp['stock_code'] or None), label, now)
            entry = dict(status=result['status'], corp_code=corp['corp_code'], raw_count=result['raw_count'], document=None,
                receipts=[dict(rcept_no=r['rcept_no'], rcept_dt=r['rcept_dt'], report_nm=r['report_nm'], correction=r['correction'], title_period=r['title_period']) for r in result['receipts']],
                uncertain=[dict(rcept_no=u['rcept_no'], report_nm=u['report_nm']) for u in result['uncertain']])
            summary['companies'][key] = entry
            if want_document and result['status'] == 'listed':
                latest = _latest_original_annual(result['receipts'])
                if latest:
                    data = client.document_zip(latest['rcept_no'])
                    artifact = store.put(latest['rcept_no'], 'document-zip', data, observed_at=now, source_url='opendart:document.xml')
                    entry['document'] = dict(rcept_no=latest['rcept_no'], sha256=artifact['sha256'], size=artifact['size'])
    except BudgetExceeded:
        return stop('budget')
    except QuotaStop:
        return stop('quota')
    except ValueError:
        return stop('provider_error')
    return finish()
