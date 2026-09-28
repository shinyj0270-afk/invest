import copy
import json
import tempfile
import unittest
import batch
from pathlib import Path
from unittest.mock import patch

from investment.core import digest
from investment.refresh import merge_daily, refresh, STATUS_KEY
from investment.store import Store
from tests import test_infomax_daily

ROOT = Path(__file__).resolve().parents[1]


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'config').mkdir()
        self.config = dict(profile='home', data_dir='private_data',
            enabled_data_adapters=['infomax_manual'], infomax_refresh=dict(
                daily_file='daily.xlsx', company_config='companies.json', policy='policy.json'))
        self.write_config()
        (self.root/'companies.json').write_text('{}', encoding='utf-8')
        (self.root/'policy.json').write_text('{}', encoding='utf-8')
        helper = test_infomax_daily.DailyImportTests()
        helper.setUp()
        self.daily = helper.convert()
        self.previous = copy.deepcopy(self.daily)
        self.previous['meta'].update(financial_period='2026-06-30', financial_observed_on='2026-09-28')
        self.previous['companies'][0].update(financial_evidence=dict(period_end='2026-06-30',
            observed_million_krw={}, official_million_krw={}, differences_million_krw={},
            debt_scope_note='검토 유지', notes=[]),
            financial_accounts={'checked':123}, evidence=[{'note':'수동 근거'}])
        self.previous['companies'][0]['metrics']['roe_pct'] = 15
        self.store = Store(self.root/'private_data', 'home', 'user_input')
        self.store.save_snapshot(self.previous)
        self.converter = patch('investment.refresh.convert', return_value=self.daily).start()
        self.addCleanup(patch.stopall)

    def write_config(self):
        (self.root/'config/local.json').write_text(json.dumps(self.config), encoding='utf-8')

    def test_end_to_end_preserves_financials_and_builds_lists(self):
        self.daily['companies'][0]['metrics']['price'] = 200
        result = refresh(self.root)
        self.assertEqual(result['receipt']['status'], 'complete')
        row = self.store.latest()['companies'][0]
        self.assertEqual(row['metrics']['price'], 200)
        self.assertEqual(row['metrics']['roe_pct'], 15)
        for key in ('financial_evidence','financial_accounts','evidence','quarters'):
            self.assertEqual(row[key], self.previous['companies'][0][key])
        self.assertEqual(result['snapshot']['meta']['financial_observed_on'], '2026-09-28')
        for frequency in ('daily','weekly'):
            result_file = json.loads((self.store.path.parent/(frequency+'-latest.json')).read_text(encoding='utf-8'))
            self.assertEqual(result_file['snapshot_id'], result['receipt']['snapshot_id'])
        self.assertIsNone(Store(self.root/'private_data','home','fixture').latest())

    def test_unchanged_is_idempotent(self):
        first = refresh(self.root)
        second = refresh(self.root)
        self.assertEqual(second['receipt']['status'], 'unchanged')
        self.assertEqual(first['snapshot'], second['snapshot'])
        self.assertEqual(first['receipt']['last_data_saved_at'], second['receipt']['last_data_saved_at'])
        self.assertEqual(len(list((self.store.path.parent/'refresh-snapshots').glob('*.json'))), 1)

    def test_invalid_file_retains_last_good_and_success_stamp(self):
        good = refresh(self.root)
        self.converter.side_effect = ValueError('과거 관측 결측')
        with self.assertRaisesRegex(ValueError, '결측'):
            refresh(self.root)
        self.assertEqual(self.store.latest(), good['snapshot'])
        receipt = self.store.setting(STATUS_KEY)
        self.assertEqual(receipt['status'], 'failed')
        self.assertEqual(receipt['last_success_at'], good['receipt']['last_success_at'])
        self.assertFalse((self.store.path.parent/'refresh.lock').exists())

    def test_date_regression_rejected(self):
        self.daily['meta']['price_date'] = '2026-09-20'
        with self.assertRaisesRegex(ValueError, '과거'):
            refresh(self.root)
        self.assertEqual(self.store.latest(), self.previous)

    def test_company_change_rejected(self):
        self.daily['companies'][0]['code'] = '900002'
        with self.assertRaisesRegex(ValueError, '종목 구성'):
            refresh(self.root)
        self.assertEqual(self.store.latest(), self.previous)

    def test_batch_failure_is_partial_and_button_retry_recovers(self):
        with patch('batch.run', side_effect=ValueError('목록 잠금')):
            result = refresh(self.root)
        self.assertEqual(result['receipt']['status'], 'partial')
        self.assertNotIn('last_success_at', result['receipt'])
        self.assertEqual(self.store.latest(), result['snapshot'])
        retry = refresh(self.root)
        self.assertEqual(retry['receipt']['status'], 'unchanged')
        self.assertEqual(retry['receipt']['errors'], [])

    def test_stale_trend_retries_without_reimporting_daily_file(self):
        previous = self.store.latest()
        previous['meta']['trend_source'] = {'provider':'Yahoo Finance','cutoff':'2026-09-20'}
        self.store.save_snapshot(previous)
        with patch('tools.trend_history.fetch_charts', side_effect=ValueError('공개 시세 응답 실패')) as fetch:
            partial = refresh(self.root)
        self.assertEqual(partial['receipt']['status'],'partial')
        self.assertEqual(fetch.call_count,1)
        self.assertIn('추세 시세 재조회 실패',partial['receipt']['errors'][0])
        self.assertEqual(self.store.latest()['meta']['trend_source']['cutoff'],'2026-09-20')

        def updated(candidate, files):
            result = copy.deepcopy(candidate)
            result['meta']['trend_source']['cutoff'] = result['meta']['price_date']
            return result
        with patch('tools.trend_history.fetch_charts', return_value={}) as fetch, \
             patch('tools.trend_history.build', side_effect=updated):
            recovered = refresh(self.root)
        self.assertEqual(recovered['receipt']['status'],'complete',recovered['receipt'])
        self.assertEqual(fetch.call_count,1)
        self.assertEqual(self.store.latest()['meta']['trend_source']['cutoff'],
                         recovered['receipt']['price_date'])
        with patch('tools.trend_history.fetch_charts') as fetch:
            unchanged = refresh(self.root)
        self.assertEqual(unchanged['receipt']['status'],'unchanged')
        fetch.assert_not_called()

    def test_concurrent_refresh_rejected_without_removing_lock(self):
        lock = self.store.path.parent/'refresh.lock'
        lock.write_text('active', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '실행 중'):
            refresh(self.root)
        self.assertTrue(lock.exists())

    def test_adapter_permission_required(self):
        self.config['enabled_data_adapters'] = []
        self.write_config()
        with self.assertRaisesRegex(ValueError, '경로'):
            refresh(self.root)
        self.converter.assert_not_called()

    def test_db_write_failure_retains_last_good(self):
        # Archive creation is before the authoritative transaction.
        with patch('pathlib.Path.replace', side_effect=OSError('disk failure')):
            with self.assertRaisesRegex(OSError, 'disk failure'):
                refresh(self.root)
        self.assertEqual(self.store.latest(), self.previous)

    def test_app_button_success_error_and_fixture_separation(self):
        from streamlit.testing.v1 import AppTest
        from investment.local_config import load_local
        local = load_local(self.root)
        with patch('investment.local_config.load_local', return_value=local), \
             patch('investment.refresh.refresh', side_effect=lambda root: refresh(self.root)):
            app = AppTest.from_file(str(ROOT/'app.py'), default_timeout=30).run()
            next(b for b in app.button if b.label=='저장 파일로 갱신').click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(any('갱신 완료' in s.value for s in app.success))
            self.converter.side_effect = ValueError('잘못된 파일')
            next(b for b in app.button if b.label=='저장 파일로 갱신').click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(any('잘못된 파일' in e.value for e in app.error))
            next(s for s in app.selectbox if s.label=='데이터 모드').select('가상 테스트').run()
            self.assertFalse(any(b.label=='저장 파일로 갱신' for b in app.button))


if __name__ == '__main__':
    unittest.main()
