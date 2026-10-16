"""Synthetic market-source transition tests; no external network or real holdings."""
from copy import deepcopy
from datetime import datetime
from zoneinfo import ZoneInfo
import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

from investment.naver_review import build_market, validate_candidate, daily_values
from investment.holdings_bridge import holdings_input
from tests.test_infomax_daily import DailyImportTests


class NaverReviewTests(unittest.TestCase):
    def setUp(self):
        helper = DailyImportTests(); helper.setUp()
        self.before = helper.convert()
        self.before['companies'][0]['financial_accounts'] = {'checked': 123}
        self.before['companies'][0]['metrics']['roe_pct'] = 12
        self.code = '900001'
        self.now = datetime(2026, 9, 28, 8, tzinfo=ZoneInfo('Asia/Seoul'))
        self.before['meta']['fetched_at'] = '2026-09-28T07:00:00+09:00'
        bars = deepcopy(self.before['companies'][0]['prices'])
        for b in bars:
            b.update(final=True, venue='KRX', adjustment_basis='naver_chart_adjusted', turnover=None)
        self.histories = {self.code: dict(symbol=self.code, kind='item', price_date=bars[-1]['date'],
                                        prices=bars, source={'provider': 'synthetic Naver chart'})}
        self.daily = {self.code: {'items': [dict(tradingDateKst=b['date'], closingPrice=str(b['close']),
            tradingVolume=str(b['volume']), tradingValue='1000') for b in reversed(bars)]}}
        self.details = {self.code: dict(itemcode=self.code, itemname='가상 테스트 기업', type='ST',
                                        tradeTime='20260927160000', marketSum='200000000')}
        self.sources = {self.code: [{'provider': 'synthetic Naver trading values'}]}

    def build(self):
        return build_market(self.before, self.histories, self.daily, self.details, self.sources, self.now)

    def test_replaces_full_price_basis_preserves_financials_and_flow_dates(self):
        result = self.build(); validate_candidate(self.before, result)
        row = result['companies'][0]
        self.assertEqual(row['financial_accounts'], {'checked': 123})
        self.assertEqual(row['metrics']['roe_pct'], 12)
        self.assertEqual(row['metrics']['market_cap_eok'], 2)
        self.assertEqual(row['metrics']['avg_trading_value_20d_eok'], .00001)
        self.assertEqual(result['meta']['flow_end'], self.before['meta']['flow_end'])
        self.assertEqual(row['flows'], self.before['companies'][0]['flows'])
        self.assertIsNone(row['metrics']['foreign_net_turnover_20d_pct'])
        self.assertEqual(row['market_metric_evidence']['turnover_unit'], 'KRW')
        self.assertEqual(self.before['companies'][0]['metrics']['market_cap_eok'], 1)
        bridge = holdings_input(result, '2026-09-28')
        self.assertIn('네이버', bridge['research'][0]['price_source']['label'])

    def test_source_labels_remain_compatible_with_dashboard(self):
        self.before['companies'][0]['sources'].append({'url': 'https://example.test/old', 'provider': 'old source'})
        result = self.build()
        sources = result['companies'][0]['sources']
        self.assertTrue(all(isinstance(s.get('label'), str) and s['label'] for s in sources))
        self.assertEqual(next(s['label'] for s in sources if s.get('url') == 'https://example.test/old'), 'old source')
        self.assertNotIn('label', self.before['companies'][0]['sources'][-1])

    def test_new_price_date_withholds_old_flow_metrics(self):
        self.before['meta']['flow_end'] = '2026-09-26'
        r = self.build()
        self.assertIsNone(r['companies'][0]['metrics']['foreign_net_20d_eok'])
        self.assertIn('2026-09-26', r['companies'][0]['metric_missing_reasons']['foreign_net_20d_eok'])

    def test_no_old_price_scale_join(self):
        self.before['companies'][0]['prices'][0]['date'] = '2025-01-01'
        r = self.build()
        self.assertNotEqual(r['companies'][0]['prices'][0]['date'], '2025-01-01')

    def test_corrected_volume_stays_with_actual_money_response(self):
        self.daily[self.code]['items'][0]['tradingVolume'] = '12'
        r = self.build()
        self.assertEqual(r['companies'][0]['prices'][-1]['volume'], 12)
        self.assertEqual(r['companies'][0]['prices'][-1]['turnover'], 1000)

    def test_future_detail_is_rejected_and_mismatched_date_cap_is_missing(self):
        self.details[self.code]['tradeTime'] = '20260928090000'
        with self.assertRaisesRegex(ValueError, '미래'): self.build()
        self.details[self.code]['tradeTime'] = '20260926160000'
        self.assertIsNone(self.build()['companies'][0]['metrics']['market_cap_eok'])

    def test_quantity_only_or_missing_turnover_is_not_money(self):
        self.daily[self.code]['items'][0].pop('tradingValue')
        self.daily[self.code]['items'][0]['foreignNetVolume'] = '200'
        with self.assertRaisesRegex(ValueError, '거래대금'): self.build()

    def test_duplicate_dates_and_wrong_venue_scale_fail(self):
        self.daily[self.code]['items'][1]['tradingDateKst'] = self.daily[self.code]['items'][0]['tradingDateKst']
        with self.assertRaisesRegex(ValueError, '중복'): self.build()
        self.setUp()
        self.daily[self.code]['items'][0]['closingPrice'] = '101'
        with self.assertRaisesRegex(ValueError, '불일치'): self.build()

    def test_financial_mutation_rejected_before_promotion(self):
        r = self.build(); r['companies'][0]['metrics']['roe_pct'] = 99
        with self.assertRaisesRegex(ValueError, '재무'): validate_candidate(self.before, r)
        r = self.build(); r['meta']['financial_period'] = 'changed'
        with self.assertRaisesRegex(ValueError, '메타'): validate_candidate(self.before, r)

    def test_todays_partial_row_is_ignored(self):
        rows = self.daily[self.code]['items']
        rows.insert(0, dict(tradingDateKst='2026-09-28'))
        self.assertEqual(len(daily_values({'items': rows}, cutoff='2026-09-27')), 20)

    def test_naver_route_promotion_and_network_failure_keep_last_good(self):
        from investment.store import Store
        from investment.refresh import refresh
        from investment.core import digest
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root/'config').mkdir()
            (root/'config/local.json').write_text(json.dumps(dict(profile='work', data_dir='data',
                enabled_data_adapters=['infomax_manual'], infomax_refresh={'provider':'naver'})), encoding='utf-8')
            store = Store(root/'data', 'work', 'user_input'); store.save_snapshot(self.before)
            candidate = self.build()
            with patch('investment.naver_review.NaverMarketProvider.fetch', return_value=(candidate, {'test':1}, 'synthetic Naver')), \
                 patch('batch.run', return_value={'snapshot_id':digest(candidate)}):
                result = refresh(root)
            self.assertEqual(result['receipt']['status'], 'complete')
            self.assertEqual(store.latest(), candidate)
            with patch('investment.naver_review.NaverMarketProvider.fetch', side_effect=ValueError('bad response')):
                with self.assertRaises(ValueError): refresh(root)
            self.assertEqual(store.latest(), candidate)
            self.assertFalse((store.path.parent/'refresh.lock').exists())

    def test_normal_launcher_checks_naver_freshness_only_when_opted_in(self):
        from investment.live_dashboard import configured_data
        with patch('investment.live_dashboard.load_local', return_value={'infomax_refresh':{'provider':'naver'}}), \
             patch('investment.live_dashboard.ensure_data', return_value={'test':'naver'}) as online, \
             patch('investment.live_dashboard.saved_data') as saved:
            self.assertEqual(configured_data(Path('.')), {'test':'naver'})
            online.assert_called_once_with(Path('.'), force=False)
            saved.assert_not_called()
        with patch('investment.live_dashboard.load_local', return_value={'infomax_refresh':{'provider':'daily'}}), \
             patch('investment.live_dashboard.ensure_data') as online, \
             patch('investment.live_dashboard.saved_data', return_value={'test':'file'}) as saved:
            self.assertEqual(configured_data(Path('.')), {'test':'file'})
            online.assert_not_called()


if __name__ == '__main__':
    unittest.main()
