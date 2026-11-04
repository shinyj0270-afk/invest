"""Contract for `investment/pit_factors.py`: the point-in-time quality factors Q, G, C, B and a separately named score `S_pit_QGCB` (V needs prices: not computed).

Input: PIT annual rows (`pit_annual.project` output; value fields are top-level keys). G and C are exactly those of `pit_quality.partial_factors`.
Q   median of three ROICs over the last four continuous visible annual periods. For each pair (prev, cur): ROIC = op_cur x (1 - tax rate_cur) / average(IC_prev, IC_cur),
    IC = equity + net_debt (net_debt from `pit_metrics`, so IC = equity + total debt - liquid assets). Average IC <= 0 -> the pair is unusable.
    Tax rate rule (proposal, replaces the previously undecided exception rule): pretax_income <= 0 -> rate 0; pretax_income > 0 -> income_tax_expense / pretax_income, which must lie in [0, 1]
    (outside, or income_tax_expense missing -> unusable; no statutory-rate substitution). Any unusable pair -> Q is None.
B   -net_debt / equity of the LATEST visible annual row (equity must be > 0).
net_debt is usable when its metric status is `ok`, or `partial` with every reason in `tolerated` (default: nothing is tolerated). `LIQUID_UNDERSTATEMENT` is the set that tolerates a missing
    short_term_financial_instruments / current_financial_assets (net debt then is an upper bound).
Result of `compute_factors(rows, as_of, *, tolerated=frozenset())`: dict(G, C, Q, B, missing, reasons, ambiguous_periods, periods_used, pit=True, scope='G,C,Q,B', not_computed=['V'],
    tolerated=sorted list, approximations={factor: sorted list of the tolerated reasons / `tax_rate_zero_for_loss` actually used}).
Reasons per missing factor (sorted, unique): not_enough_years, missing:<field>, net_debt:<reason of the net_debt metric>, tax_rate_unusable, non_positive_invested_capital, non_positive_equity,
    ambiguous_period (a later period exists only as an ambiguous row), no_annual_row.
`pit_scores(companies, as_of, *, minimum=5, tolerated=frozenset())` ranks each factor in its own pool (`core.percentile`) and scores 100 x (.30 Q + .25 G + .20 C + .10 B) / .85 only when all four
    percentiles exist; otherwise None with reason `factor_missing` / `pool_too_small` under reasons['S_pit_QGCB']. It never writes `quality_score` or `S_long`.
Pool membership (proposal): a company whose LATEST visible annual period ended more than `max_staleness_days` (default 460, about 15 months: a year plus the filing lag; None disables it) before `as_of` is STALE:
    it is a company that has no current data on that date (for example a delisted one), so it is left out of every pool and gets S_pit_QGCB None with reason `stale_period` (and stale=True).
    Every result carries `latest_period` (the latest visible non-ambiguous period or None) and `stale`; a company without any visible row is not stale, its factors are simply missing.
"""
import copy
import unittest
from statistics import median
from investment import pit_factors as pf

REV = {2018: 80.0, 2019: 90.0, 2020: 100.0, 2021: 110.0, 2022: 121.0, 2023: 133.1}
OCF = {2018: 8.0, 2019: 9.0, 2020: 10.0, 2021: 12.0, 2022: 12.1, 2023: 20.0}
AS_OF = '2024-06-30'


def frow(year, *, company='AAA111', basis='CFS', op=50.0, equity=360.0, pretax=45.0, tax=9.0, drop=(), **over):
    r = dict(company=company, period_end=f'{year}-12-31', basis=basis, available_at=f'{year + 1}-03-15', rcept_no=f'{year + 1}0314000001', rcept_dt=f'{year + 1}-03-14',
             policy='next_session_after_rcept_dt_v1', revenue=REV[year], ocf=OCF[year], op=op, equity=equity, cash=50.0, short_term_financial_instruments=10.0,
             current_financial_assets=0.0, borrowings_current=100.0, borrowings_noncurrent=100.0, lease_total=0.0, pretax_income=pretax, income_tax_expense=tax)
    for key in drop:
        r.pop(key, None)
    r.update(over)
    return r


def series(years=(2020, 2021, 2022, 2023), **kw):
    return [frow(y, **kw) for y in years]


def per_year(base, **by_year):
    """series with per-year overrides: per_year(series(), op={2021: 37.5})"""
    rows = copy.deepcopy(base)
    for field, values in by_year.items():
        for r in rows:
            year = int(r['period_end'][:4])
            if year in values:
                r[field] = values[year]
    return rows


class FactorTests(unittest.TestCase):
    def test_all_four_factors_from_complete_rows(self):
        f = pf.compute_factors(series(), AS_OF)
        self.assertAlmostEqual(f['G'], (REV[2023] / REV[2020]) ** (1 / 3) - 1)
        self.assertAlmostEqual(f['C'], median(OCF[y] / REV[y] for y in (2021, 2022, 2023)))
        self.assertAlmostEqual(f['Q'], 0.08, places=12)
        self.assertAlmostEqual(f['B'], -140 / 360, places=12)
        self.assertEqual((f['missing'], f['reasons'], f['pit'], f['scope'], f['not_computed']), ([], {}, True, 'G,C,Q,B', ['V']))
        self.assertEqual((f['tolerated'], f['approximations'], f['periods_used']), ([], {}, ['2020-12-31', '2021-12-31', '2022-12-31', '2023-12-31']))

    def test_q_is_the_median_of_three_roics_using_the_current_year_operating_profit(self):
        rows = per_year(series(), op={2021: 37.5, 2022: 62.5, 2023: 50.0})
        self.assertAlmostEqual(pf.compute_factors(rows, AS_OF)['Q'], 0.08, places=12)
        rows = per_year(series(), op={2020: 1000.0, 2021: 37.5, 2022: 50.0, 2023: 100.0})
        self.assertAlmostEqual(pf.compute_factors(rows, AS_OF)['Q'], 0.08, places=12)        # the oldest year's op is not used

    def test_the_invested_capital_is_averaged_over_the_pair(self):
        rows = per_year(series(), equity={2020: 560.0}, op={2021: 60.0, 2022: 37.5, 2023: 62.5})     # IC 2020 = 700, others 500
        # pair (2020, 2021): 48 / ((700 + 500) / 2) = .08 is the median; with only the current IC it would be .096, with only the previous IC .0686
        self.assertAlmostEqual(pf.compute_factors(rows, AS_OF)['Q'], median([48 / 600, 30 / 500, 50 / 500]), places=12)
        self.assertAlmostEqual(pf.compute_factors(rows, AS_OF)['Q'], 0.08, places=12)

    def test_the_tax_rate_rule(self):
        loss = per_year(series(), pretax_income={2022: -10.0, 2023: -5.0}, income_tax_expense={2022: 3.0, 2023: 3.0})      # loss years: rate 0 (NOPAT = op), tax expense ignored
        f = pf.compute_factors(loss, AS_OF)
        self.assertAlmostEqual(f['Q'], median([40 / 500, 50 / 500, 50 / 500]), places=12)          # .10, not the .08 a normal rate would give
        self.assertEqual(f['approximations'], {'Q': ['tax_rate_zero_for_loss']})
        zero_pretax = per_year(series(), pretax_income={2022: 0.0, 2023: 0.0})
        self.assertAlmostEqual(pf.compute_factors(zero_pretax, AS_OF)['Q'], 0.10, places=12)
        edge = per_year(series(), income_tax_expense={2023: 45.0})                          # rate exactly 1 -> NOPAT 0, still usable
        self.assertAlmostEqual(pf.compute_factors(edge, AS_OF)['Q'], median([40 / 500, 40 / 500, 0.0]), places=12)
        no_tax = per_year(series(), income_tax_expense={2022: 0.0, 2023: 0.0})              # rate exactly 0, usable
        self.assertAlmostEqual(pf.compute_factors(no_tax, AS_OF)['Q'], median([40 / 500, 50 / 500, 50 / 500]), places=12)
        self.assertEqual(pf.compute_factors(no_tax, AS_OF)['approximations'], {})
        for tax in (-1.0, 46.0):
            with self.subTest(tax=tax):
                f = pf.compute_factors(per_year(series(), income_tax_expense={2022: tax}), AS_OF)
                self.assertEqual((f['Q'], f['reasons']['Q']), (None, ['tax_rate_unusable']))
        f = pf.compute_factors(series(drop=('income_tax_expense',)), AS_OF)
        self.assertEqual((f['Q'], f['reasons']['Q']), (None, ['missing:income_tax_expense']))
        f = pf.compute_factors(series(drop=('pretax_income',)), AS_OF)
        self.assertEqual((f['Q'], f['reasons']['Q']), (None, ['missing:pretax_income']))
        f = pf.compute_factors(series(drop=('op',)), AS_OF)
        self.assertEqual((f['Q'], f['reasons']['Q']), (None, ['missing:op']))
        f = pf.compute_factors(series(drop=('equity',)), AS_OF)
        self.assertEqual((f['Q'], f['B'], f['reasons']['Q'], f['reasons']['B']), (None, None, ['missing:equity'], ['missing:equity']))

    def test_approximations_are_recorded_only_for_factors_that_were_computed(self):
        rows = per_year(series(drop=('equity',)), pretax_income={2022: -10.0})        # a loss year (rate 0) but Q is unknown because equity is missing
        f = pf.compute_factors(rows, AS_OF)
        self.assertIsNone(f['Q']);self.assertEqual(f['approximations'], {})
        strict = pf.compute_factors(series(drop=('current_financial_assets',)), AS_OF)
        self.assertEqual(strict['approximations'], {})
        both = pf.compute_factors(per_year(series(drop=('current_financial_assets',)), pretax_income={2022: -10.0}), AS_OF, tolerated=pf.LIQUID_UNDERSTATEMENT)
        self.assertEqual(both['approximations'], {'Q': ['liquid_assets:current_financial_assets_absent', 'tax_rate_zero_for_loss'], 'B': ['liquid_assets:current_financial_assets_absent']})

    def test_the_tolerated_set_is_exactly_the_liquid_asset_understatements(self):
        self.assertEqual(pf.LIQUID_UNDERSTATEMENT, frozenset({'liquid_assets:current_financial_assets_absent', 'liquid_assets:short_term_financial_instruments_absent',
                                                             'current_financial_assets_absent', 'short_term_financial_instruments_absent'}))

    def test_a_partial_net_debt_is_tolerated_only_when_every_one_of_its_reasons_is(self):
        rows = series(drop=('current_financial_assets', 'short_term_financial_instruments'))           # two reasons
        one = frozenset({'liquid_assets:current_financial_assets_absent'})
        self.assertEqual((pf.compute_factors(rows, AS_OF, tolerated=one)['Q'], pf.compute_factors(rows, AS_OF, tolerated=one)['B']), (None, None))
        both = frozenset({'liquid_assets:current_financial_assets_absent', 'liquid_assets:short_term_financial_instruments_absent'})
        self.assertIsNotNone(pf.compute_factors(rows, AS_OF, tolerated=both)['Q'])
        for bad in ({1}, frozenset({None})):
            with self.subTest(bad=bad), self.assertRaises((TypeError, ValueError)):
                pf.compute_factors(series(), AS_OF, tolerated=bad)

    def test_zero_equity_and_zero_average_invested_capital_are_non_positive(self):
        zero_equity = pf.compute_factors(series(equity=0.0), AS_OF)
        self.assertEqual((zero_equity['B'], zero_equity['reasons']['B']), (None, ['non_positive_equity']))
        self.assertIsNotNone(zero_equity['Q'])                                              # IC = 0 + 140 is positive
        zero_capital = pf.compute_factors(series(equity=-140.0), AS_OF)                      # IC = -140 + 140 = 0 in every year
        self.assertEqual((zero_capital['Q'], zero_capital['reasons']['Q']), (None, ['non_positive_invested_capital']))

    def test_a_non_positive_average_invested_capital_makes_q_unknown(self):
        rows = series(equity=-300.0)                                                         # IC = -300 + 140 < 0
        f = pf.compute_factors(rows, AS_OF)
        self.assertEqual((f['Q'], f['reasons']['Q']), (None, ['non_positive_invested_capital']))
        self.assertEqual((f['B'], f['reasons']['B']), (None, ['non_positive_equity']))

    def test_net_debt_must_be_ok_unless_its_reasons_are_tolerated(self):
        lease_unknown = series(drop=('lease_total',))
        f = pf.compute_factors(lease_unknown, AS_OF)
        self.assertEqual((f['Q'], f['B']), (None, None))
        self.assertEqual((f['reasons']['Q'], f['reasons']['B']), (['net_debt:total_debt:lease_unconfirmed'], ['net_debt:total_debt:lease_unconfirmed']))
        self.assertEqual(pf.compute_factors(lease_unknown, AS_OF, tolerated=pf.LIQUID_UNDERSTATEMENT)['Q'], None)         # a lease gap is never tolerated by this set

    def test_a_missing_liquid_financial_asset_is_tolerated_only_on_request(self):
        rows = series(drop=('current_financial_assets',))
        strict = pf.compute_factors(rows, AS_OF)
        self.assertEqual((strict['Q'], strict['B']), (None, None))
        self.assertEqual(strict['reasons']['Q'], ['net_debt:liquid_assets:current_financial_assets_absent'])
        tolerant = pf.compute_factors(rows, AS_OF, tolerated=pf.LIQUID_UNDERSTATEMENT)
        self.assertAlmostEqual(tolerant['Q'], 0.08, places=12);self.assertAlmostEqual(tolerant['B'], -140 / 360, places=12)
        self.assertEqual(tolerant['approximations'], {'Q': ['liquid_assets:current_financial_assets_absent'], 'B': ['liquid_assets:current_financial_assets_absent']})
        self.assertEqual(tolerant['tolerated'], sorted(pf.LIQUID_UNDERSTATEMENT))
        both = pf.compute_factors(series(drop=('current_financial_assets', 'short_term_financial_instruments')), AS_OF, tolerated=pf.LIQUID_UNDERSTATEMENT)
        self.assertIsNotNone(both['Q'])

    def test_b_uses_only_the_latest_visible_row_while_q_needs_all_four_years(self):
        rows = per_year(series(), borrowings_current={2020: None})                         # net debt of 2020 unknown
        f = pf.compute_factors(rows, AS_OF)
        self.assertEqual(f['Q'], None);self.assertIn('net_debt:total_debt:missing:borrowings_current', f['reasons']['Q'])
        self.assertAlmostEqual(f['B'], -140 / 360, places=12)
        latest_bad = per_year(series(), borrowings_current={2023: None})
        f = pf.compute_factors(latest_bad, AS_OF)
        self.assertEqual((f['B'], f['reasons']['B']), (None, ['net_debt:total_debt:missing:borrowings_current']))

    def test_fewer_than_four_years_leave_q_g_c_unknown_but_not_b(self):
        f = pf.compute_factors(series(years=(2021, 2022, 2023)), AS_OF)
        self.assertEqual((f['G'], f['C'], f['Q']), (None, None, None))
        for key in ('G', 'C', 'Q'):
            self.assertEqual(f['reasons'][key], ['not_enough_years'])
        self.assertAlmostEqual(f['B'], -140 / 360, places=12)
        self.assertEqual(f['missing'], ['C', 'G', 'Q'])

    def test_only_rows_visible_at_the_date_are_used(self):
        rows = series(years=(2019, 2020, 2021, 2022, 2023))
        early = pf.compute_factors(rows, '2024-03-14')                                       # FY2023 becomes visible on 2024-03-15
        self.assertEqual(early['periods_used'], ['2019-12-31', '2020-12-31', '2021-12-31', '2022-12-31'])
        later = pf.compute_factors(rows, '2024-03-15')
        self.assertEqual(later['periods_used'][-1], '2023-12-31')
        none = pf.compute_factors(rows, '2019-06-30')
        self.assertEqual((none['B'], none['reasons']['B']), (None, ['no_annual_row']))

    def test_an_ambiguous_period_carries_no_values_and_follows_the_g_c_policy(self):
        def amb(year):
            return dict(company='AAA111', period_end=f'{year}-12-31', basis='CFS', available_at=f'{year + 1}-03-15', ambiguous=True, policy='next_session_after_rcept_dt_v1', rcept_nos=['a', 'b'])
        later = pf.compute_factors(series() + [amb(2024)], '2025-06-30')           # the newest period is ambiguous: the last four unambiguous periods are used
        self.assertEqual(later['ambiguous_periods'], ['2024-12-31'])
        self.assertEqual(later['periods_used'][-1], '2023-12-31')
        self.assertTrue(all(later[k] is not None for k in ('G', 'C', 'Q', 'B')))
        gap = pf.compute_factors(series()[:3] + [amb(2023)], AS_OF)                # the ambiguous period leaves only three years
        self.assertEqual((gap['G'], gap['C'], gap['Q']), (None, None, None))
        for key in ('G', 'C', 'Q'):
            self.assertIn('not_enough_years', gap['reasons'][key]);self.assertIn('ambiguous_period', gap['reasons'][key])
        self.assertIsNotNone(gap['B'])
        missing = pf.compute_factors(series(drop=('lease_total',)) + [amb(2024)], '2025-06-30')
        self.assertIn('ambiguous_period', missing['reasons']['Q']);self.assertIn('ambiguous_period', missing['reasons']['B'])

    def test_a_correction_is_a_separate_version_and_the_visible_one_is_used(self):
        original = series()
        corrected = dict(frow(2023), rcept_no='20240801000009', available_at='2024-08-02', equity=1000.0)
        before = pf.compute_factors(original + [corrected], '2024-07-31')
        after = pf.compute_factors(original + [corrected], '2024-08-02')
        self.assertAlmostEqual(before['B'], -140 / 360, places=12)
        self.assertAlmostEqual(after['B'], -140 / 1000, places=12)

    def test_the_input_is_not_modified_and_scope_checks_are_kept(self):
        rows = series();before = copy.deepcopy(rows)
        pf.compute_factors(rows, AS_OF, tolerated=pf.LIQUID_UNDERSTATEMENT)
        self.assertEqual(rows, before)
        with self.assertRaises(ValueError):
            pf.compute_factors(series() + [frow(2023, company='BBB222')], AS_OF)
        with self.assertRaises(ValueError):
            pf.compute_factors(series(), '2024-6-30')
        for bad in ('x', ['x'], 5, None):
            with self.subTest(bad=bad), self.assertRaises((TypeError, ValueError)):
                pf.compute_factors(series(), AS_OF, tolerated=bad)


def companies_with_increasing_factors(n=5):
    """Company i gets larger Q, G, C and B (a smaller net debt) the larger i is."""
    out = {}
    for i in range(n):
        code = f'C{i:05d}'
        rows = []
        for year in (2020, 2021, 2022, 2023):
            growth = 1.05 + 0.02 * i
            rows.append(frow(year, company=code, op=40.0 + 5 * i, borrowings_current=100.0 - 10 * i, revenue=100.0 * growth ** (year - 2020),
                             ocf=(10.0 + 2 * i) * growth ** (year - 2020)))
        out[code] = rows
    return out


class ScoreTests(unittest.TestCase):
    def test_scores_follow_the_weighted_percentiles(self):
        results = pf.pit_scores(companies_with_increasing_factors(), AS_OF)
        self.assertEqual([r['code'] for r in results], [f'C{i:05d}' for i in range(5)])
        for i, r in enumerate(results):
            with self.subTest(code=r['code']):
                self.assertAlmostEqual(r['S_pit_QGCB'], 100 * (i + 0.5) / 5, places=9)
                self.assertEqual(r['reasons']['S_pit_QGCB'], [])
                self.assertNotIn('quality_score', r);self.assertNotIn('S_long', r)
                self.assertEqual(r['scope'], 'G,C,Q,B')

    def test_each_factor_carries_its_own_weight_and_the_results_are_ordered_by_code(self):
        pool = {}
        for i in range(5):                                                                   # Q rises with i; G, C and B fall with i
            growth = 1.13 - 0.02 * i
            pool[f'C{i:05d}'] = [frow(y, company=f'C{i:05d}', op=40.0 + 5 * i, borrowings_current=60.0 + 10 * i, revenue=100.0 * growth ** (y - 2020),
                                      ocf=(18.0 - 2 * i) * growth ** (y - 2020)) for y in (2020, 2021, 2022, 2023)]
        ordered = dict(reversed(list(pool.items())))
        results = pf.pit_scores(ordered, AS_OF)
        self.assertEqual([r['code'] for r in results], sorted(pool))
        for i, r in enumerate(results):
            q, other = (i + 0.5) / 5, (4 - i + 0.5) / 5
            self.assertAlmostEqual(r['S_pit_QGCB'], 100 * (0.30 * q + 0.25 * other + 0.20 * other + 0.10 * other) / 0.85, places=9)

    def test_a_small_pool_and_missing_factors_are_named(self):
        small = pf.pit_scores(companies_with_increasing_factors(4), AS_OF)
        self.assertTrue(all(r['S_pit_QGCB'] is None and r['reasons']['S_pit_QGCB'] == ['pool_too_small'] for r in small))
        self.assertTrue(all(r['S_pit_QGCB'] is not None for r in pf.pit_scores(companies_with_increasing_factors(4), AS_OF, minimum=4)))
        pool = companies_with_increasing_factors()
        pool['C00002'] = series(company='C00002', drop=('lease_total',))
        results = {r['code']: r for r in pf.pit_scores(pool, AS_OF)}
        self.assertIsNone(results['C00002']['S_pit_QGCB']);self.assertEqual(results['C00002']['reasons']['S_pit_QGCB'], ['factor_missing'])
        self.assertTrue(all(results[c]['S_pit_QGCB'] is None for c in ('C00000', 'C00001', 'C00003', 'C00004')))     # Q and B pools have only four members now

    def test_tolerated_reasons_are_passed_through(self):
        pool = {code: [dict(r, current_financial_assets=None) for r in rows] for code, rows in companies_with_increasing_factors().items()}
        pool = {code: [{k: v for k, v in r.items() if k != 'current_financial_assets'} for r in rows] for code, rows in pool.items()}
        strict = pf.pit_scores(pool, AS_OF)
        self.assertTrue(all(r['S_pit_QGCB'] is None for r in strict))
        tolerant = pf.pit_scores(pool, AS_OF, tolerated=pf.LIQUID_UNDERSTATEMENT)
        self.assertTrue(all(r['S_pit_QGCB'] is not None for r in tolerant))
        self.assertEqual(tolerant[0]['approximations']['Q'], ['liquid_assets:current_financial_assets_absent'])

    def test_argument_checks_and_the_input_is_not_modified(self):
        pool = companies_with_increasing_factors();before = copy.deepcopy(pool)
        pf.pit_scores(pool, AS_OF)
        self.assertEqual(pool, before)
        for bad in ({}, None, [1]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pf.pit_scores(bad, AS_OF)
        for bad in (0, 1.5, True, '5'):
            with self.subTest(minimum=bad), self.assertRaises(ValueError):
                pf.pit_scores(pool, AS_OF, minimum=bad)
        with self.assertRaises(ValueError):
            pf.pit_scores({'ZZZ999': series()}, AS_OF)                                       # company code differs from the rows
        with self.assertRaises(ValueError):
            pf.pit_scores({1: series()}, AS_OF)


class StalenessTests(unittest.TestCase):
    def test_a_stale_company_is_left_out_of_every_pool_and_the_others_are_unchanged(self):
        pool = companies_with_increasing_factors()
        baseline = {r['code']: r for r in pf.pit_scores(pool, AS_OF)}
        with_stale = dict(pool, STALE1=series(years=(2018, 2019, 2020, 2021), company='STALE1'))
        results = {r['code']: r for r in pf.pit_scores(with_stale, AS_OF)}
        self.assertEqual((results['STALE1']['S_pit_QGCB'], results['STALE1']['reasons']['S_pit_QGCB'], results['STALE1']['stale'], results['STALE1']['latest_period']),
                         (None, ['stale_period'], True, '2021-12-31'))
        for code in pool:
            with self.subTest(code=code):
                self.assertAlmostEqual(results[code]['S_pit_QGCB'], baseline[code]['S_pit_QGCB'], places=12)
                self.assertEqual((results[code]['stale'], results[code]['latest_period']), (False, '2023-12-31'))

    def test_a_stale_company_does_not_help_a_small_pool(self):
        pool = companies_with_increasing_factors(4)
        pool['STALE1'] = series(years=(2018, 2019, 2020, 2021), company='STALE1')
        results = {r['code']: r for r in pf.pit_scores(pool, AS_OF)}
        self.assertTrue(all(results[c]['S_pit_QGCB'] is None and results[c]['reasons']['S_pit_QGCB'] == ['pool_too_small'] for c in pool if c != 'STALE1'))

    def test_the_default_limit_is_460_days_inclusive(self):
        from datetime import date, timedelta
        rows = series()                                                                      # latest period 2023-12-31
        last = date(2023, 12, 31)
        for days, stale in ((460, False), (461, True)):
            with self.subTest(days=days):
                result = pf.pit_scores({'AAA111': rows}, (last + timedelta(days=days)).isoformat())[0]
                self.assertEqual(result['stale'], stale)
                self.assertEqual(result['reasons']['S_pit_QGCB'] == ['stale_period'], stale)

    def test_the_limit_can_be_changed_or_switched_off(self):
        pool = companies_with_increasing_factors()
        everyone = pf.pit_scores(pool, AS_OF, max_staleness_days=30)                         # 2023-12-31 is 182 days before 2024-06-30
        self.assertTrue(all(r['stale'] and r['S_pit_QGCB'] is None and r['reasons']['S_pit_QGCB'] == ['stale_period'] for r in everyone))
        stale_pool = dict(pool, STALE1=series(years=(2018, 2019, 2020, 2021), company='STALE1'))
        off = {r['code']: r for r in pf.pit_scores(stale_pool, AS_OF, max_staleness_days=None)}
        self.assertFalse(off['STALE1']['stale']);self.assertEqual(off['STALE1']['latest_period'], '2021-12-31')
        self.assertIsNotNone(off['STALE1']['S_pit_QGCB'])                                    # it is ranked like any other company

    def test_a_company_without_a_visible_row_is_missing_not_stale(self):
        result = pf.pit_scores({'AAA111': series()}, '2019-06-30')[0]
        self.assertEqual((result['stale'], result['latest_period']), (False, None))
        self.assertEqual(result['reasons']['S_pit_QGCB'], ['factor_missing'])

    def test_the_limit_is_validated(self):
        for bad in (0, -1, 1.5, True, '460'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pf.pit_scores({'AAA111': series()}, AS_OF, max_staleness_days=bad)

    def test_compute_factors_reports_the_latest_period(self):
        self.assertEqual(pf.compute_factors(series(), AS_OF)['latest_period'], '2023-12-31')
        self.assertIsNone(pf.compute_factors(series(), '2019-06-30')['latest_period'])


if __name__ == '__main__':unittest.main()
