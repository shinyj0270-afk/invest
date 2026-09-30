"""Fictional data only: evidence boundaries and arithmetic for current valuation."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from investment.core import validate_snapshot
from investment.fixture import make_fixture
from investment.valuation import enrich_valuation, valuation_records
from tools.infomax_valuation import build


class ValuationTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = make_fixture()
        self.row = self.snapshot['companies'][0]
        self.row['prices'][-1].update(close=10000, final=True, venue='KRX', adjustment_basis='split_adjusted')
        self.base = dict(source='Infomax reviewed test', observed_on='2026-09-23',
            price_date='2026-09-23', financial_period='2026-06-30', financial_basis='CFS',
            adjustment_basis='split_adjusted', venue='KRX', period_type='TTM')

    def observation(self, metric='eps_ttm', value=1000, **changes):
        result = dict(self.base, metric=metric, value=value)
        if metric in ('pbr', 'bps'):
            result['period_type'] = 'point_in_time'
        result.update(changes)
        return result

    def result(self, *observations):
        self.row['valuation_observations'] = list(observations)
        return valuation_records(self.row, self.snapshot)

    def test_real_formulas_and_periods(self):
        result = self.result(self.observation(), self.observation('bps', 5000))
        self.assertEqual(result['per']['value'], 10)
        self.assertEqual(result['pbr']['value'], 2)
        self.assertEqual(result['per']['status'], 'derived')
        self.assertEqual(result['per']['period'], '2026-06-30')
        self.assertEqual(result['pbr']['denominator'], 5000)

    def test_source_ratios_need_positive_denominator(self):
        self.assertIsNone(self.result(self.observation('per', 8))['per']['value'])
        direct = self.observation('per', 8, denominator_positive=True)
        self.assertEqual(self.result(direct)['per']['value'], 8)
        self.assertEqual(self.result(direct)['per']['status'], 'observed')
        self.assertIsNone(self.result(direct, self.observation(value=-500))['per']['value'])

    def test_missing_zero_negative_never_cheap(self):
        for metric, output in (('eps_ttm', 'per'), ('bps', 'pbr'), ('per', 'per'), ('pbr', 'pbr')):
            for value in (None, 0, -10):
                with self.subTest(metric=metric, value=value):
                    result = self.result(self.observation(metric, value, denominator_positive=True))[output]
                    self.assertIsNone(result['value'])
                    self.assertTrue(result['reason'])

    def test_incompatible_dates_and_basis_stay_unknown(self):
        for changes in (dict(price_date='2026-09-22'), dict(observed_on='2026-09-24'),
            dict(observed_on='2026-09-22'), dict(financial_period='2026-12-31'),
            dict(financial_basis='OFS'), dict(adjustment_basis='unadjusted'),
            dict(venue='NXT'), dict(period_type='point_in_time')):
            with self.subTest(changes=changes):
                result = self.result(self.observation(**changes))['per']
                self.assertEqual(result['status'], 'unknown')
                self.assertIsNone(result['value'])

    def test_missing_or_provisional_price(self):
        for changes in (dict(final=False), dict(close=0), dict(venue=None), dict(adjustment_basis='unverified')):
            original = copy.deepcopy(self.row['prices'][-1])
            self.row['prices'][-1].update(changes)
            self.assertIsNone(self.result(self.observation())['per']['value'])
            self.row['prices'][-1] = original

    def test_infomax_priority_and_original_preserved(self):
        before = copy.deepcopy(self.snapshot)
        enriched = enrich_valuation(self.snapshot)
        self.assertEqual(self.snapshot, before)
        self.assertIsNone(enriched['companies'][0]['metrics']['per'])
        self.assertIn('per', enriched['companies'][0]['metric_missing_reasons'])
        official = self.observation('per', 7, source='official', denominator_positive=True)
        infomax = self.observation('per', 9, denominator_positive=True)
        self.assertEqual(self.result(official, infomax)['per']['value'], 9)

    def test_malformed_evidence_rejected_by_contract(self):
        for changes in (dict(value=float('nan')), dict(value=True), dict(value='1'),
                        dict(financial_period='2026-02-30'), dict(source=''), dict(denominator_positive='true')):
            self.row['valuation_observations'] = [self.observation(**changes)]
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_snapshot(self.snapshot)

    def test_duplicate_and_overflow_are_not_results(self):
        with self.assertRaises(ValueError):
            self.result(self.observation(), self.observation(value=2000))
        self.assertIsNone(self.result(self.observation(value=1e-320))['per']['value'])

    def test_current_observation_does_not_imply_historical_availability(self):
        record = self.observation(observed_on='2026-09-25')
        self.assertIsNone(self.result(record)['per']['value'])
        self.snapshot['meta']['as_of'] = '2026-09-25'
        self.assertEqual(self.result(record)['per']['value'], 10)
        self.assertEqual(self.result(record)['per']['observed_on'], '2026-09-25')

    def test_same_retrieval_uses_latest_report_regardless_of_input_order(self):
        old = self.observation(value=500, financial_period='2025-12-31')
        current = self.observation(value=1000, financial_period='2026-06-30')
        for records in ((old, current), (current, old)):
            result = self.result(*records)['per']
            self.assertEqual(result['value'], 10)
            self.assertEqual(result['period'], '2026-06-30')

    def test_offline_infomax_route_preserves_base_and_rejects_unknown_company(self):
        before = copy.deepcopy(self.snapshot)
        payload = dict(schema_version='infomax-valuation-0.1', companies={self.row['code']: [self.observation()]})
        output = build(self.snapshot, payload)
        self.assertEqual(output['companies'][0]['metrics']['per'], 10)
        self.assertEqual(self.snapshot, before)
        payload['companies']['123456'] = payload['companies'].pop(self.row['code'])
        with self.assertRaises(ValueError):
            build(self.snapshot, payload)

    def test_public_schema_accepts_optional_valuation_and_rejects_wrong_types(self):
        from jsonschema import Draft202012Validator, FormatChecker
        schema = json.loads((Path(__file__).resolve().parents[1] / 'snapshot.schema.json').read_text(encoding='utf-8'))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        self.row['valuation_observations'] = [self.observation()]
        self.assertEqual(list(validator.iter_errors(enrich_valuation(self.snapshot))), [])
        self.row['valuation_observations'][0]['value'] = '1000'
        self.assertTrue(list(validator.iter_errors(self.snapshot)))

    def test_offline_cli_writes_new_output_and_preserves_existing(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            base, observations, output = [folder / name for name in ('base.json', 'observations.json', 'output.json')]
            base.write_text(json.dumps(self.snapshot), encoding='utf-8')
            observations.write_text(json.dumps(dict(schema_version='infomax-valuation-0.1',
                companies={self.row['code']: [self.observation()]})), encoding='utf-8')
            command = [sys.executable, str(root / 'tools/infomax_valuation.py'), '--base', str(base),
                '--observations', str(observations), '--output', str(output)]
            run = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            original = output.read_bytes()
            self.assertEqual(json.loads(original)['companies'][0]['metrics']['per'], 10)
            again = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual(output.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
