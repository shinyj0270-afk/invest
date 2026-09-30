import copy
import json
import unittest

from investment.fixture import make_fixture
from investment.price_strength import analyze_price_strength, benchmark_excess
from investment.workspace_research import build_research


class PriceStrengthTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = make_fixture()
        for row in self.snapshot['companies']:
            for bar in row['prices']:
                bar['final'] = True
        for bar in self.snapshot['benchmarks']['KOSPI']:
            bar.update(final=True, venue='KRX')
        self.row = self.snapshot['companies'][0]
        self.code = self.row['code']

    def result(self):
        return analyze_price_strength(self.snapshot)[self.code]

    def test_independent_quarters_and_recent_double_weight(self):
        for index, value in [(-253, 100), (-190, 110), (-127, 132), (-64, 171.6), (-1, 240.24)]:
            self.row['prices'][index]['close'] = value
        value = self.result()
        for actual, expected in zip(value['quarter_returns_pct'], [40, 30, 20, 10]):
            self.assertAlmostEqual(actual, expected)
        self.assertAlmostEqual(value['weighted_return_pct'], 28)
        self.assertEqual(value['status'], 'ready')
        self.assertEqual(value['eligible_count'], 8)
        self.assertAlmostEqual(value['score'], 93.75)

    def test_midpoint_ties_share_same_score(self):
        for row in self.snapshot['companies']:
            row['prices'] = copy.deepcopy(self.row['prices'])
        results = analyze_price_strength(self.snapshot)
        self.assertTrue(all(r['score'] == 50 for r in results.values()))
        self.assertTrue(all('저장 유효 8개 내 순위' in r['reason'] for r in results.values()))

    def test_minimum_five_and_excluded_security(self):
        self.snapshot['companies'] = self.snapshot['companies'][:5]
        self.snapshot['companies'][-1]['security_type'] = 'etf'
        result = self.result()
        self.assertIsNone(result['score'])
        self.assertIsNotNone(result['weighted_return_pct'])
        self.assertEqual((result['universe_count'], result['eligible_count']), (4, 4))

    def test_future_bars_do_not_change_values(self):
        before = analyze_price_strength(self.snapshot)
        for row in self.snapshot['companies']:
            row['prices'].append(dict(row['prices'][-1], date='2099-01-01', close=999999))
        self.snapshot['sessions'].append('2099-01-01')
        self.assertEqual(analyze_price_strength(self.snapshot), before)

    def test_invalid_windows_excluded_from_population(self):
        original = copy.deepcopy(self.snapshot)
        for bad in ('missing', 'stale', 'unfinal', 'adjustment', 'venue', 'suspended', 'negative', 'duplicate'):
            with self.subTest(bad=bad):
                self.snapshot = copy.deepcopy(original); self.row = self.snapshot['companies'][0]
                if bad == 'missing': del self.row['prices'][-100]
                elif bad == 'stale': self.row['prices'].pop()
                elif bad == 'suspended': self.row['suspended'] = True
                elif bad == 'duplicate': self.row['prices'][-2]['date'] = self.row['prices'][-1]['date']
                elif bad == 'negative': self.row['prices'][-1]['close'] = -1
                elif bad == 'unfinal': self.row['prices'][-1]['final'] = False
                elif bad == 'adjustment': self.row['prices'][-1]['adjustment_basis'] = 'unadjusted'
                else: self.row['prices'][-1]['venue'] = 'OTHER'
                result = self.result()
                self.assertIsNone(result['score'])
                self.assertIsNone(result['weighted_return_pct'])
                self.assertEqual(result['eligible_count'], 7)

    def test_calendar_verified_and_overlay_cannot_silently_fallback(self):
        self.snapshot['meta'].update(data_mode='user_input', calendar_basis='observed_dates_unverified')
        self.assertIsNone(self.result()['score'])
        self.snapshot['meta']['calendar_basis'] = 'verified_exchange_sessions'
        self.assertIsNotNone(self.result()['score'])
        self.row['trend_prices'] = copy.deepcopy(self.row['prices'][:-1])
        self.row['trend_price_venue'] = 'KRX'
        self.assertIsNone(self.result()['score'])

    def test_different_venues_have_separate_populations(self):
        for row in self.snapshot['companies'][-3:]:
            row['price_venue'] = 'OTHER'
            for bar in row['prices']:
                bar['venue'] = 'OTHER'
        results = analyze_price_strength(self.snapshot)
        self.assertEqual(results[self.code]['eligible_count'], 5)
        self.assertIsNotNone(results[self.code]['score'])
        last = results[self.snapshot['companies'][-1]['code']]
        self.assertEqual(last['eligible_count'], 3)
        self.assertIsNone(last['score'])

    def test_observed_overlay_intersection_is_not_the_exchange_calendar(self):
        self.row['trend_prices'] = copy.deepcopy(self.row['prices'])
        self.row['trend_price_venue'] = 'KRX'
        self.snapshot['meta']['trend_sessions'] = list(self.snapshot['sessions'])
        del self.row['trend_prices'][-100]
        del self.snapshot['meta']['trend_sessions'][-100]
        self.assertIsNone(self.result()['score'])

    def test_universe_ranking_does_not_depend_on_fundamental_filters_or_input_order(self):
        original = copy.deepcopy(self.snapshot)
        before = analyze_price_strength(self.snapshot)
        for row in self.snapshot['companies']:
            row['metrics']['per'] = -999
            row['industry'] = '필터로 숨긴 산업'
            row['ui_selected'] = False
        self.snapshot['companies'].reverse()
        self.assertEqual(analyze_price_strength(self.snapshot), before)
        actual = copy.deepcopy(original)
        analyze_price_strength(actual)
        self.assertEqual(actual, original)
        json.dumps(before, allow_nan=False)

    def test_price_only_excess_is_available_without_ohlcv(self):
        expected = benchmark_excess(self.row, self.snapshot)
        for bar in self.row['prices']:
            for key in ('high', 'low', 'volume', 'turnover'):
                bar.pop(key, None)
        data = build_research(self.snapshot)
        technical = data['rows'][self.code]['technical']
        self.assertEqual(data['rs_choice'], 'price_primary_excess_secondary')
        self.assertEqual(technical['status'], 'unknown')
        self.assertEqual(technical['price_strength']['status'], 'ready')
        self.assertIsNotNone(technical['rs126_pct'])
        self.assertEqual(technical['rs126_pct'], expected['rs126_pct'])
        self.snapshot['benchmarks']['KOSPI'][-1]['final'] = False
        self.assertIsNone(benchmark_excess(self.row, self.snapshot)['rs126_pct'])


if __name__ == '__main__':
    unittest.main()
