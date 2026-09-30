"""Offline synthetic tests for saved-data portfolio validation."""
import copy
import json
from pathlib import Path
import subprocess
import unittest

from tests import test_infomax_daily
from tools.verify_portfolio_data import verify

ROOT = Path(__file__).resolve().parents[1]


class PortfolioDataTests(unittest.TestCase):
    def setUp(self):
        helper = test_infomax_daily.DailyImportTests()
        helper.setUp()
        self.snapshot = helper.convert()

    def test_unconfirmed_settings_and_unknown_research_are_separate(self):
        result = verify(self.snapshot, as_of='2026-09-30')
        self.assertEqual(result['verification_status'], 'passed')
        self.assertEqual(result['portfolio_status'], 'SETTINGS_REQUIRED')
        self.assertEqual(result['ready_count'], 0)
        self.assertIsNone(result['cash_pct'])

    def test_confirmed_settings_cannot_turn_missing_data_into_cash_only(self):
        result = verify(self.snapshot, policy=dict(policyConfirmed=True, stressLossLimitPct=25),
                        as_of='2026-09-30')
        self.assertEqual(result['portfolio_status'], 'DATA_REQUIRED')
        self.assertEqual(result['selected'], [])
        self.assertIsNone(result['cash_pct'])
        self.assertIn('공통 위험군 미확인', result['candidates'][0]['reasons'])

    def test_stale_and_missing_prices_are_reported_without_changing_source(self):
        before = copy.deepcopy(self.snapshot)
        result = verify(self.snapshot, as_of='2026-10-10')
        self.assertIn('가격 누락·미래·설정 기한 초과', result['candidates'][0]['reasons'])
        self.assertEqual(self.snapshot, before)
        del self.snapshot['companies'][0]['prices']
        self.assertEqual(verify(self.snapshot)['ready_count'], 0)

    def test_fixture_market_cannot_masquerade_as_real(self):
        self.snapshot['meta']['data_mode'] = 'fixture'
        with self.assertRaises(ValueError):
            verify(self.snapshot)

    def test_allocation_constraints_use_explicit_synthetic_scenarios(self):
        script = r'''
const assert=require('assert/strict'),P=require('./src/portfolio_engine.js');
const {checkPortfolio}=require('./tools/portfolio_check.js');
const policy={policyConfirmed:true,stressLossLimitPct:25};
let x=P.fixture(),result=checkPortfolio(x,policy);
assert.equal(result.mode,'fixture');assert.equal(result.selected.length,5);assert.equal(result.cash_pct,20);
assert.equal(checkPortfolio(x,{...policy,maxCompanies:2}).selected.length,2);
x=P.fixture();x.research.forEach(r=>r.risk_group='shared synthetic exposure');
result=checkPortfolio(x,policy);assert.ok(result.selected.reduce((s,r)=>s+r.weight_pct,0)<=40);
x=P.fixture();x.research[1].issuer_id=x.research[0].issuer_id;
result=checkPortfolio(x,policy);assert.equal(new Set(result.selected.map(r=>r.issuer_id)).size,result.selected.length);
result=checkPortfolio(P.fixture(),{...policy,stressLossLimitPct:10});assert.ok(result.cash_pct>=66.66);
x=P.fixture();x.research.forEach(r=>r.review.thesis='unknown');
result=checkPortfolio(x,policy);assert.equal(result.portfolio_status,'DATA_REQUIRED');assert.equal(result.cash_pct,null);
x=P.fixture();x.research.forEach(r=>r.review.thesis='broken');
result=checkPortfolio(x,policy);assert.equal(result.portfolio_status,'CASH_ONLY');assert.equal(result.cash_pct,100);
assert.throws(()=>checkPortfolio(P.fixture(),{...policy,maxCompanies:6}));
console.log('PASS 8 synthetic allocation scenarios');
'''
        result = subprocess.run(['node', '-e', script], cwd=ROOT, capture_output=True,
                                text=True, encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
