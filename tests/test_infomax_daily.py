import copy
from datetime import date, timedelta
import unittest
import tempfile
from pathlib import Path
from tools.infomax_daily import build, convert, HEADERS


class DailyImportTests(unittest.TestCase):
    def setUp(self):
        self.as_of = '2026-09-28'
        self.identities = {'900001': dict(name='가상 테스트 기업', market='KOSPI',
            industry='시험', security_type='ordinary', analysis_profile='nonfinancial')}
        self.values = [['시작', date(2025,9,28), '종료', date(2026,9,28),
                       'Data 개수', 100, '주기', '일', '정렬', 'D', '영업일', 0, '시세산출', '종가'],
                       ['가상 테스트 기업'], HEADERS.copy()]
        # Synthetic calendar, not evidence about Korean market sessions.
        for n in range(21):
            self.values.append([date(2026,9,28)-timedelta(days=n),100,10,1000,1e8,-2,3])
        self.formulas = [[], ['=_xll.IMDH("STK","900001",A3:G3,...)']]
        pairs = {'unknown_venue':'allow_use_with_label',
                 'revision_finality':'allow_provisional_use_with_label',
                 'investor_aggregation':'use_existing_provider_fields_with_label',
                 'observed_sessions_calendar':'use_latest_20_common_observed_dates_with_label',
                 'flow_turnover_scope_comparability':'allow_provisional_ratio_with_label'}
        self.decisions = {k:dict(decision=v,required_label=k) for k,v in pairs.items()}

    def convert(self):
        return build(self.values,self.formulas,self.identities,self.as_of,
                     self.decisions,dict(file='synthetic.xlsx',sha256='test'))

    def test_units_signed_flows_and_same_day_exclusion(self):
        self.values[3][1:] = [999999]*6
        s=self.convert(); m=s['companies'][0]['metrics']
        self.assertEqual(s['meta']['price_date'],'2026-09-27')
        self.assertEqual(m['price'],100)
        self.assertEqual(m['market_cap_eok'],1)
        self.assertEqual(m['institution_net_20d_eok'],-40000/1e8)
        self.assertEqual(m['foreign_net_turnover_20d_pct'],300)
        self.assertEqual(len(s['companies'][0]['prices']),20)
        self.assertIsNone(m['roe_pct'])
        self.assertFalse(s['companies'][0]['flows'][0]['final'])

    def test_missing_historical_value_rejected(self):
        self.values[4][5]=None
        with self.assertRaisesRegex(ValueError,'결측'): self.convert()

    def test_duplicate_date_rejected(self):
        self.values[5][0]=self.values[4][0]
        with self.assertRaisesRegex(ValueError,'중복'): self.convert()

    def test_future_date_rejected(self):
        self.values[4][0]=date(2026,9,29)
        with self.assertRaisesRegex(ValueError,'미래'): self.convert()

    def test_formula_identity_required(self):
        self.formulas[1][0]='=IMDH("STK","900002",...)'
        with self.assertRaisesRegex(ValueError,'미등록'): self.convert()

    def test_field_order_not_guessed(self):
        self.values[2]=HEADERS[::-1]
        with self.assertRaisesRegex(ValueError,'필드'): self.convert()

    def test_provisional_policy_not_inferred(self):
        self.decisions={}
        m=self.convert()['companies'][0]['metrics']
        self.assertIsNone(m['foreign_net_20d_eok'])
        self.assertIsNone(m['market_cap_eok'])

    def test_company_dates_must_match(self):
        self.identities['900002']=dict(self.identities['900001'],name='다른 가상 기업')
        self.values[1]=self.values[1]+[None]*6+['다른 가상 기업']
        self.formulas[1]=self.formulas[1]+[None]*6+['=IMDH("STK","900002",...)']
        self.values[2]=HEADERS+HEADERS
        for row in self.values[3:]: row.extend(copy.deepcopy(row))
        self.values[-1][7]-=timedelta(days=1)
        with self.assertRaisesRegex(ValueError,'관측일 불일치'): self.convert()

    def test_saved_workbook_date_and_array_formula(self):
        from openpyxl import Workbook
        from openpyxl.worksheet.formula import ArrayFormula
        from zipfile import ZipFile
        from xml.etree import ElementTree as ET
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'synthetic.xlsx'
            book = Workbook()
            for row in self.values:
                book.active.append(row)
            book.active['A2'] = ArrayFormula(ref='A2:G24', text=self.formulas[1][0])
            book.save(path)
            with ZipFile(path) as archive:
                files = {name:archive.read(name) for name in archive.namelist()}
            ns = {'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            tree = ET.fromstring(files['xl/worksheets/sheet1.xml'])
            cell = tree.find('.//s:c[@r="A2"]', ns)
            cell.set('t','str')
            cell.find('s:v', ns).text = self.identities['900001']['name']
            files['xl/worksheets/sheet1.xml'] = ET.tostring(tree)
            with ZipFile(path, 'w') as archive:
                for name, content in files.items(): archive.writestr(name, content)
            config = dict(companies=self.identities, decisions=self.decisions)
            result = convert(path, config)
            self.assertEqual(result['meta']['as_of'], self.as_of)
            self.assertEqual(result['companies'][0]['metrics']['price'],100)
            with self.assertRaisesRegex(ValueError,'종료일 불일치'):
                convert(path, config, '2026-09-29')


if __name__=='__main__': unittest.main()
