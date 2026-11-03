import copy
import unittest
from datetime import date, timedelta
from investment.pit_annual import project
from investment.pit_values import map_record, MAPPING_VERSION

RECEIPT = '20260310000001'


def record(**over):
    base = dict(code='298040', basis='CFS', year=2025, quarter=4, period_start='2025-01-01', period_end='2025-12-31', receipt=RECEIPT,
        unit='KRW', currency='KRW', parser_version='parser-x', url='https://example.invalid/viewer?rcpNo=' + RECEIPT,
        period_contract=dict(report_kind='annual', period_start='2025-01-01', period_end='2025-12-31', currency='KRW',
            source=dict(receipt=RECEIPT, sha256='a' * 64)),
        values=dict(revenue=1000.0, operating_profit=100.0, ocf=120.0, equity=800.0, cash=50.0, balance_debt=300.0, tax=20.0, pretax=110.0,
            assets=1500.0, liabilities=700.0, net_income=90.0))
    base.update(over);return base


def sessions():
    out = [];d = date(2026, 1, 2)
    while d < date(2026, 12, 31):
        if d.weekday() < 5:out.append(d.isoformat())
        d += timedelta(days=1)
    return out


class MappingTests(unittest.TestCase):
    def test_full_year_krw_cfs_record_maps_to_the_pit_receipt_shape(self):
        receipt, provenance = map_record(record(), company='298040', rcept_dt='2026-03-10')
        self.assertEqual({k: receipt[k] for k in ('company', 'period_end', 'basis', 'report_kind', 'rcept_no', 'rcept_dt')},
            dict(company='298040', period_end='2025-12-31', basis='CFS', report_kind='annual', rcept_no=RECEIPT, rcept_dt='2026-03-10'))
        self.assertEqual(receipt['values'], dict(revenue=1000.0, op=100.0, ocf=120.0, equity=800.0, cash=50.0))
        self.assertEqual((provenance['mapping_version'], provenance['rcept_no'], provenance['parser_version'], provenance['contract_sha256']),
            (MAPPING_VERSION, RECEIPT, 'parser-x', 'a' * 64))
        self.assertEqual(provenance['source_keys'], dict(revenue='revenue', op='operating_profit', ocf='ocf', equity='equity', cash='cash'))

    def test_debt_is_only_mapped_when_its_scope_is_explicitly_accepted_and_tax_is_never_mapped(self):
        default, _ = map_record(record(), company='298040', rcept_dt='2026-03-10');self.assertNotIn('debt', default['values'])
        with_debt, prov = map_record(record(), company='298040', rcept_dt='2026-03-10', include_debt=True)
        self.assertEqual(with_debt['values']['debt'], 300.0);self.assertEqual(prov['source_keys']['debt'], 'balance_debt')
        for receipt in (default, with_debt):
            self.assertFalse({'effective_tax_rate', 'tax_verified', 'tax', 'pretax', 'dps'} & set(receipt['values']))

    def test_records_outside_the_pilot_scope_are_rejected(self):
        bad = {'non_krw': record(currency='USD', unit='USD'), 'unit_only': record(unit='USD'), 'currency_only': record(currency='USD'), 'quarter': record(quarter=2), 'short_year': record(period_start='2025-04-01'),
               'non_december': record(period_end='2025-09-30'), 'not_annual': record(period_contract=dict(record()['period_contract'], report_kind='half')),
               'basis': record(basis='XXX'), 'other_receipt': record(receipt='20260311000002'), 'no_contract': record(period_contract=None)}
        for name, r in bad.items():
            with self.subTest(name=name), self.assertRaises(ValueError):map_record(r, company='298040', rcept_dt='2026-03-10')

    def test_receipt_date_must_match_the_receipt_number_and_company_must_be_a_code(self):
        for bad in ('2026-03-09', '2026-03-18', '2026-13-01', 'garbage', None):                    # earlier than the number's date, 8 days later, not a date
            with self.subTest(rcept_dt=bad), self.assertRaises(ValueError):map_record(record(), company='298040', rcept_dt=bad)
        for ok in ('2026-03-11', '2026-03-17'):                                                   # real data: rcept_dt may be later than the number's date
            self.assertEqual(map_record(record(), company='298040', rcept_dt=ok)[0]['rcept_dt'], ok)
        with self.assertRaises(ValueError):map_record(record(), company='', rcept_dt='2026-03-10')

    def test_non_numeric_values_and_an_empty_mapping_are_rejected(self):
        for key, val in (('revenue', 'x'), ('revenue', True), ('ocf', float('nan')), ('revenue', float('inf')), ('operating_profit', float('-inf')), ('revenue', 10 ** 400)):
            r = record();r['values'][key] = val
            with self.subTest(key=key), self.assertRaises(ValueError):map_record(r, company='298040', rcept_dt='2026-03-10')
        r = record();r['values'] = dict(assets=1.0, liabilities=1.0)
        with self.assertRaises(ValueError):map_record(r, company='298040', rcept_dt='2026-03-10')

    def test_missing_optional_fields_stay_missing(self):
        r = record();del r['values']['ocf'];receipt, prov = map_record(r, company='298040', rcept_dt='2026-03-10')
        self.assertNotIn('ocf', receipt['values']);self.assertNotIn('ocf', prov['source_keys'])

    def test_the_input_is_not_mutated_and_the_output_feeds_pit_annual(self):
        r = record();before = copy.deepcopy(r)
        receipt, _ = map_record(r, company='298040', rcept_dt='2026-03-10');self.assertEqual(r, before)
        out = project([receipt], sessions());self.assertEqual(out['blocked'], [])
        self.assertEqual((out['rows'][0]['available_at'], out['rows'][0]['op']), ('2026-03-11', 100.0))


if __name__ == '__main__':unittest.main()
