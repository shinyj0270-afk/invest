import tempfile
import unittest
from pathlib import Path
from investment.pit_acquire import Budget, BudgetExceeded, acquire_receipt
from investment.pit_artifacts import ArtifactStore

NO = '20260310000001'
NOW = '2026-11-04T09:00:00+09:00'


def node(doc='cfs', basis='CFS', url='https://example.invalid/v?rcpNo=' + NO, title='연결재무제표'):
    return dict(document_id=doc, url=url, title=title, basis=basis)


def good_record():
    return dict(code='298040', basis='CFS', year=2025, quarter=4, period_start='2025-01-01', period_end='2025-12-31', receipt=NO,
        unit='KRW', currency='KRW', parser_version='p', url='u', period_contract=dict(report_kind='annual', source=dict(sha256='b' * 64)),
        values=dict(revenue=1.0, operating_profit=2.0))


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store = ArtifactStore(Path(self.tmp.name));self.fetched = []

    def run_acquire(self, nodes, fetch=None, parse=None, **over):
        def default_fetch(url):
            self.fetched.append(url);return b'<html>statements</html>'
        kw = dict(entry=dict(rcept_no=NO, rcept_dt='2026-03-10'), company='298040', basis='CFS', discover=lambda no: nodes,
            fetch=fetch or default_fetch, parse=parse or (lambda data, n, e: good_record()), store=self.store, now=NOW)
        kw.update(over);return acquire_receipt(**kw)


class AcquireTests(Fixture):
    def test_one_qualifying_candidate_is_fetched_stored_parsed_and_mapped(self):
        out = self.run_acquire([node(), node(doc='ofs', basis='OFS', title='재무제표')])
        self.assertEqual(out['status'], 'ok');self.assertEqual(out['receipt']['values'], dict(revenue=1.0, op=2.0))
        self.assertEqual(out['artifact']['status'], 'first');self.assertEqual(self.fetched, ['https://example.invalid/v?rcpNo=' + NO])
        self.assertEqual(self.store.read(out['artifact']), b'<html>statements</html>')
        self.assertEqual(out['provenance']['document_sha256'], 'b' * 64)

    def test_zero_or_several_qualifying_candidates_block_the_receipt_before_any_fetch(self):
        for nodes, reason in (([], 'no_candidate'), ([node(basis='OFS')], 'no_candidate'), ([node(), node(doc='cfs2')], 'multiple_candidates')):
            with self.subTest(reason=reason):
                out = self.run_acquire(nodes);self.assertEqual((out['status'], out['reason']), ('blocked', reason))
        self.assertEqual(self.fetched, []);self.assertEqual(self.store.entries(), [])

    def test_a_failed_download_is_recorded_and_the_receipt_is_failed_not_dropped(self):
        def boom(url):raise OSError('timeout')
        out = self.run_acquire([node()], fetch=boom)
        self.assertEqual((out['status'], out['reason']), ('failed', 'fetch_failed'))
        self.assertEqual([(e['status'], e['reason']) for e in self.store.entries()], [('failed', 'timeout')])

    def test_a_parse_failure_keeps_the_downloaded_bytes(self):
        def bad(data, n, e):raise ValueError('대차 불일치')
        out = self.run_acquire([node()], parse=bad)
        self.assertEqual((out['status'], out['reason']), ('failed', 'parse_failed'))
        self.assertEqual(self.store.entries()[0]['status'], 'first')                       # the bytes are preserved for review

    def test_a_record_outside_the_pilot_scope_is_a_mapping_failure_with_the_artifact_kept(self):
        usd = dict(good_record(), currency='USD', unit='USD')
        out = self.run_acquire([node()], parse=lambda d, n, e: usd)
        self.assertEqual((out['status'], out['reason']), ('failed', 'mapping_failed'));self.assertEqual(len(self.store.entries()), 1)

    def test_changed_bytes_on_a_second_acquisition_are_flagged(self):
        self.run_acquire([node()]);second = self.run_acquire([node()], fetch=lambda url: b'<html>different</html>')
        self.assertEqual(second['artifact']['status'], 'changed')
        self.assertEqual(second['status'], 'changed_bytes')                               # needs a human decision; never silently reused

    def test_the_budget_is_charged_per_request_and_stops_the_run(self):
        budget = Budget(max_requests=1, min_interval=0.0, clock=lambda: 0.0, sleep=lambda s: None)
        self.run_acquire([node()], budget=budget)
        with self.assertRaises(BudgetExceeded):self.run_acquire([node()], budget=budget)


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
