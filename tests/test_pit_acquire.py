import tempfile
import unittest
from pathlib import Path
from investment.pit_acquire import Budget, BudgetExceeded, acquire_receipt
from investment.pit_artifacts import ArtifactStore

NO = '20260310000001'
NOW = '2026-11-04T09:00:00+09:00'


def node(doc='cfs', basis='CFS', url='https://example.invalid/v?rcpNo=' + NO, title='연결재무제표'):
    return dict(document_id=doc, url=url, title=title, basis=basis)


def good_record(**over):
    base = dict(code='298040', basis='CFS', year=2025, quarter=4, period_start='2025-01-01', period_end='2025-12-31', receipt=NO,
        unit='KRW', currency='KRW', parser_version='p', url='u', period_contract=dict(report_kind='annual', source=dict(sha256='b' * 64)),
        values=dict(revenue=1.0, operating_profit=2.0))
    base.update(over);return base


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store = ArtifactStore(Path(self.tmp.name));self.fetched = []

    def run_acquire(self, nodes, fetch=None, parse=None, discover=None, **over):
        def default_fetch(url):
            self.fetched.append(url);return b'<html>statements</html>'
        kw = dict(entry=dict(rcept_no=NO, rcept_dt='2026-03-10'), company='298040', basis='CFS', discover=discover or (lambda no, spend: nodes),
            fetch=fetch or default_fetch, parse=parse or (lambda data, n, e: good_record()), store=self.store, now=NOW)
        kw.update(over);return acquire_receipt(**kw)


class AcquireTests(Fixture):
    def test_one_qualifying_candidate_is_fetched_stored_parsed_and_mapped_with_bound_provenance(self):
        out = self.run_acquire([node(), node(doc='ofs', basis='OFS', title='재무제표')])
        self.assertEqual(out['status'], 'ok');self.assertEqual(out['receipt']['values'], dict(revenue=1.0, op=2.0))
        self.assertEqual(out['artifact']['status'], 'first');self.assertEqual(self.fetched, ['https://example.invalid/v?rcpNo=' + NO])
        self.assertEqual(self.store.read(out['artifact']), b'<html>statements</html>')
        prov = out['provenance']
        self.assertEqual(prov['artifact_sha256'], out['artifact']['sha256'])                     # raw bytes of THIS artifact
        self.assertEqual(prov['contract_sha256'], 'b' * 64)                                      # the parser's own hash, a different thing
        self.assertNotEqual(prov['artifact_sha256'], prov['contract_sha256']);self.assertEqual(prov['artifact_document_id'], 'cfs')

    def test_zero_or_several_qualifying_candidates_block_the_receipt_before_any_fetch(self):
        for nodes, reason in (([], 'no_candidate'), ([node(basis='OFS')], 'no_candidate'), ([node(), node(doc='cfs2')], 'multiple_candidates')):
            with self.subTest(reason=reason):
                out = self.run_acquire(nodes);self.assertEqual((out['status'], out['reason']), ('blocked', reason))
        self.assertEqual(self.fetched, []);self.assertEqual(self.store.entries(), [])

    def test_a_failed_download_is_recorded_and_the_receipt_is_failed_not_dropped(self):
        def boom(url):raise OSError('timeout')
        out = self.run_acquire([node()], fetch=boom)
        self.assertEqual((out['status'], out['reason'], out['detail']), ('failed', 'fetch_failed', 'timeout'))
        self.assertEqual([(e['status'], e['reason']) for e in self.store.entries()], [('failed', 'timeout')])

    def test_a_parse_failure_keeps_the_downloaded_bytes_and_the_detail(self):
        def bad(data, n, e):raise ValueError('대차 불일치')
        out = self.run_acquire([node()], parse=bad)
        self.assertEqual((out['status'], out['reason'], out['detail']), ('failed', 'parse_failed', '대차 불일치'))
        self.assertEqual(self.store.entries()[0]['status'], 'first')

    def test_the_bytes_are_stored_before_the_parser_runs(self):
        seen = []
        def parse(data, n, e):
            seen.append([x['status'] for x in self.store.entries()]);return good_record()
        self.run_acquire([node()], parse=parse);self.assertEqual(seen, [['first']])

    def test_a_record_outside_the_pilot_scope_is_a_mapping_failure_with_the_artifact_kept(self):
        usd = good_record(currency='USD', unit='USD')
        out = self.run_acquire([node()], parse=lambda d, n, e: usd)
        self.assertEqual((out['status'], out['reason']), ('failed', 'mapping_failed'));self.assertEqual(len(self.store.entries()), 1)

    def test_a_parsed_record_must_carry_the_requested_receipt_company_and_basis(self):
        for name, record in (('receipt', good_record(receipt='20260310000099')), ('basis', good_record(basis='OFS')), ('company', good_record(code='005930')), ('none', None)):
            with self.subTest(name=name):
                out = self.run_acquire([node(doc='d' + name)], parse=lambda d, n, e, r=record: r, fetch=lambda url, k=name: b'x' + k.encode())
                self.assertEqual((out['status'], out['reason']), ('failed', 'identity_mismatch'))

    def test_changed_bytes_stay_unresolved_however_often_they_are_fetched_until_a_human_pins_a_hash(self):
        first = self.run_acquire([node()]);self.assertEqual(first['status'], 'ok')
        for _ in range(2):
            again = self.run_acquire([node()], fetch=lambda url: b'<html>different</html>')
            self.assertEqual((again['status'], again['reason']), ('changed_bytes', 'unresolved_artifact_version'))
        self.store.resolve(NO, 'cfs', accepted_sha256=first['artifact']['sha256'], observed_at=NOW, reason='원문 대조 후 첫 버전 수용')
        self.assertEqual(self.run_acquire([node()], fetch=lambda url: b'<html>different</html>')['status'], 'changed_bytes')   # not the pinned bytes
        self.assertEqual(self.run_acquire([node()])['status'], 'ok')                                                          # the pinned bytes are fine

    def test_a_first_observation_with_a_wrong_expected_hash_cannot_become_ok_by_being_fetched_again(self):
        self.store.put(NO, 'cfs', b'<html>statements</html>', observed_at=NOW, source_url='u', expected_sha256='c' * 64)       # recorded as hash_mismatch
        self.assertEqual(self.run_acquire([node()])['status'], 'changed_bytes')

    def test_a_corrupt_stored_blob_fails_the_acquisition_explicitly(self):
        ok = self.run_acquire([node()]);blob = Path(self.tmp.name) / 'blobs' / ok['artifact']['sha256'];blob.write_bytes(b'corrupt')
        out = self.run_acquire([node(doc='other')])
        self.assertEqual((out['status'], out['reason']), ('failed', 'artifact_store_error'))

    def test_discovery_failure_is_a_failed_receipt_not_an_escaping_exception(self):
        def boom(no, spend):raise OSError('목차 조회 실패')
        out = self.run_acquire([], discover=boom);self.assertEqual((out['status'], out['reason'], out['detail']), ('failed', 'discovery_failed', '목차 조회 실패'))

    def test_every_request_made_by_discovery_and_fetch_is_charged_to_the_budget(self):
        def discover(no, spend):
            spend();spend();return [node()]                       # a discoverer that needs two requests
        budget = Budget(max_requests=10, min_interval=0.0, clock=lambda: 0.0, sleep=lambda s: None)
        self.run_acquire([], discover=discover, budget=budget);self.assertEqual(budget.count, 3)               # 2 discovery + 1 fetch
        tight = Budget(max_requests=1, min_interval=0.0, clock=lambda: 0.0, sleep=lambda s: None)
        with self.assertRaises(BudgetExceeded):self.run_acquire([], discover=discover, budget=tight)
        self.assertEqual(self.fetched, ['https://example.invalid/v?rcpNo=' + NO])                               # nothing fetched by the tight run

class MalformedRecordTests(Fixture):
    def test_odd_contract_shapes_do_not_escape_as_exceptions(self):
        odd = good_record(period_contract=dict(report_kind='annual', source=['bad']))
        out = self.run_acquire([node()], parse=lambda d, n, e: odd)
        self.assertEqual(out['status'], 'ok');self.assertIsNone(out['provenance']['contract_sha256'])
        class Weird(dict):
            def get(self, *a):raise TypeError('boom')
        out = self.run_acquire([node(doc='w')], parse=lambda d, n, e: Weird(good_record()), fetch=lambda url: b'w')
        self.assertEqual(out['status'], 'failed');self.assertIn(out['reason'], ('mapping_failed', 'identity_mismatch', 'parse_failed'))


class BudgetTests(unittest.TestCase):
    def test_requests_are_paced_and_counted(self):
        now = [0.0];slept = []
        def sleep(s):slept.append(s);now[0] += s
        budget = Budget(max_requests=3, min_interval=0.5, clock=lambda: now[0], sleep=sleep)
        budget.spend();budget.spend();self.assertEqual(slept, [0.5]);self.assertEqual(budget.count, 2)
        now[0] += 5;budget.spend();self.assertEqual(slept, [0.5]);self.assertEqual(budget.count, 3)    # enough time passed: no extra wait
        with self.assertRaises(BudgetExceeded):budget.spend()
        self.assertEqual(budget.count, 3)


if __name__ == '__main__':unittest.main()
