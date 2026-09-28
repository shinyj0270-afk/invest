import copy
from datetime import date
import unittest
from tools.infomax_financial_snapshot import BALANCE, INCOME, parse, calculate


class FinancialSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.dates=['2026-06-30','2026-03-31','2025-12-31','2025-09-30','2025-06-30']
        b=dict.fromkeys(BALANCE[1:],0.0)
        b.update({'자산':1000.,'자본':600.,'부채':400.,'기말비지배주주지분':100.,
                  '지배기업주주지분(요약재무)':500.,'현금및현금성자산':100.,
                  '유동자산(요약재무)':400.,'유동부채(요약재무)':200.,
                  '차입금':80.,'사채':20.,'단기차입금(요약재무)':50.,'장기차입금(요약재무)':30.,
                  '유동성장기부채(요약재무)':10.,'리스부채(요약재무)':5.,
                  '유동성리스부채(요약재무)':None,'단기사채(요약재무)':None})
        inc=dict(zip(INCOME[1:],[200.,40.,25.,5.,30.]))
        self.bal={d:copy.deepcopy(b) for d in self.dates}
        self.inc={d:copy.deepcopy(inc) for d in self.dates}
        self.inc[self.dates[-1]]['매출액(영업수익)']=100.
        self.review=dict(period_end=self.dates[0],debt_fields=['차입금','사채','유동성장기부채(요약재무)','리스부채(요약재무)'],
            debt_scope_note='Synthetic reviewed partition; current lease included in current debt.',
            omitted_blank_fields={'유동성리스부채(요약재무)':'Included in current debt'},
            sources=[{'label':'Synthetic test source','url':''}],
            official_million_krw=dict(assets=1.,equity=.6,liabilities=.4,cash=.1,nci=.1,
                current_assets=.4,current_liabilities=.2,revenue=.2,profit=.04,parent_income=.025,
                interest=.005,previous_revenue=.1,opening_equity=.6,opening_nci=.1,parent_ttm=.1,total_debt=.115))
        self.values=[['시작',date(2025,1,1),'종료',date(2026,9,28),'Data 개수',5,'주기','분기','정렬','D'],
                     ['가상기업'],INCOME.copy()]+[[d]+list(self.inc[d].values()) for d in self.dates]
        self.formulas=[[],['=IMDH("STK","900001",A3:F3,B1,D1,F1,"Per=분기,sort=D,real=false,Orient=V,Cons=연결,Comp=순,Trai=연속,unit=true")']]

    def parse(self):
        return parse(self.values,self.formulas,INCOME,{'900001':'가상기업'},'2026-09-28','순')

    def test_calculations_and_negative_net_cash(self):
        m,a=calculate(self.bal,self.inc,self.review)
        self.assertEqual(m['revenue_growth_pct'],100)
        self.assertEqual(m['operating_margin_pct'],20)
        self.assertEqual(m['roe_pct'],20)
        self.assertAlmostEqual(m['debt_ratio_pct'],400/600*100)
        self.assertAlmostEqual(m['net_debt_equity_pct'],15/600*100)
        self.assertEqual(m['interest_coverage_x'],8)
        self.assertEqual(m['current_ratio_pct'],200)
        self.assertEqual(a['differences_at_least_100m'],[])
        self.bal[self.dates[0]]['현금및현금성자산']=200
        self.assertLess(calculate(self.bal,self.inc,self.review)[0]['net_debt_equity_pct'],0)

    def test_blank_lease_not_zero(self):
        self.review['debt_fields'].append('유동성리스부채(요약재무)')
        with self.assertRaisesRegex(ValueError,'구성 계정 결측'): calculate(self.bal,self.inc,self.review)

    def test_duplicate_debt_and_scope_expiry_rejected(self):
        self.review['debt_fields'].append('차입금')
        with self.assertRaisesRegex(ValueError,'구성 중복'): calculate(self.bal,self.inc,self.review)
        self.review['debt_fields'].pop()
        self.review['period_end']='2026-03-31'
        with self.assertRaisesRegex(ValueError,'검토 기간'): calculate(self.bal,self.inc,self.review)

    def test_no_missing_quarter_or_cumulative_income(self):
        self.assertEqual(len(self.parse()['900001']),5)
        self.values.pop(5)
        with self.assertRaises(ValueError): self.parse()

    def test_accounting_basis_and_comp_required(self):
        original=self.formulas[1][0]
        for old,new in [('Cons=연결','Cons=연결우선'),('Comp=순','Comp=누적')]:
            self.formulas[1][0]=original.replace(old,new)
            with self.assertRaisesRegex(ValueError,'함수 조건'): self.parse()

    def test_wrong_identity_and_date_rejected(self):
        self.formulas[1][0]=self.formulas[1][0].replace('900001','900002')
        with self.assertRaisesRegex(ValueError,'미등록'): self.parse()
        self.formulas[1][0]=self.formulas[1][0].replace('900002','900001')
        self.values[4][0]=self.values[3][0]
        with self.assertRaisesRegex(ValueError,'중복 분기'): self.parse()

    def test_missing_denominator_rejected(self):
        self.inc[self.dates[0]]['이자비용']=0
        with self.assertRaisesRegex(ValueError,'분모'): calculate(self.bal,self.inc,self.review)

    def test_large_official_difference_retained(self):
        self.review['official_million_krw']['total_debt']=100.115
        audit=calculate(self.bal,self.inc,self.review)[1]
        self.assertIn('total_debt',audit['differences_at_least_100m'])
        self.assertEqual(audit['selected_source'],'infomax')

    def test_excel_error_and_field_order_rejected(self):
        self.values[3][2]='#N/A'
        with self.assertRaises(ValueError): self.parse()
        self.values[3][2]=40
        self.values[2]=list(reversed(INCOME))
        with self.assertRaisesRegex(ValueError,'계정 이름'): self.parse()

    def test_parent_equity_and_borrowing_partition_checks(self):
        self.bal[self.dates[0]]['지배기업주주지분(요약재무)']=100500
        with self.assertRaisesRegex(ValueError,'지분 분모'): calculate(self.bal,self.inc,self.review)
        self.bal[self.dates[0]]['지배기업주주지분(요약재무)']=500
        self.bal[self.dates[0]]['차입금']=100080
        with self.assertRaisesRegex(ValueError,'단기'): calculate(self.bal,self.inc,self.review)


if __name__=='__main__': unittest.main()
