import json
import tempfile
import unittest
from pathlib import Path
from investment.pit_acquire import Budget
from investment.pit_artifacts import ArtifactStore
from investment.pit_first_call import run_fetch_document
from tests.test_pit_first_call import FakeClient, list_json

LISTED = [('20240314001093', '사업보고서 (2023.12)'), ('20240801000002', '[기재정정]사업보고서 (2023.12)'), ('20240515000003', '분기보고서 (2024.03)'),
          ('20230316000692', '사업보고서 (2022.12)')]


def budget(n=1):
    return Budget(max_requests=n, min_interval=0.0, clock=lambda: 0.0, sleep=lambda s: None)


class FetchDocumentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store = ArtifactStore(Path(self.tmp.name) / 'a')
        self.store.put('00000000000000', 'corpcode-zip', b'PKx', observed_at='2026-11-04T09:00:00+09:00', source_url='u')
        raw = list_json('01262458', '282690', LISTED)
        self.store.put('01262458'.zfill(14), 'list-01262458-1', json.dumps(raw, ensure_ascii=False, sort_keys=True).encode(), observed_at='2026-11-04T09:00:00+09:00', source_url='u')

    def run_it(self, rcept_no, client=None, shared=None):
        shared = shared or budget();client = client or FakeClient();client.budget = shared
        return client, run_fetch_document(client=client, store=self.store, budget=shared, rcept_no=rcept_no)

    def test_a_listed_original_annual_report_is_fetched_once_and_stored_with_its_hash(self):
        client, summary = self.run_it('20240314001093')
        self.assertEqual(client.calls, ['doc:20240314001093']);self.assertEqual((summary['status'], summary['stop_reason'], summary['reused']), ('completed', None, False))
        stored = self.store.latest('20240314001093', 'document-zip');self.assertEqual(stored, client.doc)
        self.assertEqual(summary['size'], len(client.doc));self.assertEqual(summary['requests_used'], 1)
        self.assertEqual(len(summary['sha256']), 64)

    def test_a_second_run_reuses_the_stored_document_without_a_request(self):
        self.run_it('20240314001093');client, summary = self.run_it('20240314001093')
        self.assertEqual((client.calls, summary['reused'], summary['requests_used']), ([], True, 0))

    def test_only_listed_original_annual_reports_are_allowed_and_nothing_is_requested_otherwise(self):
        for number in ('20240801000002', '20240515000003', '20991231000001'):             # correction, quarterly report, never listed
            with self.subTest(number=number):
                client, summary = self.run_it(number)
                self.assertEqual((summary['status'], summary['stop_reason'], client.calls), ('stopped', 'not_a_listed_annual_original', []))

    def test_the_list_rule_checks_kind_period_and_the_source_of_the_listing(self):
        put = lambda doc_id, items, code='99999999': self.store.put(code.zfill(14), doc_id, json.dumps(list_json(code, '000000', items), ensure_ascii=False).encode(),
                                                                       observed_at='2026-11-04T09:00:00+09:00', source_url='u')
        put('list-99999999-1', [('20240101000001', '반기보고서 (2023.12)'), ('20240101000002', '사업보고서 (2023.03)')])
        put('notes-99999999', [('20240101000003', '사업보고서 (2023.12)')])                  # not a list page: never trusted
        for number in ('20240101000001', '20240101000002', '20240101000003'):
            with self.subTest(number=number):
                client, summary = self.run_it(number);self.assertEqual((summary['stop_reason'], client.calls), ('not_a_listed_annual_original', []))

    def test_a_damaged_list_artifact_is_skipped_not_fatal(self):
        fresh = ArtifactStore(Path(self.tmp.name) / 'b')                                    # the damaged page comes FIRST in this store
        fresh.put('99999999'.zfill(14), 'list-99999999-1', b'not json', observed_at='2026-11-04T09:00:00+09:00', source_url='u')
        fresh.put('01262458'.zfill(14), 'list-01262458-1', json.dumps(list_json('01262458', '282690', LISTED), ensure_ascii=False).encode(),
                  observed_at='2026-11-04T09:00:00+09:00', source_url='u')
        self.store = fresh
        client, summary = self.run_it('20240314001093');self.assertEqual(summary['status'], 'completed')

    def test_bad_receipt_numbers_are_refused_before_any_work(self):
        for bad in ('2024031400109', '20240314001093 ', 20240314001093, None, '2024031400109a'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.run_it(bad)

    def test_quota_budget_and_provider_problems_stop_without_retry(self):
        client, summary = self.run_it('20240314001093', client=FakeClient(quota_at=1))
        self.assertEqual((summary['status'], summary['stop_reason']), ('stopped', 'quota'))
        tight = Budget(max_requests=0, min_interval=0.0, clock=lambda: 0.0, sleep=lambda s: None)
        client, summary = self.run_it('20230316000692', shared=tight);self.assertEqual((summary['stop_reason'], client.calls), ('budget', []))

        class Broken(FakeClient):
            def document_zip(self, rcept_no):
                self._tick('doc');raise ValueError('원문 응답이 zip이 아닙니다')
        client, summary = self.run_it('20230316000692', client=Broken());self.assertEqual((summary['stop_reason'], len(client.calls)), ('provider_error', 1))
        self.assertIsNone(self.store.latest('20230316000692', 'document-zip'))


if __name__ == '__main__':unittest.main()
