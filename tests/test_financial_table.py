import copy,json,tempfile,unittest
from pathlib import Path
from openpyxl import Workbook
from investment.fixture import make_fixture
from investment.financial_table import build_table,load_local_financials
from investment.workspace_export import export_workspace
from tools.infomax_demo import sample
from tools.infomax_import import build_snapshot

class FinancialTableTests(unittest.TestCase):
    def setUp(self):
        self.snapshot=make_fixture();self.row=self.snapshot['companies'][0]
        self.row['annual']=[];self.row['quarters']=[]
        self.period=dict(period_end='2026-06-30',available_at='2026-08-14',basis='CFS',cadence='quarter',source='검증용 가상자료',
            revenue=100e8,operating_profit=-10e8,net_income=0,ebitda=20e8,borrowings=30e8,total_borrowings=50e8,
            assets=200e8,equity=80e8,liabilities=120e8,interest_expense=2e8)
    def source(self,*periods):
        return dict(code=self.row['code'],name=self.row['name'],market=self.row['market'],periods=list(periods),notes=[])
    def test_units_signed_income_and_zero_are_preserved(self):
        column=build_table(self.row,self.snapshot,self.source(self.period))['groups'][0]['columns'][0]
        self.assertEqual(column['values']['revenue'],100)
        self.assertEqual(column['values']['operating_profit'],-10)
        self.assertEqual(column['values']['net_income'],0)
        self.assertEqual(column['values']['operating_margin'],-10)
        self.assertEqual(column['values']['debt_ratio'],150)
        self.assertEqual(column['values']['borrowing_dependence'],25)
    def test_missing_ebitda_and_invalid_denominator_do_not_become_zero(self):
        p=dict(self.period,ebitda=None,equity=-1,interest_expense=0)
        v=build_table(self.row,self.snapshot,self.source(p))['groups'][0]['columns'][0]['values']
        for key in ['ebitda','ebitda_interest','debt_ratio','debt_ebitda']:self.assertIsNone(v[key])
    def test_quarterly_ebitda_is_not_annualized(self):
        p=dict(self.period,cadence='annual')
        quarter=build_table(self.row,self.snapshot,self.source(self.period))['groups'][0]['columns'][0]['values']
        annual=build_table(self.row,self.snapshot,self.source(p))['groups'][0]['columns'][0]['values']
        self.assertIsNone(quarter['debt_ebitda']);self.assertEqual(annual['debt_ebitda'],2.5)
    def test_future_period_and_future_publication_are_excluded(self):
        for p in [dict(self.period,period_end='2026-12-31'),dict(self.period,available_at='2026-12-01'),dict(self.period,period_end='2026-02-30')]:
            self.assertEqual(build_table(self.row,self.snapshot,self.source(p))['groups'],[])
    def test_different_period_types_and_accounting_bases_stay_separate(self):
        table=build_table(self.row,self.snapshot,self.source(self.period,dict(self.period,basis='OFS'),dict(self.period,cadence='annual')))
        self.assertEqual(len(table['groups']),3)
    def test_duplicate_period_fails_closed_and_identity_is_checked(self):
        table=build_table(self.row,self.snapshot,self.source(self.period,self.period))
        self.assertEqual(table['groups'],[]);self.assertIn('중복',table['notes'][0])
        wrong=dict(self.source(self.period),name='다른 기업')
        self.assertEqual(build_table(self.row,self.snapshot,wrong)['groups'],[])
    def test_source_and_snapshot_are_not_modified(self):
        src=self.source(self.period);before=copy.deepcopy((self.snapshot,src))
        html=export_workspace(self.snapshot,financials={self.row['code']:src})
        self.assertEqual((self.snapshot,src),before)
        self.assertIn('financial_tables',html)
    def test_local_xlsx_units_are_converted_and_files_preserved(self):
        grids,config=copy.deepcopy(sample());snapshot=build_snapshot(grids,config);snapshot['meta']['data_mode']='user_input'
        config['mode']='user_input'
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'config').mkdir();raw=root/'private';raw.mkdir()
            (root/'config/local.json').write_text(json.dumps(dict(profile='home',manual_snapshot_file='private/snapshot.json')),encoding='utf-8')
            (raw/'config-review.json').write_text(json.dumps(config),encoding='utf-8')
            for key in ['info','income','balance']:
                wb=Workbook();ws=wb.active
                for r in grids[key]:ws.append(r)
                wb.save(raw/(key+'.xlsx'));wb.close()
            before={p:p.read_bytes() for p in raw.iterdir()}
            loaded=load_local_financials(root,snapshot)
            self.assertEqual(set(loaded),{r['code'] for r in snapshot['companies']})
            code=snapshot['companies'][0]['code']
            p=loaded[code]['periods'][0]
            self.assertEqual(p['revenue'],grids['income'][3][1]*1000)
            self.assertTrue(all(p.read_bytes()==value for p,value in before.items()))
            config['units']['매출액(영업수익)']='원'
            (raw/'config-review.json').write_text(json.dumps(config),encoding='utf-8')
            self.assertEqual(load_local_financials(root,snapshot),{})
    def test_margin_removed_and_interest_input_keeps_eok_unit(self):
        table=build_table(self.row,self.snapshot,self.source(self.period))
        self.assertNotIn('ebitda_margin',[r[0] for r in table['rows']])
        column=table['groups'][0]['columns'][0]
        self.assertNotIn('ebitda_margin',column['values'])
        self.assertEqual(column['interest_expense_eok'],2)
    def test_fixture_never_reads_manual_real_files(self):
        self.assertEqual(load_local_financials('/path/does/not/exist',self.snapshot),{})

if __name__=='__main__':unittest.main()
