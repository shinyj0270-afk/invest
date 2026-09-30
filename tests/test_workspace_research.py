import copy
import json
import unittest
from datetime import date, timedelta
from statistics import mean

from investment.fixture import make_fixture
from investment.trend import calculate
from investment.workspace_research import build_research


class WorkspaceResearchTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = make_fixture()
        self.snapshot['companies'] = self.snapshot['companies'][:1]
        self.row = self.snapshot['companies'][0]
        self.code = self.row['code']
        for bar in self.row['prices']:
            bar['final'] = True
        for bar in self.snapshot['benchmarks']['KOSPI']:
            bar.update(final=True, venue='KRX')

    def result(self):
        return build_research(self.snapshot)['rows'][self.code]

    def test_existing_rs_formula_and_no_new_score_or_private_fields(self):
        self.row['private_note'] = 'PRIVATE SENTINEL'
        self.row['holdings'] = {'quantity': 999}
        before = copy.deepcopy(self.snapshot)
        payload = build_research(self.snapshot)
        tech = payload['rows'][self.code]['technical']
        old = calculate(self.row, self.snapshot['benchmarks']['KOSPI'],
                        self.snapshot['sessions'], self.snapshot['meta']['price_date'])
        self.assertEqual(tech['status'], old['status'])
        self.assertEqual(tech['rs126'], old['rs126'])
        self.assertAlmostEqual(tech['rs126_pct'], old['rs126']*100)
        self.assertNotIn('score', tech)
        self.assertEqual(payload['rs_choice'], 'price_primary_excess_secondary')
        self.assertIn('price_strength', tech)
        self.assertEqual(payload['data_mode'], 'fixture')
        self.assertNotIn('PRIVATE SENTINEL', json.dumps(payload, allow_nan=False))
        self.assertEqual(self.snapshot, before)

    def test_ma_series_uses_only_preceding_prices(self):
        tech = self.result()['technical']
        self.assertEqual(len(tech['series']), 160)
        index = len(self.row['prices'])-160
        first = tech['series'][0]
        expected = mean(b['close'] for b in self.row['prices'][index-49:index+1])
        self.assertAlmostEqual(first['ma50'], expected)
        self.assertIsNone(first['ma150'])
        self.row['prices'][-1]['close'] *= 2
        self.assertEqual(self.result()['technical']['series'][0], first)

    def test_52_weeks_uses_calendar_window_not_252_bars(self):
        cutoff = date.fromisoformat(self.snapshot['meta']['price_date'])
        lower = (cutoff-timedelta(weeks=52)).isoformat()
        in_window = [b for b in self.row['prices'] if b['date'] > lower]
        in_window[0]['close'] = 1000000
        tech = self.result()['technical']
        self.assertEqual(tech['high_52w_close'], 1000000)
        self.assertAlmostEqual(tech['gap_to_52w_high_pct'], (self.row['prices'][-1]['close']/1000000-1)*100)
        self.row['prices'] = self.row['prices'][-252:]
        self.assertIsNone(self.result()['technical']['high_52w_close'])

    def test_unverified_calendar_withholds_52_week_high(self):
        self.snapshot['meta'].update(data_mode='user_input', calendar_basis='observed_dates_unverified')
        tech = self.result()['technical']
        self.assertIsNone(tech['high_52w_close'])
        self.assertIn('캘린더', tech['high_52w_reason'])
        self.assertIsNotNone(tech['sma']['50'])
        self.assertIsNone(tech['rs126_pct'])
        self.assertIsNone(tech['rs252_pct'])
        self.assertEqual(tech['status'], 'unknown')
        self.snapshot['meta']['calendar_basis'] = 'verified_exchange_sessions'
        self.assertIsNotNone(self.result()['technical']['high_52w_close'])

    def test_partial_overlay_calendar_cannot_leave_legacy_rs_or_pass(self):
        self.row['trend_prices'] = copy.deepcopy(self.row['prices'])
        self.row['trend_price_venue'] = 'KRX'
        self.snapshot['meta']['trend_sessions'] = list(self.snapshot['sessions'])
        del self.row['trend_prices'][-100]
        del self.snapshot['meta']['trend_sessions'][-100]
        tech = self.result()['technical']
        self.assertTrue(tech['series'])
        self.assertIsNone(tech['price_strength']['weighted_return_pct'])
        self.assertIsNone(tech['rs126_pct'])
        self.assertIsNone(tech['rs252_pct'])
        self.assertIsNone(tech['high_52w_close'])
        self.assertEqual(tech['status'], 'unknown')

    def test_small_rank_population_preserves_valid_individual_trend(self):
        tech = self.result()['technical']
        self.assertIsNone(tech['price_strength']['score'])
        self.assertIsNotNone(tech['price_strength']['weighted_return_pct'])
        self.assertEqual(tech['status'], 'pass')
        self.assertIsNotNone(tech['rs126_pct'])

    def test_gap_stale_mixed_venue_adjustment_or_unfinalized_are_pending(self):
        for change in ('gap', 'stale', 'venue', 'adjustment', 'final', 'absent_final'):
            with self.subTest(change=change):
                original = copy.deepcopy(self.row['prices'])
                if change == 'gap': del self.row['prices'][-70]
                elif change == 'stale': self.row['prices'].pop()
                elif change == 'venue': self.row['prices'][-70]['venue'] = 'OTHER'
                elif change == 'adjustment': self.row['prices'][-70]['adjustment_basis'] = 'unadjusted'
                elif change == 'final': self.row['prices'][-70]['final'] = False
                else: del self.row['prices'][-70]['final']
                tech = self.result()['technical']
                self.assertEqual(tech['status'], 'unknown')
                self.assertIsNone(tech['rs126'])
                self.assertEqual(tech['series'], [])
                self.assertIsNone(tech['high_52w_close'])
                self.row['prices'] = original

    def test_future_bars_and_benchmark_do_not_change_results(self):
        before = self.result()['technical']
        self.row['prices'].append(dict(self.row['prices'][-1], date='2099-01-01', close=999999))
        self.snapshot['sessions'].append('2099-01-01')
        self.snapshot['benchmarks']['KOSPI'].append(dict(date='2099-01-01', close=1))
        self.assertEqual(self.result()['technical'], before)

    def test_unfinalized_benchmark_withholds_rs_but_keeps_price_ma(self):
        del self.snapshot['benchmarks']['KOSPI'][-1]['final']
        tech = self.result()['technical']
        self.assertIsNone(tech['rs126'])
        self.assertIsNotNone(tech['sma']['200'])
        self.assertEqual(tech['status'], 'unknown')

    def test_overlay_uses_own_dates_and_does_not_fallback(self):
        self.row['trend_prices'] = copy.deepcopy(self.row['prices'])
        self.row['trend_price_venue'] = 'KRX'
        self.row['trend_prices'].pop()
        self.assertEqual(self.result()['technical']['series'], [])

    def test_future_financial_period_and_availability_are_not_current_facts(self):
        self.row['financial_period'] = '2099-03-31'
        self.assertTrue(all(v is None for v in self.result()['fundamental']['metrics'].values()))
        del self.row['financial_period']
        self.row['financial_available_on'] = '2099-01-01'
        self.assertTrue(all(v is None for v in self.result()['fundamental']['metrics'].values()))

    def test_quarter_half_year_and_annual_periods(self):
        for period in ('2025Q4', '2025-Q4', '2026-H1', '2026H1', '2025', '2026-03-31 단독분기'):
            with self.subTest(period=period):
                self.row['financial_period'] = period
                self.assertIsNotNone(self.result()['fundamental']['metrics']['roe_pct'])
        for period in ('2026Q4', '2026-H2', '2026', 'unknown'):
            with self.subTest(period=period):
                self.row['financial_period'] = period
                self.assertIsNone(self.result()['fundamental']['metrics']['roe_pct'])

    def test_valuation_has_its_own_validity(self):
        self.assertIsNone(self.result()['fundamental']['metrics']['per'])
        self.row['financial_period'] = 'unknown'
        self.row['valuation_details'] = {'per': {'status': 'derived', 'value': 10},
                                        'pbr': {'status': 'unknown', 'value': 1}}
        facts = self.result()['fundamental']
        self.assertEqual(facts['metrics']['per'], 10)
        self.assertIsNone(facts['metrics']['pbr'])
        self.assertIn('PER 10.00배', facts['notes'])

    def test_event_allowlist_cutoff_and_fixture_isolation(self):
        public = dict(code=self.code, kind='disclosure', title='합성 공시', source='가상 원천',
                      url='https://example.org/event', published_on='2026-09-01',
                      reviewed=True, private_note='PRIVATE', data_mode='fixture')
        events = {self.code: [public, dict(public, published_on='2099-01-01'),
            dict(public, first_seen_at='2099-01-01T00:00:00+09:00'),
            dict(public, url='javascript:alert(1)'), dict(public, data_mode='live')]}
        rows = build_research(self.snapshot, events)['rows'][self.code]['events']
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0]), {'kind', 'title', 'source', 'url', 'published_on'})
        self.assertNotIn('PRIVATE', json.dumps(rows))

    def test_invalid_dates_and_duplicates_do_not_generate_chart(self):
        self.row['prices'][-2]['date'] = self.row['prices'][-1]['date']
        self.assertEqual(self.result()['technical']['series'], [])


if __name__ == '__main__':
    unittest.main()
