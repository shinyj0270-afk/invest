import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from investment.company_financials import CompanyFinancials, acquire_lock, folder, load_cached
from investment.financial_table import build_table, merge_financials
from investment.official_statements import import_packet, load_official, validate_packet

ROW = dict(code='900000', name='합성 기업', market='KOSDAQ')
SOURCE = b'synthetic official original for isolated tests only'


def packet():
    values = dict(assets=1000, liabilities=400, equity=600, revenue=100,
                  operating_profit=-20, net_income=-10, ocf=80, icf=-40,
                  financing_cf=-20, fx_effect=3, cash_start=200, cash_end=223)
    report = dict(basis='CFS', year=2026, quarter=2, period_start='2026-01-01',
                  period_end='2026-06-30', cadence='cumulative', currency='KRW', actual=True,
                  cells={k: dict(text=str(v), label=k, page=2, table=0, row=i,
                                column=1, column_label='2026 반기 누적', multiplier=1,
                                period_start='2026-01-01', period_end='2026-06-30', basis='CFS')
                         for i, (k, v) in enumerate(values.items())})
    return dict(schema='official-document-statements-1', company=dict(ROW, corp_code='12345678'),
                document=dict(file='source.pdf', sha256=hashlib.sha256(SOURCE).hexdigest(),
                              url='https://issuer.example.invalid/prospectus.pdf', kind='prospectus',
                              pages=3, legal_name=ROW['name'], corp_code='12345678',
                              publisher_role='issuer', available_at='2026-09-14', caveats=['검토 재무']) ,
                review=dict(status='user_confirmed', reviewer='합성 검토자', confirmed_on='2026-10-15'),
                reports=[report])


class OfficialStatementsTests(unittest.TestCase):
    def setup_root(self, root):
        (root/'config').mkdir()
        (root/'config/local.json').write_text(json.dumps(dict(profile='home', data_dir='data')))
        (root/'source.pdf').write_bytes(SOURCE)
        path = root/'packet.json'
        path.write_text(json.dumps(packet()), encoding='utf-8')
        return path

    def test_import_projection_and_financial_table_preserve_actual_half_and_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); path = self.setup_root(root)
            result = import_packet(root, path, ROW)
            self.assertEqual(result['action'], 'update')
            target = folder(root)/'official-documents/900000.json'
            item = load_official(target, ROW, '2026-10-15')
            self.assertEqual(item['periods'][0]['revenue'], 100)
            self.assertEqual(item['periods'][0]['operating_profit'], -20)
            self.assertEqual({p['cadence'] for p in item['periods']}, {'cumulative'})
            self.assertIn('투자설명서', item['periods'][0]['source'])
            self.assertNotIn('DART', item['periods'][0]['source'])
            self.assertEqual(item['financial_completeness']['ttm']['status'], 'pending')
            self.assertEqual(item['financial_completeness']['roe']['status'], 'pending')
            with patch('investment.company_financials.load_market_cache', return_value={}):
                cached = load_cached(root, dict(meta=dict(price_date='2026-10-15')), [ROW])['900000']
            table = build_table(ROW, dict(meta=dict(price_date='2026-10-15', data_mode='user_input')), cached)
            self.assertEqual(table['groups'][0]['cadence'], 'cumulative')
            self.assertAlmostEqual(table['groups'][0]['columns'][0]['values']['revenue'], 100/1e8)
            self.assertEqual(table['financial_completeness']['ttm']['status'], 'pending')
            provider = dict(ROW, periods=[dict(cached['periods'][0], revenue=0, available_at=None)])
            merged = merge_financials({'900000': provider}, {'900000': cached}, as_of='2026-10-15')['900000']
            self.assertEqual(merged['periods'][0]['revenue'], 0)
            self.assertNotIn('DART', merged['periods'][0]['source'])
            self.assertIn('공식 원문', merged['periods'][0]['source'])
            self.assertIsNone(load_official(target, ROW, '2026-09-13'))
            self.assertIsNone(load_official(target, dict(ROW, name='다른 기업'), '2026-10-15'))

    def test_failed_validation_or_source_hash_preserves_applied_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); path = self.setup_root(root)
            import_packet(root, path, ROW)
            target = folder(root)/'official-documents/900000.json'; before = target.read_bytes()
            bad = packet(); bad['reports'][0]['cells']['ocf']['text'] = '82'
            path.write_text(json.dumps(bad), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '현금흐름'): import_packet(root, path, ROW)
            self.assertEqual(target.read_bytes(), before)
            path.write_text(json.dumps(packet()), encoding='utf-8')
            (root/'source.pdf').write_bytes(b'changed source')
            with self.assertRaisesRegex(ValueError, '해시'): import_packet(root, path, ROW)
            self.assertEqual(target.read_bytes(), before)

    def test_ambiguous_period_basis_units_actual_approval_and_missing_cash_rejected(self):
        changes = [
            lambda p: p['review'].update(status='pending'),
            lambda p: p['document'].update(kind='company-finance'),
            lambda p: p['document'].update(kind='krx-split'),
            lambda p: p['document'].update(corp_code='87654321'),
            lambda p: p['document'].update(url='http://issuer.example.invalid/file.pdf'),
            lambda p: p['reports'][0].update(actual=False),
            lambda p: p['reports'][0].update(quarter=1),
            lambda p: p['reports'][0]['cells']['revenue'].update(period_end='2025-12-31'),
            lambda p: p['reports'][0]['cells']['revenue'].update(basis='OFS'),
            lambda p: p['reports'][0]['cells']['revenue'].update(multiplier=100000000),
            lambda p: p['reports'][0]['cells']['revenue'].update(text='-'),
            lambda p: p['reports'][0]['cells'].pop('cash_end'),
            lambda p: p['reports'].append(copy.deepcopy(p['reports'][0])),
            lambda p: p['reports'][0]['cells']['assets'].update(text='1002'),
        ]
        for change in changes:
            with self.subTest(change=change):
                data = packet(); change(data)
                with self.assertRaises(ValueError): validate_packet(data, ROW)

    def test_unit_conversion_parenthesized_losses_and_tampering(self):
        data = packet()
        for cell in data['reports'][0]['cells'].values(): cell['multiplier'] = 1000
        data['reports'][0]['cells']['net_income']['text'] = '(10)'
        result = validate_packet(data, ROW)
        self.assertEqual(result['reports'][0]['values']['net_income'], -10000)
        result['reports'][0]['values']['revenue'] = 123
        with self.assertRaisesRegex(ValueError, '저장 값'): validate_packet(result, ROW)

    def test_lock_conflict_and_unknown_profile_prevent_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); path = self.setup_root(root); dest = folder(root); dest.mkdir(parents=True)
            with acquire_lock(dest/'collection.lock'):
                with self.assertRaises(ValueError): import_packet(root, path, ROW)
            self.assertFalse((dest/'official-documents').exists())
            (root/'config/local.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'profile'): import_packet(root, path, ROW)

    def test_small_revision_deferred_material_revision_backed_up_older_source_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); path = self.setup_root(root)
            import_packet(root, path, ROW); target = folder(root)/'official-documents/900000.json'
            before = target.read_bytes(); data = packet()
            data['reports'][0]['cells']['revenue']['text'] = '103'
            path.write_text(json.dumps(data), encoding='utf-8')
            self.assertEqual(import_packet(root, path, ROW)['action'], 'defer')
            self.assertEqual(target.read_bytes(), before)
            data['reports'][0]['cells']['revenue']['text'] = '108'
            path.write_text(json.dumps(data), encoding='utf-8')
            self.assertEqual(import_packet(root, path, ROW)['action'], 'update')
            self.assertEqual(len(list((target.parent/'backups').glob('*.json'))), 1)
            applied = target.read_bytes(); data['document']['available_at'] = '2026-09-13'
            path.write_text(json.dumps(data), encoding='utf-8')
            self.assertEqual(import_packet(root, path, ROW)['reason'], 'older_document')
            self.assertEqual(target.read_bytes(), applied)

    def test_existing_dart_period_wins_and_failure_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); path = self.setup_root(root); import_packet(root, path, ROW)
            dest = folder(root); (dest/'900000.json').write_text('{}')
            (dest/'900000.status.json').write_text(json.dumps(dict(status='failed', checked_at='2026-10-15T12:00:00+09:00')))
            official = load_official(dest/'official-documents/900000.json', ROW, '2026-10-15')
            existing = dict(ROW, periods=[dict(official['periods'][0], revenue=999, source='DART')], notes=[])
            with patch('investment.company_financials.load_bundle', return_value={'900000': existing}), patch('investment.company_financials.load_market_cache', return_value={}):
                cached = load_cached(root, dict(meta=dict(price_date='2026-10-15')), [ROW])['900000']
            self.assertEqual(len(cached['periods']), 1)
            self.assertEqual(cached['periods'][0]['revenue'], 999)
            self.assertEqual(cached['collection_health']['status'], 'failed')
            self.assertEqual(cached['official_document']['kind'], 'prospectus')

    def test_imported_original_is_cached_without_implicit_network_collection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); path = self.setup_root(root); import_packet(root, path, ROW)
            row = dict(ROW, eligibility='candidate', metrics=dict(market_cap_eok=2000))
            with patch('investment.company_financials.load_market_cache', return_value=dict(universe=dict(companies=[row]))):
                service = CompanyFinancials(root, collector=lambda *a, **kw: self.fail('unexpected network collection'))
                self.assertEqual(service.start(ROW['code'])['status'], 'cached')


if __name__ == '__main__':
    unittest.main()
