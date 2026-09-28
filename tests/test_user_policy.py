import copy
import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from infomax_user_policy import apply_observed_flow_policy


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
        self.assertIn('거래소 범위 동일성 미확인',e['labels'])

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
