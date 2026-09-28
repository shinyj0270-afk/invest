import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from infomax_financials import REFERENCES, EXTRAS, QUARTERS, BALANCE_DATES, reconcile

def fixture(code):
    ref=REFERENCES[code]
    data={k:{code:{}} for k in EXTRAS}
    for date in BALANCE_DATES:
        eq=ref['opening_equity'] if date=='2025-06-30' else ref['equity']
        nci=ref['opening_nci'] if date=='2025-06-30' else ref['nci']
        data['balance-extra'][code][date]={'자본':eq*1000,'기말비지배주주지분':nci*1000,'현금및현금성자산':ref['cash']*1000}
        data['debt-extra'][code][date]={'자본':eq*1000,'차입금':sum(ref['supplier_borrowing_components'].values())*1000,'사채':ref['supplier_bond_reference']*1000}
    parent=[ref['parent_q2'],ref['parent_h1']-ref['parent_q2'],ref['parent_fy']-ref['parent_prior_h1'],0]
    interest=[ref['interest_q2'],ref['interest_h1']-ref['interest_q2'],1,1]
    for date,net,cost in zip(QUARTERS,parent,interest):
        data['income-extra'][code][date]={'당기순이익지배기업주주지분':net*1000,'이자비용':cost*1000,'영업이익':ref['profit_q2']*1000}
    return data

class FinancialReconciliationTests(unittest.TestCase):
    def test_all_companies_and_independent_ttm(self):
        for code in REFERENCES:
            result=reconcile(code,fixture(code))
            self.assertTrue(all(v==0 for v in result['differences_million_krw'].values()))
            self.assertEqual(len(result['metrics']),3)

    def test_strict_tolerance(self):
        for million,accepted in [(99,True),(100,False),(-100,False)]:
            data=fixture('005930')
            data['income-extra']['005930'][QUARTERS[0]]['당기순이익지배기업주주지분']+=million*1000
            if accepted: reconcile('005930',data)
            else:
                with self.assertRaises(ValueError): reconcile('005930',data)

    def test_ttm_mismatch_blocks_release(self):
        data=fixture('000660')
        data['income-extra']['000660'][QUARTERS[2]]['당기순이익지배기업주주지분']+=1000000
        with self.assertRaises(ValueError): reconcile('000660',data)

    def test_debt_not_supplier_two_field_sum(self):
        expected={'005930':22408721,'000660':21113139,'005380':190418762}
        for code,total in expected.items():
            data=fixture(code)
            result=reconcile(code,data)
            self.assertEqual(result['total_debt_million_krw'],total)
            self.assertNotEqual(total,sum(data['debt-extra'][code][QUARTERS[0]][k]/1000 for k in ['차입금','사채']))

    def test_hyundai_bond_difference_not_silently_accepted(self):
        data=fixture('005380')
        data['debt-extra']['005380'][QUARTERS[0]]['사채']=116377178000
        result=reconcile('005380',data)
        self.assertEqual(result['supplier_bonds_minus_official_noncurrent_million_krw'],333195)
        self.assertEqual(result['total_debt_million_krw'],190418762)

    def test_user_priority_replaces_bond_and_preserves_comparison(self):
        data=fixture('005380')
        data['debt-extra']['005380'][QUARTERS[0]]['사채']=116377178000
        result=reconcile('005380',data,prefer_infomax=True)
        self.assertEqual(result['total_debt_million_krw'],190751957)
        self.assertEqual(result['official_total_debt_million_krw'],190418762)
        self.assertEqual(result['supplier_bonds_minus_official_noncurrent_million_krw'],333195)
        self.assertAlmostEqual(result['metrics']['net_debt_equity_pct'],(190751957-20256150)/135416445*100)
        self.assertEqual(result['status'],'user_policy_infomax_priority')

    def test_user_priority_keeps_large_money_difference_visible(self):
        data=fixture('005930')
        data['income-extra']['005930'][QUARTERS[0]]['당기순이익지배기업주주지분']+=1000000
        result=reconcile('005930',data,prefer_infomax=True)
        self.assertEqual(result['differences_million_krw']['parent_q2'],1000)
        self.assertFalse(result['official_amount_checks_within_tolerance'])

    def test_user_priority_does_not_bypass_structural_checks(self):
        data=fixture('005930')
        data['debt-extra']['005930'][QUARTERS[0]]['자본']+=1
        with self.assertRaises(ValueError): reconcile('005930',data,prefer_infomax=True)

if __name__=='__main__': unittest.main()
