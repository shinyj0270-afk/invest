"""Contract for `investment/pit_quality.py`: a PARTIAL point-in-time quality score from PIT annual rows (`pit_annual.project` output).

Only G (3-year revenue CAGR) and C (median ocf/revenue over 3 years) can be built from the pilot fields; Q needs debt and a verified tax rate,
V and B read untimestamped metrics. The result is therefore a separate `S_pit_GC`, never `quality_score` / `S_long`, and it names what is missing.
"""
import copy
import unittest
from statistics import median
from investment import pit_quality as pq

REV = {2019: 90.0, 2020: 100.0, 2021: 110.0, 2022: 121.0, 2023: 133.1}
OCF = {2019: 9.0, 2020: 10.0, 2021: 12.0, 2022: 12.1, 2023: 20.0}


def row(year, revenue=None, ocf=None, *, company='AAA111', basis='CFS', available=None, rcept=None, revenue_key=True):
    r = dict(company=company, period_end=f'{year}-12-31', basis=basis, available_at=available or f'{year + 1}-03-15', rcept_no=rcept or f'{year + 1}0314000001',
             rcept_dt=f'{year + 1}-03-14', policy='next_session_after_rcept_dt_v1', op=5.0, equity=50.0, cash=5.0)
    if revenue_key:r['revenue'] = REV[year] if revenue is None else revenue
    r['ocf'] = OCF[year] if ocf is None else ocf
    return r


def series(**kw):
    return [row(y, **kw) for y in (2020, 2021, 2022, 2023)]


def ambiguous(year, available=None, company='AAA111'):
    return dict(company=company, period_end=f'{year}-12-31', basis='CFS', available_at=available or f'{year + 1}-03-15', ambiguous=True,
                policy='next_session_after_rcept_dt_v1', rcept_nos=[f'{year + 1}0314000001', f'{year + 1}0314000002'])


AS_OF = '2024-06-30'


class FactorTests(unittest.TestCase):
    def test_g_and_c_follow_the_same_rules_as_the_existing_quality_factors(self):
        f = pq.partial_factors(series(), AS_OF)
        self.assertAlmostEqual(f['G'], (REV[2023] / REV[2020]) ** (1 / 3) - 1)
        self.assertAlmostEqual(f['C'], median(OCF[y] / REV[y] for y in (2021, 2022, 2023)))
        self.assertEqual((f['pit'], f['scope']), (True, 'G,C only'))
        self.assertEqual(f['not_computed'], ['Q', 'V', 'B'])
        self.assertEqual(f['missing'], [])
        self.assertEqual(f['periods_used'], ['2020-12-31', '2021-12-31', '2022-12-31', '2023-12-31'])

    def test_a_row_is_visible_from_its_available_at_day_and_not_before(self):
        rows = series()
        on_day = pq.partial_factors(rows, '2024-03-15')
        self.assertIsNotNone(on_day['G'])
        before = pq.partial_factors(rows, '2024-03-14')
        self.assertEqual((before['G'], before['C']), (None, None));self.assertEqual(sorted(before['missing']), ['C', 'G'])
        self.assertIn('not_enough_years', before['reasons']['G'])

    def test_a_correction_replaces_a_period_only_from_its_own_available_at(self):
        corrected = row(2023, revenue=140.0, available='2024-09-01', rcept='20240830000009')
        rows = series() + [corrected]
        early = pq.partial_factors(rows, '2024-08-31');late = pq.partial_factors(rows, '2024-09-01')
        self.assertAlmostEqual(early['G'], (133.1 / 100) ** (1 / 3) - 1);self.assertAlmostEqual(late['G'], (140.0 / 100) ** (1 / 3) - 1)

    def test_four_consecutive_december_years_are_required(self):
        gap = [row(2019), row(2021), row(2022), row(2023)]
        f = pq.partial_factors(gap, AS_OF)
        self.assertEqual((f['G'], f['C']), (None, None));self.assertIn('not_enough_years', f['reasons']['G'])
        self.assertEqual(pq.partial_factors(series()[1:], AS_OF)['G'], None)

    def test_a_missing_or_unusable_value_blocks_only_the_factor_that_needs_it(self):
        no_ocf = series();no_ocf[2] = {k: v for k, v in no_ocf[2].items() if k != 'ocf'}
        f = pq.partial_factors(no_ocf, AS_OF)
        self.assertIsNotNone(f['G']);self.assertIsNone(f['C']);self.assertEqual(f['missing'], ['C']);self.assertIn('missing_value', f['reasons']['C'])
        negative = series();negative[0] = row(2020, revenue=-5.0)
        f = pq.partial_factors(negative, AS_OF)
        self.assertIsNone(f['G']);self.assertIn('unusable_value', f['reasons']['G'])
        zero_rev = pq.partial_factors([row(2020), row(2021), row(2022), row(2023, revenue=0.0)], AS_OF)
        self.assertIsNone(zero_rev['G']);self.assertIsNone(zero_rev['C']);self.assertIn('unusable_value', zero_rev['reasons']['G']);self.assertNotIn('missing_value', zero_rev['reasons']['G'])
        nan = series();nan[3] = row(2023, ocf=float('nan'))
        self.assertIsNone(pq.partial_factors(nan, AS_OF)['C'])
        flag = series();flag[3] = row(2023, revenue=True)
        self.assertIsNone(pq.partial_factors(flag, AS_OF)['G'])

    def test_an_ambiguous_latest_row_makes_that_period_unknown_not_guessed(self):
        rows = series()[:3] + [ambiguous(2023)]
        f = pq.partial_factors(rows, AS_OF)
        self.assertEqual((f['G'], f['C']), (None, None));self.assertEqual(f['ambiguous_periods'], ['2023-12-31'])
        self.assertIn('ambiguous_period', f['reasons']['G']);self.assertIn('not_enough_years', f['reasons']['G']);self.assertEqual(f['periods_used'], [])
        # an ambiguity that only becomes visible later does not affect an earlier as_of
        late = [dict(r) for r in series()] + [ambiguous(2023, available='2024-09-01')]
        self.assertIsNotNone(pq.partial_factors(late, '2024-08-31')['G'])
        self.assertEqual(pq.partial_factors(late, '2024-09-01')['ambiguous_periods'], ['2023-12-31'])
        # a later, unambiguous correction after an ambiguity resolves the period
        fixed = rows + [row(2023, available='2024-10-01', rcept='20241001000001')]
        self.assertIsNotNone(pq.partial_factors(fixed, '2024-10-01')['G'])

    def test_rows_of_other_companies_bases_or_wrong_shape_are_refused(self):
        with self.assertRaises(ValueError):
            pq.partial_factors(series() + [row(2023, company='BBB222')], AS_OF)
        with self.assertRaises(ValueError):
            pq.partial_factors(series() + [row(2023, basis='OFS')], AS_OF)
        for bad in (None, 'x', [None], [{'company': 'AAA111'}], 5):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pq.partial_factors(bad, AS_OF)
        for as_of in (None, '2024-6-30', '20240630', 20240630, '2024-13-01'):
            with self.subTest(as_of=as_of), self.assertRaises(ValueError):
                pq.partial_factors(series(), as_of)

    def test_inputs_are_not_modified_and_an_empty_list_gives_nothing_computed(self):
        rows = series();before = copy.deepcopy(rows);pq.partial_factors(rows, AS_OF);self.assertEqual(rows, before)
        f = pq.partial_factors([], AS_OF)
        self.assertEqual((f['G'], f['C'], f['periods_used']), (None, None, []))


def company(code, g_growth, c_ratio):
    """Four years with a given constant revenue growth and ocf/revenue ratio."""
    revenue = [100 * (1 + g_growth) ** i for i in range(4)]
    return [dict(row(2020 + i, revenue=revenue[i], ocf=revenue[i] * c_ratio, company=code)) for i in range(4)]


class ScoreTests(unittest.TestCase):
    def pool(self):
        return {f'C{i}': company(f'C{i}', 0.05 * (i + 1), 0.04 * (i + 1)) for i in range(5)}

    def test_the_score_is_a_weighted_percentile_of_g_and_c_with_renormalised_weights(self):
        result = {r['code']: r for r in pq.partial_scores(self.pool(), AS_OF)}
        self.assertEqual(sorted(result), ['C0', 'C1', 'C2', 'C3', 'C4'])
        for i in range(5):
            p = (i + 0.5) / 5                                              # strictly increasing in both factors
            expected = 100 * (0.25 * p + 0.20 * p) / 0.45
            self.assertAlmostEqual(result[f'C{i}']['S_pit_GC'], expected)
        top = result['C4'];self.assertEqual((top['pit'], top['scope'], top['not_computed']), (True, 'G,C only', ['Q', 'V', 'B']))
        for r in result.values():
            self.assertNotIn('quality_score', r);self.assertNotIn('S_long', r)

    def test_mixed_ranks_use_each_factor_separately(self):
        pool = self.pool()
        pool['C0'] = company('C0', 0.50, 0.01)                              # best growth, worst cash conversion
        result = {r['code']: r for r in pq.partial_scores(pool, AS_OF)}
        p_g, p_c = 4.5 / 5, 0.5 / 5
        self.assertAlmostEqual(result['C0']['S_pit_GC'], 100 * (0.25 * p_g + 0.20 * p_c) / 0.45)

    def test_a_pool_below_the_minimum_or_a_company_missing_a_factor_gets_no_score_but_keeps_its_factors(self):
        small = {k: v for k, v in list(self.pool().items())[:3]}
        for r in pq.partial_scores(small, AS_OF):
            self.assertIsNone(r['S_pit_GC']);self.assertIsNotNone(r['G']);self.assertIn('pool_too_small', r['reasons']['S_pit_GC'])
        explicit = {r['code']: r for r in pq.partial_scores(small, AS_OF, minimum=1)}
        self.assertIsNotNone(explicit['C0']['S_pit_GC'])
        pool = self.pool();pool['C2'] = [dict(r) for r in pool['C2']];del pool['C2'][1]['ocf']
        result = {r['code']: r for r in pq.partial_scores(pool, AS_OF)}
        self.assertIsNone(result['C2']['S_pit_GC']);self.assertEqual(result['C2']['missing'], ['C'])
        self.assertIn('factor_missing', result['C2']['reasons']['S_pit_GC'])
        self.assertIsNone(result['C0']['S_pit_GC'])                         # only 4 companies have C: that factor's pool is below the minimum for everyone
        self.assertIn('pool_too_small', result['C0']['reasons']['S_pit_GC'])

    def test_the_pool_only_counts_companies_that_have_the_factor(self):
        pool = self.pool();pool['C5'] = company('C5', 0.01, 0.01)
        pool['C5'] = [dict(r) for r in pool['C5']];del pool['C5'][0]['revenue']
        result = {r['code']: r for r in pq.partial_scores(pool, AS_OF)}
        self.assertEqual(result['C5']['reasons']['S_pit_GC'], ['factor_missing'])                    # the G pool has exactly `minimum` members: not too small
        self.assertIsNone(result['C5']['S_pit_GC']);self.assertIsNotNone(result['C0']['S_pit_GC'])      # five companies still have both factors

    def test_a_factor_pool_exactly_at_the_minimum_is_not_reported_as_too_small(self):
        pool = self.pool();pool['C2'] = [dict(r) for r in pool['C2']];del pool['C2'][1]['ocf']              # C2 has G but lacks C
        for code in ('E1', 'E2'):                                                                         # extras with C but without G
            rows = [dict(r) for r in company(code, 0.30, 0.30)];del rows[0]['revenue'];pool[code] = rows
        result = {r['code']: r for r in pq.partial_scores(pool, AS_OF)}                                   # G pool = 5 (the minimum), C pool = 6
        self.assertEqual(result['C2']['reasons']['S_pit_GC'], ['factor_missing'])
        self.assertIsNone(result['C2']['S_pit_GC']);self.assertIsNone(result['E1']['S_pit_GC'])

    def test_the_code_key_must_match_the_rows_and_invalid_arguments_are_refused(self):
        pool = self.pool();pool['WRONG'] = pool.pop('C0')
        with self.assertRaises(ValueError):
            pq.partial_scores(pool, AS_OF)
        for bad in (None, [], {}, {'C0': 'x'}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pq.partial_scores(bad, AS_OF)
        for minimum in (0, -1, True, 1.5, None):
            with self.subTest(minimum=minimum), self.assertRaises(ValueError):
                pq.partial_scores(self.pool(), AS_OF, minimum=minimum)

    def test_ties_share_the_mid_rank_like_the_existing_percentile(self):
        pool = {f'C{i}': company(f'C{i}', 0.10, 0.10) for i in range(5)}
        for r in pq.partial_scores(pool, AS_OF):
            self.assertAlmostEqual(r['S_pit_GC'], 50.0)


if __name__ == '__main__':
    unittest.main()
