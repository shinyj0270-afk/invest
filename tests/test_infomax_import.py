"""Offline boundary and calculation tests. All records are invented."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.infomax_import import InputError, build_snapshot, day, number, read_grid, write_new
from tools.infomax_demo import sample, create_demo


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.grids, self.config = copy.deepcopy(sample())

    def result(self):
        return build_snapshot(self.grids, self.config)

    def test_calculations_and_insufficient_accounts(self):
        result = self.result()
        for row in result['companies']:
            m = row['metrics']
            self.assertEqual(m['market_cap_eok'], 100)
            self.assertEqual(m['operating_margin_pct'], 10)
            self.assertEqual(m['debt_ratio_pct'], 50)
            self.assertEqual(m['foreign_net_20d_eok'], .2)
            self.assertEqual(m['institution_net_20d_eok'], -.1)
            self.assertEqual(m['foreign_net_turnover_20d_pct'], 1)
            self.assertEqual(m['avg_trading_value_20d_eok'], 1)
            self.assertIsNone(m['roe_pct'])
            self.assertIsNone(m['revenue_growth_pct'])
            self.assertEqual(row['history'], [])
        self.assertEqual(result['meta']['data_mode'], 'fixture')

    def test_today_excluded_without_filling_null(self):
        result = self.result()
        self.assertEqual(result['meta']['import_audit']['900001']['excluded_after_completed']['flows'], 1)
        self.assertEqual(self.grids['flows'][3][1:3], [None, None])

    def test_missing_flow_does_not_shorten_window(self):
        self.grids['flows'][4][2] = None
        m = self.result()['companies'][0]['metrics']
        self.assertIsNone(m['foreign_net_20d_eok'])
        self.assertIsNone(m['foreign_net_turnover_20d_pct'])
        self.assertEqual(m['institution_net_20d_eok'], -.1)

    def test_missing_session_row_not_inferred(self):
        del self.grids['prices'][4]
        m = self.result()['companies'][0]['metrics']
        self.assertIsNone(m['avg_trading_value_20d_eok'])
        self.assertIsNone(m['foreign_net_turnover_20d_pct'])

    def test_venue_mismatch_blocks_ratios_only(self):
        self.config['flow_venue'] = 'NXT'
        result = self.result()
        self.assertEqual(result['meta']['venue'], '가격 KRX / 수급 NXT')
        m = result['companies'][0]['metrics']
        self.assertEqual(m['foreign_net_20d_eok'], .2)
        self.assertIsNone(m['foreign_net_turnover_20d_pct'])

    def test_unconfirmed_flow_is_not_final(self):
        self.config['flows_final'] = False
        self.assertIsNone(self.result()['companies'][0]['metrics']['institution_net_20d_eok'])

    def test_cap_date_must_match(self):
        self.config['market_cap_date'] = '2026-01-30'
        self.assertIsNone(self.result()['companies'][0]['metrics']['market_cap_eok'])

    def test_financial_publication_missing_and_future(self):
        self.config['companies']['900001']['financial_available_on'] = None
        self.assertIsNone(self.result()['companies'][0]['metrics']['operating_margin_pct'])
        self.config['companies']['900001']['financial_available_on'] = '2026-02-01'
        with self.assertRaises(InputError):
            self.result()

    def test_zero_denominator_remains_null(self):
        self.grids['income'][3][1] = 0
        self.grids['balance'][3][2:4] = [0, 300000]
        m = self.result()['companies'][0]['metrics']
        self.assertIsNone(m['operating_margin_pct'])
        self.assertIsNone(m['debt_ratio_pct'])

    def test_balance_reconciliation(self):
        self.grids['balance'][3][1] += 100
        with self.assertRaisesRegex(InputError, '자산=자본'):
            self.result()

    def test_bad_basis_units_dates_and_sessions(self):
        with self.assertRaises(InputError):
            build_snapshot(self.grids, [])
        for key, value in [('balance_comp', '순'), ('income_comp', '누적'), ('financial_basis', 'OFS'),
                           ('financial_period', '2025-12-30'), ('as_of', '2026-02-30'), ('sessions_20d', [])]:
            with self.subTest(key=key):
                config = copy.deepcopy(self.config)
                config[key] = value
                with self.assertRaises(InputError):
                    build_snapshot(self.grids, config)
        self.config['units']['외국인순매수금액'] = '원'
        with self.assertRaises(InputError):
            self.result()

    def test_duplicate_dates_and_names(self):
        self.grids['prices'].append(self.grids['prices'][4])
        with self.assertRaises(InputError):
            self.result()
        self.grids, _ = sample()
        self.grids['info'][2][0] = self.grids['info'][1][0]
        with self.assertRaises(InputError):
            self.result()

    def test_future_observation_rejected(self):
        self.grids['prices'][3][0] = '2026-02-01'
        with self.assertRaises(InputError):
            self.result()

    def test_no_assumed_classification(self):
        del self.config['companies']['900001']['security_type']
        self.assertEqual(self.result()['companies'][0]['security_type'], 'unknown')

    def test_number_and_date_boundaries(self):
        self.assertEqual(number('-1,234.5', 'x'), -1234.5)
        self.assertEqual(number('0', 'x'), 0)
        self.assertIsNone(number(' ', 'x'))
        self.assertEqual(day(datetime(2026, 1, 1), 'x'), '2026-01-01')
        for value in ['#N/A', '####', '=1+1', 'NaN', 'Inf', '1,2', '-', True, float('inf')]:
            with self.subTest(value=value), self.assertRaises(InputError):
                number(value, 'x')

    def test_code_leading_zero_preserved(self):
        self.grids['info'][1][2:4] = ['005930', '005930']
        self.config['companies']['005930'] = self.config['companies'].pop('900001')
        self.assertEqual(self.result()['companies'][0]['code'], '005930')
        self.grids['info'][1][2] = 5930
        with self.assertRaises(InputError):
            self.result()

    def test_csv_roundtrip_and_engine_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = create_demo(Path(tmp) / 'demo')
            result = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(result['companies'][0]['metrics']['foreign_net_20d_eok'], .2)
            self.assertEqual(len(result['meta']['source_files']), 5)
            js = 'const fs=require("fs");require("./src/engine.js").validateSnapshot(JSON.parse(fs.readFileSync(process.argv[1],"utf8")));'
            subprocess.run(['node', '-e', js, str(path)], cwd=ROOT, check=True, capture_output=True)

    def test_cp949_and_formula_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'test.csv'
            p.write_bytes('종목명,코드\n가상,005930\n'.encode('cp949'))
            grid, evidence = read_grid(p)
            self.assertEqual(grid[1][1], '005930')
            self.assertEqual(len(evidence['sha256']), 64)
        self.grids['income'][3][2] = '#VALUE!'
        with self.assertRaises(InputError):
            self.result()

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'snapshot.json'
            write_new(p, {'old': True})
            with self.assertRaises(InputError):
                write_new(p, {'new': True})
            self.assertEqual(json.loads(p.read_text()), {'old': True})

    def test_bad_input_never_publishes_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = create_demo(Path(tmp) / 'demo')
            config = p.parent / 'config.json'
            payload = json.loads(config.read_text(encoding='utf-8'))
            payload['balance_comp'] = '순'
            config.write_text(json.dumps(payload), encoding='utf-8')
            output = p.parent / 'invalid.json'
            args = [sys.executable, 'tools/infomax_import.py', '--config', str(config), '--output', str(output)]
            for kind in ('info', 'prices', 'flows', 'balance', 'income'):
                args += ['--'+kind, str(p.parent / (kind+'.csv'))]
            run = subprocess.run(args, cwd=ROOT, capture_output=True)
            self.assertEqual(run.returncode, 2)
            self.assertFalse(output.exists())

    def test_xlsx_reader_cached_value_and_no_formula_execution(self):
        # Minimal OOXML reader fixture, not an authored user workbook.
        try:
            import openpyxl
        except ImportError:
            self.skipTest('openpyxl not installed')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'reader.xlsx'
            parts = {
                '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
                '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
                'xl/workbook.xml': '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>',
                'xl/_rels/workbook.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
                'xl/worksheets/sheet1.xml': '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>005930</t></is></c><c r="B1"><f>1+1</f><v>2</v></c><c r="C1"><f>INFOMAX()</f></c></row></sheetData></worksheet>'}
            with ZipFile(p, 'w') as archive:
                for name, content in parts.items():
                    archive.writestr(name, content)
            grid, _ = read_grid(p)
            self.assertEqual(grid, [('005930', 2, None)])


if __name__ == '__main__':
    unittest.main()
