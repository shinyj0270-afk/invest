import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from investment.pit_artifacts import ArtifactStore
from investment.pit_first_call import run_delisted_list
from investment.pit_live import plan_delisted_list
from tests.test_pit_delisted import ROWS, TIRE, budget
from tests.test_pit_first_call import FakeClient, list_json
from tests.test_pit_live import corp_zip


class DelistedExtraTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root = Path(self.tmp.name)
        self.store = ArtifactStore(self.root / 'artifacts');self.put_corps(ROWS)

    def put_corps(self, rows):
        self.store.put('00000000000000', 'corpcode-zip', corp_zip(rows), observed_at='2026-11-04T09:00:00+09:00', source_url='fake')

    def run_it(self, client, name='동아타이어공업'):
        shared = budget();client.budget = shared
        result = run_delisted_list(client=client, store=self.store, budget=shared, root=self.root, name=name, bgn='20190101', end='20241231')
        saved = json.loads((self.root / f'.local/pit-pilot/delisted-{name}.json').read_text(encoding='utf-8'))
        self.assertEqual(saved, result);self.assertEqual(result['requests_used'], shared.count)
        return result

    def test_unknown_and_duplicate_names_at_the_required_store_key(self):
        for rows, name in [(ROWS, 'unknown'), (ROWS + [('99999999', '동아타이어공업', '')], '동아타이어공업')]:
            self.put_corps(rows);client = FakeClient()
            result = self.run_it(client, name)
            self.assertEqual((result['status'], result['stop_reason'], client.calls), ('stopped', 'corp_code_not_unique', []))

    def test_rejected_response_has_detail(self):
        client = FakeClient(lists={('01262458', 1): list_json('01262458', '999999', TIRE)})
        result = self.run_it(client)
        self.assertEqual((result['status'], result['stop_reason']), ('stopped', 'response_rejected'))
        self.assertIn('종목코드', result['stop_detail']);self.assertEqual(client.calls, ['list:01262458:1'])

    def test_provider_error_has_detail(self):
        client = FakeClient()
        with patch.object(client, 'list_page', side_effect=ValueError('fake provider error')):
            result = self.run_it(client)
        self.assertEqual((result['status'], result['stop_reason'], result['stop_detail']), ('stopped', 'provider_error', 'fake provider error'))

    def test_empty_periods_are_not_december_only(self):
        client = FakeClient(lists={('01262458', 1): list_json('01262458', '282690', [('20210330000100', '사업보고서')])})
        result = self.run_it(client)
        self.assertEqual(result['fiscal_year_ends'], []);self.assertFalse(result['december_only']);self.assertEqual(result['consecutive_december_years'], 0)

    def test_longest_run_survives_a_gap_and_a_shorter_final_run(self):
        rows = [(f'{year + 1}0330000100', f'사업보고서 ({year}.12)') for year in (2017, 2018, 2019, 2021)]
        result = self.run_it(FakeClient(lists={('01262458', 1): list_json('01262458', '282690', rows)}))
        self.assertTrue(result['december_only']);self.assertEqual(result['consecutive_december_years'], 3)

    def test_exact_plan_limits(self):
        result = plan_delisted_list(name='example', bgn='20190101', end='20241231')
        self.assertEqual((result['max_requests'], result['min_interval_seconds'], len(result['requests'])), (3, 1.0, 2))
        self.assertEqual({r['kind'] for r in result['requests']}, {'list'})
        self.assertEqual({r['host'] for r in result['requests']}, {'opendart.fss.or.kr'})
        self.assertTrue(result['storage']);self.assertTrue(result['stop_conditions']);self.assertTrue(result['notes'])

    def test_two_pages_blank_stock_filtering_and_reuse(self):
        self.put_corps([('01262458', '동아타이어공업', '')])
        rows = [TIRE[0], TIRE[-1], ('20230330000100', '사업보고서 unusual')]
        pages = {('01262458', 1): list_json('01262458', '', rows[:2], total=3, total_page=2, count=2),
                 ('01262458', 2): list_json('01262458', '', rows[2:], page=2, total=3, total_page=2, count=2)}
        client = FakeClient(lists=pages);result = self.run_it(client)
        self.assertEqual((result['status'], result['requests_used'], result['excluded']), ('completed', 2, 1))
        self.assertEqual(len(result['receipts']), 1);self.assertEqual(result['uncertain'], [dict(rcept_no=rows[2][0], report_nm=rows[2][1])])
        again = FakeClient();result = self.run_it(again)
        self.assertEqual((again.calls, result['requests_used'], result['reused']), ([], 0, ['list-01262458-1', 'list-01262458-2']))

    def test_cli_wiring_and_exit_codes_with_fakes(self):
        import io
        from contextlib import redirect_stdout
        from tools.pit_pilot import main
        args = ['run-delisted', '--root', str(self.root), '--confirm-first-call', '--name', 'example', '--bgn', '20190101', '--end', '20241231']
        for status, code in [('completed', 0), ('stopped', 3), ('too_many_pages', 3)]:
            summary = dict(status=status, stop_reason=None, stop_detail=None, receipts=[], uncertain=[], requests_used=0, reused=[])
            with patch('investment.pit_live.key_from_env', return_value='fake'), patch('requests.Session') as session, \
                 patch('investment.pit_first_call.run_delisted_list', return_value=summary) as run, redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(args), code)
            self.assertEqual(json.loads(out.getvalue())['status'], status)
            kw = run.call_args.kwargs
            self.assertEqual((kw['budget'].max_requests, kw['budget'].min_interval), (3, 1.0))
            self.assertEqual(kw['store'].root, self.root / '.local/pit-pilot/artifacts')
            self.assertIs(kw['client'].session, session.return_value.__enter__.return_value)
            self.assertEqual((kw['name'], kw['bgn'], kw['end']), ('example', '20190101', '20241231'))


if __name__ == '__main__':unittest.main()
