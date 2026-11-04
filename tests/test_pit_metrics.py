"""Contract for `investment/pit_metrics.py`: derived financial metrics from ONE annual PIT row (design: docs/review/design_financial_concepts_NICE_2026-11-04.md, section 7).

`compute_metrics(values) -> dict` maps every name in `METRIC_NAMES` to `dict(value, status, reasons)`:
  status 'ok'      the value uses only confirmed inputs
  status 'partial' the value is computed but an input is known to be incomplete (a lower or upper bound); `reasons` says which
  status 'unknown' value is None; `reasons` says why
`reasons` is a sorted list of unique strings. Nothing missing is ever replaced by 0 unless the rule below says so. Inputs: a dict of PIT value fields (KRW); keys that are not
numbers (None, bool, NaN, inf, str) count as missing, unknown keys are ignored, the input is never modified. Percent metrics are x100 (like NICE), multiples are plain ratios.

Rules (status combination: unknown if any needed input is unknown, else partial if any is partial, else ok; reasons are the union, prefixed with the input name when inherited):
total_debt     borrowings_current + borrowings_noncurrent (BOTH needed: a missing side is unknown, reason `missing:<field>`) + leases:
                 lease_total when present; else lease_current + lease_noncurrent when both; one of the two -> partial `lease_incomplete`; none -> partial `lease_unconfirmed` (borrowings only).
                 lease_total together with BOTH current and non-current that disagree by more than 1% of lease_total -> unknown `lease_inconsistent`; if they agree lease_total is used.
liquid_assets  cash + short_term_financial_instruments + current_financial_assets (the confirmed definition: 현금및현금성자산 + 단기금융상품 + 유동금융자산); cash missing -> unknown `missing:cash`;
                 each of the other two missing -> partial `short_term_financial_instruments_absent` / `current_financial_assets_absent` (counted as 0, so net debt is an upper bound).
                 `current_financial_assets` is not produced by the parser yet, so with real rows net debt is always partial until it is.
net_debt       total_debt - liquid_assets (inherits both).
ebitda         op + D&A; needs op (`missing:op`). D&A = da_total when present (ok); else depreciation + amortization (+ rou_depreciation when present), both required (else unknown `missing:da`);
                 on that path, rou_depreciation absent while any lease amount is positive -> partial `rou_depreciation_absent`.
fcf            ocf - capex_tangible - capex_intangible; ocf and capex_tangible needed (`missing:<field>`); capex_intangible absent -> partial `capex_intangible_absent` (treated as 0).
debt_ratio_pct total_liabilities / equity x100; both needed; equity <= 0 -> unknown `non_positive_equity`.
debt_to_assets_pct total_debt / total_assets x100 (total_assets > 0 else unknown `non_positive_total_assets`).
debt_to_capital_pct total_debt / (total_debt + equity) x100 (denominator > 0 else unknown `non_positive_capital`).
ebit_margin_pct op / revenue x100 ; ebitda_margin_pct ebitda / revenue x100 ; revenue <= 0 -> unknown `non_positive_revenue`.
roa_op_pct     op / total_assets x100.   roe_pct net_income_total / equity x100 (equity <= 0 -> unknown `non_positive_equity`).
debt_to_ebitda total_debt / ebitda ; net_debt_to_ebitda net_debt / ebitda ; ebitda <= 0 -> unknown `non_positive_ebitda`.
ebitda_to_finance_costs ebitda / finance_costs ; ebitda_to_interest ebitda / interest_expense ; a denominator <= 0 -> unknown `non_positive_finance_costs` / `non_positive_interest_expense`.
ocf_to_debt_pct ocf / total_debt x100 ; fcf_to_debt_pct fcf / total_debt x100 ; total_debt <= 0 -> unknown `non_positive_total_debt`.
short_term_debt_ratio_pct (borrowings_current + lease_current) / total_debt x100; lease_current absent while the lease is not known to be zero -> partial `lease_current_absent`.
"""
import copy
import math
import unittest
from investment import pit_metrics
from investment.pit_metrics import compute_metrics, METRIC_NAMES

FULL = dict(revenue=1000.0, op=100.0, ocf=150.0, equity=500.0, cash=60.0, total_assets=2000.0, total_liabilities=1500.0, short_term_financial_instruments=40.0,
            borrowings_current=300.0, borrowings_noncurrent=400.0, lease_current=20.0, lease_noncurrent=60.0, finance_costs=50.0, interest_expense=40.0,
            pretax_income=90.0, income_tax_expense=20.0, net_income_total=70.0, depreciation=80.0, amortization=10.0, rou_depreciation=10.0,
            capex_tangible=90.0, capex_intangible=10.0, dividends_paid=5.0, current_financial_assets=0.0)
EXPECT = dict(total_debt=780.0, liquid_assets=100.0, net_debt=680.0, ebitda=200.0, fcf=50.0, debt_ratio_pct=300.0, debt_to_assets_pct=39.0,
              debt_to_capital_pct=780 / 1280 * 100, ebit_margin_pct=10.0, ebitda_margin_pct=20.0, roa_op_pct=5.0, roe_pct=14.0, debt_to_ebitda=3.9,
              net_debt_to_ebitda=3.4, ebitda_to_finance_costs=4.0, ebitda_to_interest=5.0, ocf_to_debt_pct=150 / 780 * 100, fcf_to_debt_pct=50 / 780 * 100,
              short_term_debt_ratio_pct=320 / 780 * 100)


def without(*keys, **over):
    values = {k: v for k, v in FULL.items() if k not in keys}
    values.update(over)
    return values


def only(result, name):
    return result[name]


class FullInputTests(unittest.TestCase):
    def test_every_metric_is_computed_ok_from_a_complete_row(self):
        result = compute_metrics(FULL)
        self.assertEqual(list(result), list(METRIC_NAMES))
        self.assertEqual(set(result), set(EXPECT))
        for name, expected in EXPECT.items():
            with self.subTest(metric=name):
                self.assertAlmostEqual(result[name]['value'], expected, places=9)
                self.assertEqual((result[name]['status'], result[name]['reasons']), ('ok', []))

    def test_the_input_is_not_modified_and_unknown_keys_are_ignored(self):
        values = dict(FULL, something_else=5.0)
        before = copy.deepcopy(values)
        compute_metrics(values)
        self.assertEqual(values, before)
        self.assertEqual(compute_metrics(values)['total_debt']['value'], 780.0)

    def test_non_numbers_count_as_missing(self):
        for bad in (None, True, float('nan'), float('inf'), '300', [1]):
            with self.subTest(bad=bad):
                result = compute_metrics(without(borrowings_current=bad))
                self.assertEqual(result['total_debt'], dict(value=None, status='unknown', reasons=['missing:borrowings_current']))

    def test_an_empty_row_makes_every_metric_unknown(self):
        result = compute_metrics({})
        for name in METRIC_NAMES:
            with self.subTest(metric=name):
                self.assertIsNone(result[name]['value']);self.assertEqual(result[name]['status'], 'unknown');self.assertTrue(result[name]['reasons'])


class DebtTests(unittest.TestCase):
    def test_a_missing_borrowing_side_is_unknown_and_never_zero(self):
        for key in ('borrowings_current', 'borrowings_noncurrent'):
            with self.subTest(key=key):
                self.assertEqual(compute_metrics(without(key))['total_debt'], dict(value=None, status='unknown', reasons=[f'missing:{key}']))
        both = compute_metrics(without('borrowings_current', 'borrowings_noncurrent'))['total_debt']
        self.assertEqual(both['reasons'], ['missing:borrowings_current', 'missing:borrowings_noncurrent'])

    def test_leases_are_added_by_total_or_by_parts_and_missing_leases_make_the_value_partial(self):
        total = compute_metrics(without('lease_current', 'lease_noncurrent', lease_total=100.0))['total_debt']
        self.assertEqual((total['value'], total['status'], total['reasons']), (800.0, 'ok', []))
        one = compute_metrics(without('lease_noncurrent'))['total_debt']
        self.assertEqual((one['value'], one['status'], one['reasons']), (720.0, 'partial', ['lease_incomplete']))
        none = compute_metrics(without('lease_current', 'lease_noncurrent'))['total_debt']
        self.assertEqual((none['value'], none['status'], none['reasons']), (700.0, 'partial', ['lease_unconfirmed']))

    def test_lease_total_and_parts_must_agree_within_one_percent(self):
        agree = compute_metrics(dict(FULL, lease_total=80.5))['total_debt']
        self.assertEqual((agree['value'], agree['status']), (780.5, 'ok'))
        edge = compute_metrics(dict(FULL, lease_total=80.8))['total_debt']
        self.assertEqual(edge['status'], 'ok')
        over = compute_metrics(dict(FULL, lease_total=81.5))['total_debt']
        self.assertEqual((over['value'], over['reasons']), (None, ['lease_inconsistent']))
        exact = compute_metrics(dict(FULL, lease_current=49.0, lease_noncurrent=50.0, lease_total=100.0))['total_debt']
        self.assertEqual((exact['value'], exact['status']), (800.0, 'ok'))
        bad = compute_metrics(dict(FULL, lease_total=90.0))['total_debt']
        self.assertEqual((bad['value'], bad['status'], bad['reasons']), (None, 'unknown', ['lease_inconsistent']))

    def test_liquid_assets_and_net_debt(self):
        no_stf = compute_metrics(without('short_term_financial_instruments'))
        self.assertEqual((no_stf['liquid_assets']['value'], no_stf['liquid_assets']['status'], no_stf['liquid_assets']['reasons']),
                         (60.0, 'partial', ['short_term_financial_instruments_absent']))
        self.assertEqual((no_stf['net_debt']['value'], no_stf['net_debt']['status']), (720.0, 'partial'))
        self.assertEqual(no_stf['net_debt']['reasons'], ['liquid_assets:short_term_financial_instruments_absent'])
        no_cash = compute_metrics(without('cash'))
        self.assertEqual(no_cash['liquid_assets'], dict(value=None, status='unknown', reasons=['missing:cash']))
        self.assertEqual((no_cash['net_debt']['value'], no_cash['net_debt']['status']), (None, 'unknown'))
        self.assertIn('liquid_assets:missing:cash', no_cash['net_debt']['reasons'])

    def test_current_financial_assets_are_added_and_their_absence_makes_liquid_assets_and_net_debt_partial(self):
        with_cfa = compute_metrics(dict(FULL, current_financial_assets=25.0))
        self.assertEqual((with_cfa['liquid_assets']['value'], with_cfa['liquid_assets']['status']), (125.0, 'ok'))
        self.assertEqual((with_cfa['net_debt']['value'], with_cfa['net_debt']['status']), (655.0, 'ok'))
        absent = compute_metrics(without('current_financial_assets'))
        self.assertEqual((absent['liquid_assets']['value'], absent['liquid_assets']['status'], absent['liquid_assets']['reasons']), (100.0, 'partial', ['current_financial_assets_absent']))
        self.assertEqual((absent['net_debt']['value'], absent['net_debt']['status'], absent['net_debt']['reasons']), (680.0, 'partial', ['liquid_assets:current_financial_assets_absent']))
        self.assertEqual((absent['net_debt_to_ebitda']['status'], absent['net_debt_to_ebitda']['reasons']), ('partial', ['liquid_assets:current_financial_assets_absent']))      # the origin prefix is kept, not stacked
        both = compute_metrics(without('current_financial_assets', 'short_term_financial_instruments'))['liquid_assets']
        self.assertEqual((both['value'], both['reasons']), (60.0, ['current_financial_assets_absent', 'short_term_financial_instruments_absent']))
        for bad in (None, True, float('nan')):
            with self.subTest(bad=bad):
                self.assertEqual(compute_metrics(dict(FULL, current_financial_assets=bad))['liquid_assets']['reasons'], ['current_financial_assets_absent'])

    def test_partial_and_unknown_inputs_propagate_with_the_input_name(self):
        result = compute_metrics(without('lease_current', 'lease_noncurrent'))
        for name, base in (('debt_to_assets_pct', 700 / 2000 * 100), ('debt_to_capital_pct', 700 / 1200 * 100), ('ocf_to_debt_pct', 150 / 700 * 100), ('debt_to_ebitda', 3.5)):
            with self.subTest(metric=name):
                self.assertAlmostEqual(result[name]['value'], base, places=9)
                self.assertEqual((result[name]['status'], result[name]['reasons']), ('partial', ['total_debt:lease_unconfirmed']))
        unknown = compute_metrics(without('borrowings_noncurrent'))
        for name in ('debt_to_assets_pct', 'debt_to_capital_pct', 'ocf_to_debt_pct', 'fcf_to_debt_pct', 'debt_to_ebitda', 'net_debt', 'net_debt_to_ebitda', 'short_term_debt_ratio_pct'):
            with self.subTest(metric=name):
                self.assertEqual((unknown[name]['value'], unknown[name]['status']), (None, 'unknown'))
                self.assertIn('total_debt:missing:borrowings_noncurrent', unknown[name]['reasons'])


class EbitdaAndFlowTests(unittest.TestCase):
    def test_da_total_wins_and_the_component_path_needs_depreciation_and_amortisation(self):
        tagged = compute_metrics(dict(FULL, da_total=150.0))['ebitda']
        self.assertEqual((tagged['value'], tagged['status'], tagged['reasons']), (250.0, 'ok', []))
        only_tag = compute_metrics(without('depreciation', 'amortization', 'rou_depreciation', da_total=150.0))['ebitda']
        self.assertEqual((only_tag['value'], only_tag['status']), (250.0, 'ok'))
        for key in ('depreciation', 'amortization'):
            with self.subTest(key=key):
                self.assertEqual(compute_metrics(without(key))['ebitda'], dict(value=None, status='unknown', reasons=['missing:da']))
        self.assertEqual(compute_metrics(without('op'))['ebitda'], dict(value=None, status='unknown', reasons=['missing:op']))

    def test_rou_depreciation_is_added_when_present_and_its_absence_matters_only_with_leases(self):
        absent = compute_metrics(without('rou_depreciation'))['ebitda']
        self.assertEqual((absent['value'], absent['status'], absent['reasons']), (190.0, 'partial', ['rou_depreciation_absent']))
        no_lease = compute_metrics(without('rou_depreciation', 'lease_current', 'lease_noncurrent'))['ebitda']
        self.assertEqual((no_lease['value'], no_lease['status']), (190.0, 'ok'))
        zero_lease = compute_metrics(without('rou_depreciation', lease_current=0.0, lease_noncurrent=0.0))['ebitda']
        self.assertEqual(zero_lease['status'], 'ok')
        total_only = compute_metrics(without('rou_depreciation', 'lease_current', 'lease_noncurrent', lease_total=30.0))['ebitda']
        self.assertEqual(total_only['status'], 'partial')

    def test_fcf_needs_ocf_and_tangible_capex_and_an_absent_intangible_capex_is_partial(self):
        for key in ('ocf', 'capex_tangible'):
            with self.subTest(key=key):
                self.assertEqual(compute_metrics(without(key))['fcf'], dict(value=None, status='unknown', reasons=[f'missing:{key}']))
        partial = compute_metrics(without('capex_intangible'))['fcf']
        self.assertEqual((partial['value'], partial['status'], partial['reasons']), (60.0, 'partial', ['capex_intangible_absent']))
        self.assertEqual(compute_metrics(without('capex_intangible'))['fcf_to_debt_pct']['reasons'], ['fcf:capex_intangible_absent'])

    def test_dividends_and_disposals_are_not_part_of_fcf(self):
        self.assertEqual(compute_metrics(dict(FULL, dividends_paid=999.0))['fcf']['value'], 50.0)


class RatioGuardTests(unittest.TestCase):
    def test_non_positive_denominators_are_unknown_with_their_reason(self):
        cases = [('debt_ratio_pct', dict(equity=0.0), 'non_positive_equity'), ('debt_ratio_pct', dict(equity=-5.0), 'non_positive_equity'),
                 ('roe_pct', dict(equity=-1.0), 'non_positive_equity'), ('debt_to_assets_pct', dict(total_assets=0.0), 'non_positive_total_assets'),
                 ('ebit_margin_pct', dict(revenue=0.0), 'non_positive_revenue'), ('ebitda_margin_pct', dict(revenue=-1.0), 'non_positive_revenue'),
                 ('roa_op_pct', dict(total_assets=-1.0), 'non_positive_total_assets'), ('ebitda_to_finance_costs', dict(finance_costs=0.0), 'non_positive_finance_costs'),
                 ('ebitda_to_interest', dict(interest_expense=0.0), 'non_positive_interest_expense'), ('ocf_to_debt_pct', dict(borrowings_current=0.0, borrowings_noncurrent=0.0, lease_current=0.0, lease_noncurrent=0.0), 'non_positive_total_debt'),
                 ('debt_to_ebitda', dict(op=-500.0), 'non_positive_ebitda'), ('net_debt_to_ebitda', dict(op=-500.0), 'non_positive_ebitda')]
        for name, over, reason in cases:
            with self.subTest(metric=name, over=over):
                metric = compute_metrics(dict(FULL, **over))[name]
                self.assertEqual((metric['value'], metric['status']), (None, 'unknown'))
                self.assertIn(reason, metric['reasons'])

    def test_debt_to_capital_needs_a_positive_denominator(self):
        metric = compute_metrics(dict(FULL, equity=-800.0))['debt_to_capital_pct']
        self.assertEqual((metric['value'], metric['status'], metric['reasons']), (None, 'unknown', ['non_positive_capital']))

    def test_missing_inputs_give_unknown_with_missing_reasons(self):
        for name, key in (('debt_ratio_pct', 'total_liabilities'), ('debt_ratio_pct', 'equity'), ('roe_pct', 'net_income_total'), ('ebit_margin_pct', 'revenue'),
                          ('roa_op_pct', 'total_assets'), ('ebitda_to_finance_costs', 'finance_costs'), ('ebitda_to_interest', 'interest_expense'),
                          ('debt_to_assets_pct', 'total_assets')):
            with self.subTest(metric=name, key=key):
                metric = compute_metrics(without(key))[name]
                self.assertEqual((metric['value'], metric['status']), (None, 'unknown'))
                self.assertIn(f'missing:{key}', metric['reasons'])

    def test_ebitda_inputs_flow_into_the_ebitda_ratios_with_their_status(self):
        result = compute_metrics(without('rou_depreciation'))
        for name in ('ebitda_margin_pct', 'debt_to_ebitda', 'net_debt_to_ebitda', 'ebitda_to_finance_costs', 'ebitda_to_interest'):
            with self.subTest(metric=name):
                self.assertEqual(result[name]['status'], 'partial');self.assertIn('ebitda:rou_depreciation_absent', result[name]['reasons'])
        self.assertEqual(result['ebit_margin_pct']['status'], 'ok')

    def test_short_term_debt_ratio(self):
        no_lease_current = compute_metrics(without('lease_current'))['short_term_debt_ratio_pct']
        self.assertEqual((no_lease_current['status'], no_lease_current['reasons']), ('partial', ['lease_current_absent', 'total_debt:lease_incomplete']))
        self.assertAlmostEqual(no_lease_current['value'], 300 / 760 * 100, places=9)
        zero = compute_metrics(without('lease_current', lease_total=0.0, lease_noncurrent=0.0))['short_term_debt_ratio_pct']
        self.assertEqual(zero['status'], 'ok');self.assertAlmostEqual(zero['value'], 300 / 700 * 100, places=9)

    def test_values_are_plain_floats_and_finite(self):
        for metric in compute_metrics(FULL).values():
            self.assertIsInstance(metric['value'], float);self.assertTrue(math.isfinite(metric['value']))

    def test_metric_names_are_unique_and_documented(self):
        self.assertEqual(len(METRIC_NAMES), len(set(METRIC_NAMES)));self.assertEqual(set(METRIC_NAMES), set(EXPECT))
        self.assertTrue(pit_metrics.__doc__)


if __name__ == '__main__':unittest.main()
