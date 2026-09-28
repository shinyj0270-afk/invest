import copy
import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from infomax_user_policy import apply_observed_flow_policy, apply_analysis_basis


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.decisions=json.loads((ROOT/'config/infomax.user-decisions.json').read_text(encoding='utf-8'))['decisions']
        self.dates=[f'2026-09-{n:02d}' for n in range(1,22)]
        self.data={'prices':{'X':{d:{'누적거래대금':1e8} for d in self.dates}},
                   'flows':{'X':{d:{'외국인순매수금액':1000,'기관순매수금액':-2000} for d in self.dates}}}
        self.row={'code':'X','metrics':{},'metric_missing_reasons':{}}

    def test_units_signed_totals_and_unknown_scope_preserved(self):
        apply_observed_flow_policy(self.row,self.data,self.dates[-20:],self.decisions)
        m=self.row['metrics']
        self.assertEqual(m['avg_trading_value_20d_eok'],1)
        self.assertEqual(m['foreign_net_20d_eok'],0.2)
        self.assertEqual(m['institution_net_20d_eok'],-0.4)
        self.assertEqual(m['foreign_net_turnover_20d_pct'],1)
        self.assertEqual(m['institution_net_turnover_20d_pct'],-2)
        e=self.row['user_policy_evidence']
        self.assertIsNone(e['price_venue'])
        self.assertFalse(e['official_calendar_verified'])
        self.assertFalse(e['prices_final'])
        self.assertFalse(e['venue_comparability_confirmed'])
        self.assertIn(self.decisions['flow_turnover_scope_comparability']['required_label'],e['labels'])

    def test_krx_basis_preserves_raw_values_and_unverified_facts(self):
        snapshot={'meta':{'warnings':['거래소 범위 미확인','공식 거래일 미대조']},
                  'companies':[{'metrics':{'price':123,'roe_pct':10},
                                'prices':[{'close':123,'venue':None,'final':False}],
                                'data_quality':['거래소 범위 미확인'],
                                'user_policy_evidence':{'labels':['공식 거래일 미대조'],
                                                        'price_venue':None,'prices_final':False}}]}
        original=copy.deepcopy(snapshot)
        apply_analysis_basis(snapshot,self.decisions)
        self.assertEqual(snapshot['meta']['analysis_venue'],'KRX')
        self.assertFalse(snapshot['meta']['market_data_policy']['official_calendar_required'])
        self.assertEqual(snapshot['companies'][0]['metrics'],original['companies'][0]['metrics'])
        self.assertEqual(snapshot['companies'][0]['prices'],original['companies'][0]['prices'])
        self.assertIsNone(snapshot['companies'][0]['user_policy_evidence']['price_venue'])
        again=copy.deepcopy(snapshot)
        self.assertEqual(apply_analysis_basis(snapshot,self.decisions),again)

    def test_no_krx_basis_inferred(self):
        decisions=copy.deepcopy(self.decisions)
        decisions['unknown_venue'].pop('analysis_venue')
        snapshot={'meta':{},'companies':[]}
        self.assertEqual(apply_analysis_basis(snapshot,decisions),{'meta':{},'companies':[]})

    def test_ratio_requires_explicit_approval(self):
        del self.decisions['flow_turnover_scope_comparability']
        apply_observed_flow_policy(self.row,self.data,self.dates[-20:],self.decisions)
        self.assertIsNone(self.row['metrics']['foreign_net_turnover_20d_pct'])

    def test_zero_or_missing_turnover_blocks_ratio(self):
        for bad in (0,None):
            for item in self.data['prices']['X'].values(): item['누적거래대금']=bad
            apply_observed_flow_policy(self.row,self.data,self.dates[-20:],self.decisions)
            self.assertIsNone(self.row['metrics']['foreign_net_turnover_20d_pct'])
            self.assertIn('foreign_net_turnover_20d_pct',self.row['metric_missing_reasons'])

    def test_ratio_uses_total_not_daily_average(self):
        self.data['prices']['X'][self.dates[-1]]['누적거래대금']=3e8
        apply_observed_flow_policy(self.row,self.data,self.dates[-20:],self.decisions)
        self.assertAlmostEqual(self.row['metrics']['foreign_net_turnover_20d_pct'],2e7/22e8*100)

    def test_missing_value_not_zero(self):
        self.data['flows']['X'][self.dates[-1]]['외국인순매수금액']=None
        apply_observed_flow_policy(self.row,self.data,self.dates[-20:],self.decisions)
        self.assertNotIn('foreign_net_20d_eok',self.row['metrics'])
        self.assertIsNone(self.row['metrics']['foreign_net_turnover_20d_pct'])

    def test_incomplete_approval_no_release(self):
        del self.decisions['revision_finality']
        apply_observed_flow_policy(self.row,self.data,self.dates[-20:],self.decisions)
        self.assertEqual(self.row['metrics'],{})

    def test_stale_window_rejected(self):
        with self.assertRaises(ValueError):
            apply_observed_flow_policy(self.row,self.data,self.dates[:20],self.decisions)

if __name__=='__main__': unittest.main()
