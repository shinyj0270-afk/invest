import json
import tempfile
import unittest
from pathlib import Path
from investment.pit_acquire import Budget
from investment.pit_artifacts import ArtifactStore
from investment.pit_first_call import run_delisted_list
from investment.pit_live import QuotaStop, plan_delisted_list
from tests.test_pit_first_call import FakeClient, list_json
from tests.test_pit_live import corp_zip

ROWS = [('01262458', '동아타이어공업', '282690'), ('00148717', '도레이케미칼', '008000')]
TIRE = [('20210330000100', '사업보고서 (2020.12)'), ('20220330000200', '사업보고서 (2021.12)'), ('20220601000300', '[기재정정]사업보고서 (2021.12)'),
        ('20230330000400', '사업보고서 (2022.12)'), ('20240329000500', '사업보고서 (2023.12)'), ('20240515000600', '분기보고서 (2024.03)')]


def budget():
    return Budget(max_requests=3, min_interval=0.0, clock=lambda: 0.0, sleep=lambda s: None)


class DelistedListTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root = Path(self.tmp.name)
        self.store = ArtifactStore(self.root / '.local/pit-pilot/artifacts');self.store.put('00000000000000', 'corpcode-zip', corp_zip(ROWS), observed_at='2026-11-04T09:00:00+09:00', source_url='u')

    def run_it(self, client, name='동아타이어공업', shared=None):
        shared = shared or budget();client.budget = shared
        return run_delisted_list(client=client, store=self.store, budget=shared, root=self.root, name=name, bgn='20190101', end='20241231')

    def test_a_unique_name_is_listed_with_at_most_two_pages_using_the_stored_corp_code_file(self):
        client = FakeClient(lists={('01262458', 1): list_json('01262458', '282690', TIRE)});summary = self.run_it(client)
        self.assertEqual(client.calls, ['list:01262458:1']);self.assertEqual(summary['status'], 'completed')
        self.assertEqual([r['title_period'] for r in summary['receipts']], ['2020-12', '2021-12', '2021-12', '2022-12', '2023-12'])
        self.assertEqual(summary['fiscal_year_ends'], ['2020-12', '2021-12', '2022-12', '2023-12'])
        self.assertEqual(summary['december_only'], True);self.assertEqual(summary['consecutive_december_years'], 4)
        self.assertTrue((self.root / '.local/pit-pilot/delisted-동아타이어공업.json').exists())

    def test_a_non_december_or_non_consecutive_history_is_reported_not_hidden(self):
        mixed = [('20150331000100', '사업보고서 (2014.12)'), ('20150629000200', '사업보고서 (2015.03)'), ('20160629000300', '사업보고서 (2016.03)')]
        client = FakeClient(lists={('00148717', 1): list_json('00148717', '008000', mixed)});summary = self.run_it(client, name='도레이케미칼')
        self.assertFalse(summary['december_only']);self.assertEqual(summary['consecutive_december_years'], 1)

    def test_an_ambiguous_or_unknown_name_makes_no_request(self):
        client = FakeClient();summary = self.run_it(client, name='없는회사')
        self.assertEqual((summary['status'], summary['stop_reason'], client.calls), ('stopped', 'corp_code_not_unique', []))
        self.store.put('00000000000000', 'corpcode-zip', corp_zip(ROWS + [('99999999', '동아타이어공업', '')]), observed_at='2026-11-04T09:00:00+09:00', source_url='u')
        client = FakeClient();summary = self.run_it(client);self.assertEqual((summary['stop_reason'], client.calls), ('corp_code_not_unique', []))

    def test_a_quota_signal_and_an_exhausted_budget_stop_at_once(self):
        client = FakeClient(lists={}, quota_at=1);summary = self.run_it(client)
        self.assertEqual((summary['status'], summary['stop_reason']), ('stopped', 'quota'))
        tight = Budget(max_requests=0, min_interval=0.0, clock=lambda: 0.0, sleep=lambda s: None)
        client = FakeClient(lists={('01262458', 1): list_json('01262458', '282690', TIRE)});summary = self.run_it(client, shared=tight)
        self.assertEqual((summary['stop_reason'], client.calls), ('budget', []))

    def test_too_many_pages_stop_without_extra_requests_and_a_rerun_reuses_the_stored_page(self):
        client = FakeClient(lists={('01262458', 1): list_json('01262458', '282690', [TIRE[0]] * 100, total=250, total_page=3, count=100)})
        summary = self.run_it(client);self.assertEqual(summary['status'], 'too_many_pages');self.assertEqual(client.calls, ['list:01262458:1'])
        again = FakeClient(lists={});summary = self.run_it(again);self.assertEqual((again.calls, summary['reused']), ([], ['list-01262458-1']))

    def test_a_missing_corp_code_file_is_a_clear_stop_not_a_request(self):
        empty = ArtifactStore(self.root / 'other');client = FakeClient()
        summary = run_delisted_list(client=client, store=empty, budget=budget(), root=self.root, name='동아타이어공업', bgn='20190101', end='20241231')
        self.assertEqual((summary['stop_reason'], client.calls), ('corp_code_file_missing', []))

    def test_the_plan_is_at_most_two_requests_to_opendart_only(self):
        plan = plan_delisted_list(name='동아타이어공업', bgn='20190101', end='20241231')
        self.assertLessEqual(len(plan['requests']), 2);self.assertEqual({r['host'] for r in plan['requests']}, {'opendart.fss.or.kr'});self.assertFalse(plan['viewer_scraping'])
        self.assertLessEqual(plan['max_requests'], 3)


class FilenameTests(unittest.TestCase):
    def test_a_company_name_with_characters_windows_forbids_still_gives_a_safe_summary_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);store = ArtifactStore(root / 'a')
            store.put('00000000000000', 'corpcode-zip', corp_zip([('01262458', 'A/B:C*D', '282690')]), observed_at='2026-11-04T09:00:00+09:00', source_url='u')
            client = FakeClient(lists={('01262458', 1): list_json('01262458', '282690', TIRE)});client.budget = budget()
            run_delisted_list(client=client, store=store, budget=client.budget, root=root, name='A/B:C*D', bgn='20190101', end='20241231')
            files = [p.name for p in (root / '.local/pit-pilot').iterdir() if p.name.startswith('delisted-')]
            self.assertEqual(files, ['delisted-A_B_C_D.json'])


if __name__ == '__main__':unittest.main()
