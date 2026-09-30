"""Offline Infomax pipeline tests. All observations here are synthetic."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from investment.auto_refresh import ensure_data, target_date, KST
from investment.core import observed_close
from investment.infomax_provider import SavedSnapshotProvider
from investment.refresh import refresh
from investment.research import analyze
from investment.store import Store
from tests import test_infomax_daily


class AutoRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'config').mkdir()
        self.config = dict(profile='work', enabled_data_adapters=['infomax_manual'],
                           infomax_refresh=dict(freshness_seconds=900, retry_seconds=60))
        self.write_config()
        helper = test_infomax_daily.DailyImportTests()
        helper.setUp()
        helper.identities = {'005930': dict(helper.identities['900001'], name='삼성전자 모의자료')}
        helper.values[1][0] = '삼성전자 모의자료'
        helper.formulas[1][0] = '=IMDH("STK","005930",A3:G3,...)'
        self.snapshot = helper.convert()
        self.store = Store(self.root / 'data', 'work', 'user_input')
        self.store.save_snapshot(self.snapshot)
        self.provider = Mock()
        self.provider.fetch.return_value = (self.snapshot, {'input': 1}, 'synthetic.xlsx')
        self.time = datetime(2026, 9, 28, 10, tzinfo=KST)

    def write_config(self):
        (self.root / 'config/local.json').write_text(json.dumps(self.config), encoding='utf-8')

    def run_refresh(self, **kwargs):
        return ensure_data(self.root, provider=self.provider, checked_at=self.time, **kwargs)

    def test_normalize_cache_analysis_samsung(self):
        result = self.run_refresh()
        self.assertTrue(result['receipt']['success'])
        self.assertFalse(result['receipt']['stale'])
        self.assertEqual(result['receipt']['data_as_of'], '2026-09-27')
        self.assertEqual(result['receipt']['price_records'], 20)
        row = self.store.latest()['companies'][0]
        self.assertEqual(row['code'], '005930')
        self.assertEqual(observed_close(row, '2026-09-27')['close'], 100)
        self.assertEqual(analyze(result['snapshot'])[0]['code'], '005930')

    def test_fresh_cache_skips_provider_then_ttl_checks(self):
        self.run_refresh()
        self.time += timedelta(seconds=30)
        self.assertEqual(self.run_refresh()['receipt']['status'], 'cached')
        self.provider.fetch.assert_called_once()
        self.time += timedelta(seconds=901)
        self.run_refresh()
        self.assertEqual(self.provider.fetch.call_count, 2)

    def test_recent_existing_cache_skips_first_provider_call(self):
        recent = copy.deepcopy(self.snapshot)
        recent['meta']['fetched_at'] = self.time.isoformat()
        self.store.save_snapshot(recent)
        self.assertEqual(self.run_refresh()['receipt']['status'], 'cached')
        self.provider.fetch.assert_not_called()

    def test_malformed_manual_snapshot_returns_empty_without_crash(self):
        with self.store.connect() as db:
            db.execute('DELETE FROM snapshots')
        (self.root/'bad.json').write_text('{"schema_version":"wrong"}', encoding='utf-8')
        self.config['manual_snapshot_file'] = 'bad.json'
        self.write_config()
        self.assertIsNone(self.run_refresh()['snapshot'])

    def test_stale_refresh_does_not_make_old_market_data_fresh(self):
        self.time += timedelta(days=2)
        result = self.run_refresh()
        self.assertTrue(result['receipt']['attempted'])
        self.assertTrue(result['receipt']['stale'])
        self.assertEqual(result['receipt']['data_as_of'], '2026-09-27')

    def test_failure_fallback_and_retry_throttle(self):
        self.provider.fetch.side_effect = OSError('credential=do-not-display')
        result = self.run_refresh()
        self.assertFalse(result['receipt']['success'])
        self.assertTrue(result['receipt']['fallback'])
        self.assertEqual(result['receipt']['failed_companies'], 1)
        self.assertNotIn('do-not-display', json.dumps(result['receipt']))
        self.assertEqual(result['snapshot'], self.snapshot)
        self.time += timedelta(seconds=1)
        self.assertEqual(self.run_refresh()['receipt']['status'], 'retry_wait')
        self.provider.fetch.assert_called_once()
        self.time += timedelta(seconds=60)
        self.run_refresh()
        self.assertEqual(self.provider.fetch.call_count, 2)

    def test_manual_bypasses_throttle(self):
        self.run_refresh()
        self.run_refresh(force=True)
        self.assertEqual(self.provider.fetch.call_count, 2)

    def test_missing_financial_metrics_continue_analysis(self):
        self.snapshot['companies'][0]['metrics']['roe_pct'] = None
        self.snapshot['companies'][0]['metrics']['eps_ttm'] = None
        result = self.run_refresh()
        self.assertTrue(result['receipt']['success'])
        self.assertEqual(len(analyze(result['snapshot'])), 1)

    def test_duplicate_price_rejected_and_cache_unchanged(self):
        incoming = copy.deepcopy(self.snapshot)
        incoming['companies'][0]['prices'].append(incoming['companies'][0]['prices'][-1])
        self.provider.fetch.return_value = (incoming, {'input': 2}, 'bad.xlsx')
        result = self.run_refresh()
        self.assertFalse(result['receipt']['success'])
        self.assertEqual(self.store.latest(), self.snapshot)

    def test_shorter_window_preserves_old_prices_and_updates_overlap(self):
        incoming = copy.deepcopy(self.snapshot)
        incoming['companies'][0]['prices'] = incoming['companies'][0]['prices'][-2:]
        incoming['companies'][0]['prices'][-1]['close'] = 101
        incoming['companies'][0]['sources'] = [dict(file='short.xlsx', sha256='new-source')]
        self.provider.fetch.return_value = (incoming, {'input': 2}, 'short.xlsx')
        result = self.run_refresh()
        bars = result['snapshot']['companies'][0]['prices']
        self.assertEqual(len(bars), 20)
        self.assertEqual(bars[-1]['close'], 101)
        self.assertEqual(result['receipt']['updated_price_records'], 1)
        self.assertEqual(result['receipt']['updated_companies'], 1)
        self.assertEqual(len({p['date'] for p in bars}), 20)
        self.assertTrue(all(s in result['snapshot']['companies'][0]['sources']
                            for s in self.snapshot['companies'][0]['sources']))
        self.assertEqual(self.run_refresh(force=True)['receipt']['updated_price_records'], 0)

    def test_older_dates_or_observation_times_cannot_replace_cache(self):
        for key, value in [('as_of', '2026-09-26'), ('price_date', '2026-09-26'),
                           ('fetched_at', '2020-01-01T00:00:00+00:00')]:
            with self.subTest(key=key):
                incoming = copy.deepcopy(self.snapshot)
                incoming['meta'][key] = value
                self.provider.fetch.return_value = (incoming, {'key': key}, 'older.xlsx')
                self.assertFalse(self.run_refresh(force=True)['receipt']['success'])
                self.assertEqual(self.store.latest(), self.snapshot)

    def test_invalid_numbers_and_future_day_rejected(self):
        for value in [float('nan'), float('inf'), -1, True, None]:
            with self.subTest(value=value):
                incoming = copy.deepcopy(self.snapshot)
                incoming['companies'][0]['prices'][0]['close'] = value
                self.provider.fetch.return_value = (incoming, {}, 'bad.xlsx')
                self.assertFalse(self.run_refresh(force=True)['receipt']['success'])
                self.assertEqual(self.store.latest(), self.snapshot)
        incoming = copy.deepcopy(self.snapshot)
        incoming['meta']['as_of'] = '2999-01-01'
        self.provider.fetch.return_value = (incoming, {}, 'future.xlsx')
        self.assertFalse(self.run_refresh(force=True)['receipt']['success'])

    def test_no_cache_failure_is_empty_not_fixture(self):
        with self.store.connect() as db:
            db.execute('DELETE FROM snapshots')
        self.provider.fetch.side_effect = ConnectionError('offline')
        result = self.run_refresh()
        self.assertIsNone(result['snapshot'])
        self.assertTrue(result['receipt']['stale'])
        self.assertEqual(result['receipt']['price_records'], 0)

    def test_first_valid_import_initializes_cache(self):
        with self.store.connect() as db:
            db.execute('DELETE FROM snapshots')
        result = self.run_refresh()
        self.assertTrue(result['receipt']['success'])
        self.assertEqual(result['receipt']['updated_companies'], 1)
        self.assertIsNotNone(self.store.latest())

    def test_fixture_provider_cannot_enter_real_cache(self):
        incoming = copy.deepcopy(self.snapshot)
        incoming['meta']['data_mode'] = 'fixture'
        self.provider.fetch.return_value = (incoming, {}, 'fixture.json')
        self.assertFalse(self.run_refresh()['receipt']['success'])
        self.assertEqual(self.store.latest(), self.snapshot)

    def test_lock_does_not_crash_or_remove_other_refresh_lock(self):
        lock = self.store.path.parent / 'refresh.lock'
        lock.write_text('existing', encoding='utf-8')
        self.assertTrue(self.run_refresh()['receipt']['fallback'])
        self.provider.fetch.assert_not_called()
        self.assertTrue(lock.exists())

    def test_snapshot_adapter_legacy_without_prices(self):
        legacy = copy.deepcopy(self.snapshot)
        del legacy['companies'][0]['prices']
        del legacy['sessions']
        path = self.root / 'manual.json'
        path.write_text(json.dumps(legacy), encoding='utf-8')
        provider = SavedSnapshotProvider(path)
        result = refresh(self.root, provider=provider)
        self.assertEqual(len(result['snapshot']['companies'][0]['prices']), 20)

    def test_kst_boundary_weekend_and_configured_holiday(self):
        # Sunday UTC -> Monday KST; previous weekday is Friday.
        utc = datetime(2026, 9, 27, 16, tzinfo=timezone.utc)
        self.assertEqual(target_date(self.root, {}, utc)[0], '2026-09-25')
        calendar = dict(valid_from='2026-09-20', valid_through='2026-09-30',
                        sessions=['2026-09-21', '2026-09-22', '2026-09-23', '2026-09-28'],
                        source='synthetic holiday calendar for this test')
        (self.root/'calendar.json').write_text(json.dumps(calendar), encoding='utf-8')
        config = dict(trading_calendar_file='calendar.json')
        self.assertEqual(target_date(self.root, config, utc)[0], '2026-09-23')
        with self.assertRaises(ValueError):
            target_date(self.root, config, self.time + timedelta(days=10))

    def test_bad_config_or_calendar_returns_last_good(self):
        self.config['infomax_refresh']['freshness_seconds'] = -1
        self.write_config()
        result = self.run_refresh()
        self.assertEqual(result['snapshot'], self.snapshot)
        self.assertFalse(result['receipt']['success'])
        self.provider.fetch.assert_not_called()

    def test_partial_batch_failure_and_retry(self):
        with patch('batch.run', side_effect=ValueError('batch unavailable')):
            result = self.run_refresh()
        self.assertEqual(result['receipt']['status'], 'partial')
        self.assertFalse(result['receipt']['success'])
        self.time += timedelta(seconds=61)
        self.assertTrue(self.run_refresh()['receipt']['success'])

    def test_dashboard_start_failure_manual_recovery_and_fixture_separation(self):
        from streamlit.testing.v1 import AppTest
        from investment.local_config import load_local
        root = Path(__file__).resolve().parents[1]
        local = load_local(self.root)
        self.config['infomax_refresh'] = None
        self.write_config()
        local = load_local(self.root)
        with patch('investment.local_config.load_local', return_value=local), \
             patch('investment.refresh.provider_for', return_value=self.provider):
            self.provider.fetch.side_effect = OSError('offline')
            app = AppTest.from_file(str(root/'app.py'), default_timeout=30).run()
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(any('오래된 자료' in w.value for w in app.warning))
            self.provider.fetch.side_effect = None
            next(b for b in app.button if b.label == '데이터 새로고침').click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(app.session_state['infomax_manual_result']['success'])
            calls = self.provider.fetch.call_count
            next(s for s in app.selectbox if s.label == '데이터 모드').select('가상 테스트').run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(self.provider.fetch.call_count, calls)
            self.assertFalse(any(b.label == '데이터 새로고침' for b in app.button))


if __name__ == '__main__':
    unittest.main()
