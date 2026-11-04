"""The A-stage account fields (see tests/test_pit_xml_accounts.py) flow unchanged through map_record -> project -> verify.

Names are the same at every layer. Ranges (both `pit_annual` and the independent `pit_verify` copy must agree):
  >= 0: lease_total, da_total (tag-derived), total_assets, total_liabilities, short_term_financial_instruments, borrowings_current, borrowings_noncurrent, lease_current, lease_noncurrent,
        finance_costs, interest_expense, depreciation, amortization, rou_depreciation, capex_tangible, capex_intangible, dividends_paid
  any sign: pretax_income, income_tax_expense, net_income_total
The legacy parser keys `net_income`, `assets`, `liabilities`, `tax`, `pretax` stay unmapped.
"""
import unittest
from investment import pit_annual, pit_verify
from investment.pit_annual import project
from investment.pit_values import map_record
from investment.pit_verify import verify
from tests.test_pit_annual import receipt, sessions
from tests.test_pit_values import record, RECEIPT

NONNEGATIVE = ('total_assets', 'total_liabilities', 'short_term_financial_instruments', 'borrowings_current', 'borrowings_noncurrent', 'lease_current',
               'lease_noncurrent', 'finance_costs', 'interest_expense', 'depreciation', 'amortization', 'rou_depreciation', 'capex_tangible',
               'capex_intangible', 'dividends_paid', 'lease_total', 'da_total')
ANY_SIGN = ('pretax_income', 'income_tax_expense', 'net_income_total')
NEW = NONNEGATIVE + ANY_SIGN
VALUES = {key: float(i + 1) * 10 for i, key in enumerate(NEW)}


class MappingTests(unittest.TestCase):
    def test_every_new_field_is_mapped_under_its_own_name(self):
        values = dict(record()['values'], **VALUES)
        receipt_, provenance = map_record(record(values=values), company='298040', rcept_dt='2026-03-10')
        self.assertEqual(receipt_['values'], dict(revenue=1000.0, op=100.0, ocf=120.0, equity=800.0, cash=50.0, **VALUES))
        self.assertEqual({k: provenance['source_keys'][k] for k in NEW}, {k: k for k in NEW})

    def test_a_record_without_the_new_fields_maps_exactly_as_before_and_legacy_keys_stay_unmapped(self):
        mapped, _ = map_record(record(), company='298040', rcept_dt='2026-03-10')
        self.assertEqual(mapped['values'], dict(revenue=1000.0, op=100.0, ocf=120.0, equity=800.0, cash=50.0))
        for legacy in ('net_income', 'assets', 'liabilities', 'tax', 'pretax'):
            self.assertNotIn(legacy, mapped['values'])

    def test_a_non_numeric_new_value_is_refused_and_none_is_skipped(self):
        for bad in ('12', True, float('nan')):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                map_record(record(values=dict(record()['values'], total_assets=bad)), company='298040', rcept_dt='2026-03-10')
        mapped, _ = map_record(record(values=dict(record()['values'], total_assets=None)), company='298040', rcept_dt='2026-03-10')
        self.assertNotIn('total_assets', mapped['values'])


class ProjectionTests(unittest.TestCase):
    def test_new_fields_survive_the_projection_as_floats(self):
        out = project([receipt(values=dict(revenue=100.0, **VALUES))], sessions())
        self.assertEqual(out['blocked'], [])
        for key, value in VALUES.items():
            self.assertEqual(out['rows'][0][key], value)

    def test_integers_are_canonicalised_and_negative_any_sign_fields_are_accepted(self):
        out = project([receipt(values=dict(revenue=100, pretax_income=-5, income_tax_expense=-2, net_income_total=-3, total_assets=7))], sessions())
        row = out['rows'][0]
        self.assertEqual((row['pretax_income'], row['income_tax_expense'], row['net_income_total'], row['total_assets']), (-5.0, -2.0, -3.0, 7.0))

    def test_ranges_block_the_receipt_with_bad_values(self):
        for key in NONNEGATIVE:
            with self.subTest(key=key):
                out = project([receipt(values={'revenue': 100.0, key: -1.0})], sessions())
                self.assertEqual((out['rows'], out['blocked'][0]['reason']), ([], 'bad_values'))
        for key in NEW:
            with self.subTest(key=key, kind='nan'):
                out = project([receipt(values={'revenue': 100.0, key: float('nan')})], sessions())
                self.assertEqual(out['blocked'][0]['reason'], 'bad_values')

    def test_annual_and_verify_use_identical_numeric_ranges(self):
        self.assertEqual(pit_annual.NUMERIC, pit_verify.NUMERIC)
        for key in NEW:
            self.assertIn(key, pit_annual.NUMERIC)


class VerifyTests(unittest.TestCase):
    def test_verify_passes_with_the_new_fields(self):
        receipts = [receipt(values=dict(revenue=100.0, **VALUES)), receipt(no='20260520000002', rcept='2026-05-20', values=dict(revenue=100.0, **VALUES))]
        out = verify(receipts, sessions())
        self.assertTrue(out['ok'], out)

    def test_verify_blocks_a_range_violation_like_the_projection_does(self):
        out = verify([receipt(values={'revenue': 100.0, 'borrowings_current': -1.0})], sessions())
        self.assertEqual(out['counts']['blocked'], {'bad_values': 1})

    def test_a_changed_new_value_between_a_correction_and_its_original_is_a_separate_version(self):
        receipts = [receipt(values={'revenue': 100.0, 'total_assets': 10.0}),
                    receipt(no='20260520000002', rcept='2026-05-20', values={'revenue': 100.0, 'total_assets': 11.0})]
        out = project(receipts, sessions())
        self.assertEqual([r['total_assets'] for r in out['rows']], [10.0, 11.0])
        self.assertTrue(verify(receipts, sessions())['ok'])


if __name__ == '__main__':unittest.main()
