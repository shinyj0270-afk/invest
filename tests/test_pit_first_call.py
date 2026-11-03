import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from investment.pit_acquire import Budget
from investment.pit_artifacts import ArtifactStore
from investment.pit_first_call import run_first_call
from investment.pit_live import QuotaStop
from tests.test_pit_live import corp_zip

TODAY = '2026-11-04'
ROWS = [('00555555', '효성중공업', '298040'), ('00777777', '도레이케미칼', '')]


def doc_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:z.writestr('a.xml', '<x/>')
    return buffer.getvalue()


def list_json(corp, stock, rows, page=1, total_page=1, total=None, count=100):
    return dict(status='000' if rows else '013', page_no=page, page_count=count, total_count=len(rows) if total is None else total, total_page=total_page,
        list=[dict(corp_code=corp, corp_name='x', stock_code=stock, corp_cls='Y', report_nm=name, rcept_no=no, flr_nm='x', rcept_dt=no[:8], rm='') for no, name in rows])


class FakeClient:
    def __init__(self, corp=None, lists=None, quota_at=None, doc=None, budget=None):
        self.corp, self.lists, self.quota_at, self.doc, self.calls, self.budget = corp or corp_zip(ROWS), lists or {}, quota_at, doc or doc_zip(), [], budget
    def _tick(self, name):
        if self.budget:self.budget.spend()                    # like the real client: one charge per request, before the request
        self.calls.append(name)
        if self.quota_at == len(self.calls):raise QuotaStop('020')
    def corp_code_zip(self):
        self._tick('corp');return self.corp
    def list_page(self, corp_code, bgn_de, end_de, page_no, page_count=100):
        self._tick(f'list:{corp_code}:{page_no}');return self.lists[(corp_code, page_no)]
    def document_zip(self, rcept_no):
        self._tick(f'doc:{rcept_no}');return self.doc


def budget():
    return Budget(max_requests=12, min_interval=0.0, clock=lambda: 0.0, sleep=lambda s: None)


def calendar_fetch(symbol, **kw):
    return dict(symbol=symbol, prices=[dict(date='2026-11-03')])


HY = [('20260310000001', '사업보고서 (2025.12)'), ('20260520000002', '[기재정정]사업보고서 (2025.12)'), ('20250814000003', '반기보고서 (2025.06)')]
TL = [('20170314000009', '사업보고서 (2016.12)')]


class FirstCallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root = Path(self.tmp.name)

    def run_it(self, client, **kw):
        store = ArtifactStore(self.root / '.local/pit-pilot/artifacts');shared = kw.pop('budget', None) or budget();client.budget = shared
        return run_first_call(client=client, store=store, budget=shared, root=self.root, today=TODAY,
            calendar_fetch=self.charging(shared, kw.pop('calendar_fetch', calendar_fetch)), **kw), store

    @staticmethod
    def charging(shared, fetch):
        def wrapped(symbol, **kw):
            shared.spend();return fetch(symbol, **kw)            # like the CLI's budgeted session: charged only when a request really happens
        return wrapped

    def fresh_root(self):
        self.tmp2 = tempfile.TemporaryDirectory();self.addCleanup(self.tmp2.cleanup);self.root = Path(self.tmp2.name)

    def lists(self):
        return {('00555555', 1): list_json('00555555', '298040', HY), ('00777777', 1): list_json('00777777', '', TL)}

    def test_the_happy_path_makes_exactly_the_planned_requests_and_stores_everything_locally(self):
        client = FakeClient(lists=self.lists());summary, store = self.run_it(client)
        self.assertEqual(client.calls, ['corp', 'list:00555555:1', 'doc:20260310000001', 'list:00777777:1'])           # latest ORIGINAL annual report is downloaded
        self.assertEqual(summary['status'], 'completed');self.assertEqual(summary['requests_used'], 6)                  # 2 calendar + 4 OpenDART
        self.assertEqual([r['rcept_no'] for r in summary['companies']['298040']['receipts']], ['20260310000001', '20260520000002'])
        self.assertEqual(summary['companies']['도레이케미칼']['status'], 'listed');self.assertEqual(store.verify(), [])
        self.assertTrue({e['document_id'] for e in store.entries()} >= {'corpcode-zip', 'list-00555555-1', 'document-zip'})
        self.assertTrue((self.root / '.local/pit-pilot/first-call-summary.json').exists())

    def test_a_quota_signal_stops_the_run_at_once_and_keeps_what_was_collected(self):
        client = FakeClient(lists=self.lists(), quota_at=2);summary, store = self.run_it(client)                          # 020 on the first list page
        self.assertEqual((summary['status'], summary['stop_reason']), ('stopped', 'quota'));self.assertEqual(client.calls, ['corp', 'list:00555555:1'])
        self.assertIn('corpcode-zip', {e['document_id'] for e in store.entries()})

    def test_a_quota_signal_on_the_very_first_provider_request_also_stops_cleanly(self):
        client = FakeClient(lists=self.lists(), quota_at=1);summary, store = self.run_it(client)
        self.assertEqual((summary['status'], summary['stop_reason'], client.calls), ('stopped', 'quota', ['corp']));self.assertEqual(store.entries(), [])

    def test_an_ambiguous_or_missing_corp_code_is_never_guessed(self):
        client = FakeClient(corp=corp_zip(ROWS + [('00888888', '도레이케미칼', '')]), lists=self.lists());summary, _ = self.run_it(client)
        self.assertEqual(summary['companies']['도레이케미칼']['status'], 'corp_code_not_unique');self.assertNotIn('list:00777777:1', client.calls)
        self.fresh_root();client = FakeClient(corp=corp_zip([ROWS[1]]), lists=self.lists());summary, _ = self.run_it(client)
        self.assertEqual(summary['companies']['298040']['status'], 'corp_code_not_unique');self.assertEqual(client.calls, ['corp', 'list:00777777:1'])

    def test_more_pages_than_the_plan_allows_stop_that_company_without_extra_requests(self):
        lists = self.lists();lists[('00555555', 1)] = list_json('00555555', '298040', [HY[0]] * 100, total=250, total_page=3, count=100)
        client = FakeClient(lists=lists);summary, _ = self.run_it(client)
        self.assertEqual(summary['companies']['298040']['status'], 'too_many_pages');self.assertNotIn('doc:20260310000001', client.calls)

    def test_a_failure_in_the_calendar_stops_before_any_opendart_request(self):
        def boom(symbol, **kw):raise ValueError('calendar down')
        client = FakeClient(lists=self.lists());summary, _ = self.run_it(client, calendar_fetch=boom)
        self.assertEqual((summary['status'], summary['stop_reason']), ('stopped', 'calendar_failed'));self.assertEqual(client.calls, [])

    def test_the_summary_never_contains_a_key_like_string_and_requests_never_exceed_the_cap(self):
        tight = Budget(max_requests=3, min_interval=0.0, clock=lambda: 0.0, sleep=lambda s: None)
        client = FakeClient(lists=self.lists());summary, _ = self.run_it(client, budget=tight)
        self.assertEqual(summary['status'], 'stopped');self.assertEqual(summary['stop_reason'], 'budget');self.assertLessEqual(summary['requests_used'], 3)
        self.assertNotIn('crtfc_key', json.dumps(summary))

    def test_no_annual_original_means_no_document_request(self):
        lists = self.lists();lists[('00555555', 1)] = list_json('00555555', '298040', [HY[1], HY[2]])                       # only a correction and a half-year report
        client = FakeClient(lists=lists);summary, _ = self.run_it(client)
        self.assertNotIn('doc:20260520000002', client.calls);self.assertEqual(summary['companies']['298040']['document'], None)

    def test_a_rerun_reuses_stored_artifacts_and_only_requests_what_is_missing(self):
        first = FakeClient(lists=self.lists(), quota_at=3)                                                              # stops at the document request
        summary, store = self.run_it(first);self.assertEqual(summary['stop_reason'], 'quota');self.assertEqual(first.calls, ['corp', 'list:00555555:1', 'doc:20260310000001'])
        second = FakeClient(lists=self.lists());summary, _ = self.run_it(second)
        self.assertEqual(second.calls, ['doc:20260310000001', 'list:00777777:1'])                                       # corp zip and the first list page come from the store
        self.assertEqual(summary['status'], 'completed');self.assertEqual(set(summary['reused']), {'corpcode-zip', 'list-00555555-1'})
        self.assertEqual(summary['requests_used'], 2 + 2)                                                               # calendar is charged by the fake fetcher each run

    def test_a_response_that_fails_our_validation_is_labelled_as_rejected_not_as_a_provider_error(self):
        lists = self.lists();lists[('00555555', 1)] = list_json('00555555', '999999', HY)                              # wrong stock code
        client = FakeClient(lists=lists);summary, _ = self.run_it(client)
        self.assertEqual((summary['status'], summary['stop_reason']), ('stopped', 'response_rejected'));self.assertIn('종목코드', summary['stop_detail'])
        self.assertEqual(client.calls, ['corp', 'list:00555555:1'])

    def test_the_real_data_date_gap_row_is_accepted_end_to_end(self):
        rows = HY + [('20230308000776', '사업보고서 (2022.12)')]
        page = list_json('00555555', '298040', rows);page['list'][-1]['rcept_dt'] = '20230309'
        lists = self.lists();lists[('00555555', 1)] = page
        client = FakeClient(lists=lists);summary, _ = self.run_it(client)
        self.assertEqual(summary['status'], 'completed');self.assertIn('20230308000776', [r['rcept_no'] for r in summary['companies']['298040']['receipts']])

    def test_a_completed_run_can_be_repeated_without_any_provider_request(self):
        self.run_it(FakeClient(lists=self.lists()))
        again = FakeClient(lists=self.lists());summary, _ = self.run_it(again)
        self.assertEqual(again.calls, []);self.assertEqual(summary['status'], 'completed')
        self.assertEqual(set(summary['reused']), {'corpcode-zip', 'list-00555555-1', 'document-zip', 'list-00777777-1'})


if __name__ == '__main__':unittest.main()
