import copy,math,unittest
from investment.portfolio_risk import compare_portfolios,common_window,portfolio_risk
from investment.recommendation_allocation import choose_and_allocate,capped_weights,RECOMMENDATION_POLICY
from tests.test_portfolio_risk import risk_fixture
from investment.recommendations import current_risk_views


class RiskReviewTests(unittest.TestCase):
    def setUp(self):self.targets,self.cache,self.cutoff=risk_fixture()
    def composition(self,targets,cash=20):return dict(targets=targets,cash_pct=cash,created_on='2026-10-07')

    def test_same_universe_unequal_history_exact_expected(self):
        self.cache['history']['histories']['900002']['prices']=self.cache['history']['histories']['900002']['prices'][-100:]
        old=self.composition(self.targets)
        new=self.composition([dict(self.targets[0],code='900002',weight_pct=80)])
        r=compare_portfolios(new,old,self.cache,self.cutoff)
        self.assertEqual(r['status'],'ready');self.assertEqual(r['window']['observations'],99)
        self.assertEqual(r['proposed']['start_date'],r['previous']['start_date'])
        self.assertEqual(r['proposed']['as_of'],r['previous']['as_of'])
        self.assertAlmostEqual(r['deltas']['annual_volatility_pct'],0,places=8)
        self.assertIn('concentration_increased',r['flags']);self.assertEqual(r['policy_status'],'not_configured')

    def test_diversified_alternative_reduces_covariance_risk(self):
        old=self.composition(self.targets)
        new=self.composition([self.targets[0],dict(self.targets[1],code='900002',industry='다른 산업')])
        r=compare_portfolios(new,old,self.cache,self.cutoff)
        self.assertAlmostEqual(r['proposed']['annual_volatility_pct'],0,places=8)
        self.assertLess(r['deltas']['annual_volatility_pct'],0)
        self.assertAlmostEqual(r['proposed']['max_drawdown_pct'],0,places=8)

    def test_cash_comparison_and_pending_no_numeric_deltas(self):
        r=compare_portfolios(self.composition([],100),self.composition(self.targets),self.cache,self.cutoff)
        self.assertEqual(r['status'],'ready');self.assertLess(r['deltas']['annual_volatility_pct'],0)
        del self.cache['history']['histories']['900001']['prices'][-5]
        r=compare_portfolios(self.composition(self.targets),self.composition([],100),self.cache,self.cutoff)
        self.assertEqual(r['status'],'pending');self.assertEqual(r['deltas'],{});self.assertIn('missing_price',r['flags'])

    def test_override_cannot_hide_missing_middle_session(self):
        dates=common_window(self.targets,self.cache,self.cutoff);removed=dates.pop(90)
        for t in self.targets:self.cache['history']['histories'][t['code']]['prices']=[p for p in self.cache['history']['histories'][t['code']]['prices'] if p['date']!=removed]
        r=portfolio_risk(self.targets,20,self.cache,self.cutoff,observation_dates=dates)
        self.assertEqual(r['status'],'pending')
        r=compare_portfolios(self.composition(self.targets),self.composition(self.targets),self.cache,self.cutoff,observation_dates=dates)
        self.assertEqual(r['status'],'pending');self.assertEqual(r['deltas'],{})

    def test_future_cutoff_and_mutation(self):
        original=copy.deepcopy((self.cache,self.targets));composition=self.composition(self.targets)
        r=compare_portfolios(composition,composition,self.cache,self.cutoff)
        for h in self.cache['history']['histories'].values():h['prices'].append(dict(h['prices'][-1],date='2030-01-01',close=999999,final=False))
        self.assertEqual(compare_portfolios(composition,composition,self.cache,self.cutoff),r)
        self.assertEqual(self.targets,original[1])

    def test_confirmed_bounds_validate_effective_decision_date(self):
        r=compare_portfolios(self.composition(self.targets),self.composition(self.targets),self.cache,self.cutoff,RECOMMENDATION_POLICY)
        self.assertEqual(r['policy_status'],'within_limits')
        r=compare_portfolios(self.composition([dict(self.targets[0],weight_pct=95)],5),None,self.cache,self.cutoff,RECOMMENDATION_POLICY)
        self.assertEqual(r['policy_status'],'violated');self.assertIn('max_position_pct',r['policy_violations'])
        p=dict(RECOMMENDATION_POLICY,effective_on='2030-01-01')
        self.assertEqual(compare_portfolios(self.composition(self.targets),None,self.cache,self.cutoff,p)['policy_status'],'pending')

    def test_inverse_vol_capping_and_disclosed_missing_candidates(self):
        shortlist=[dict(t,score=100-i) for i,t in enumerate(self.targets)]+[dict(self.targets[1],code='900002',industry='다른 산업',score=98),dict(self.targets[0],code='NOHIST',score=97)]
        r=choose_and_allocate(shortlist,self.cache,self.cutoff)
        self.assertEqual(r['status'],'ready');self.assertEqual(len(r['targets']),3)
        self.assertEqual(r['risk_unavailable_candidates'][0]['code'],'NOHIST')
        self.assertEqual(r['targets'][1]['code'],'900002')
        self.assertAlmostEqual(sum(t['weight_pct'] for t in r['targets'])+r['cash_pct'],100)
        self.assertGreaterEqual(r['cash_pct'],5);self.assertTrue(all(t['weight_pct']<=40 for t in r['targets']))
        self.assertEqual(capped_weights([100,1,1],95,40),[40,27.5,27.5])

    def test_safe_fallback_one_position_and_zero_vol(self):
        one=choose_and_allocate([dict(self.targets[0],score=10)],None,self.cutoff)
        self.assertEqual(one['state'],'SAFE_DEFAULT');self.assertEqual(one['targets'][0]['weight_pct'],40);self.assertEqual(one['cash_pct'],60)
        for p in self.cache['history']['histories']['900000']['prices']:p['close']=100
        flat=choose_and_allocate([dict(self.targets[0],score=10)],self.cache,self.cutoff)
        self.assertEqual(flat['state'],'SAFE_DEFAULT');self.assertIn('변동성 0',flat['reason'])

    def test_floating_allocation_respects_strict_returned_bounds(self):
        weights=capped_weights([1.1,2.2,3.3,4.4],95,40);cash=100-sum(weights)
        self.assertGreaterEqual(cash,5);self.assertTrue(all(w<=40 for w in weights));self.assertEqual(sum(weights)+cash,100)
        proposed=self.composition([dict(self.targets[0],code=str(i),weight_pct=w) for i,w in enumerate(weights)],cash)
        self.assertEqual(compare_portfolios(proposed,None,self.cache,self.cutoff,RECOMMENDATION_POLICY)['policy_status'],'within_limits')

    def test_current_saved_alternatives_use_verified_identity_and_one_window(self):
        record=self.composition(self.targets);record['alternatives']=[dict(code='900002',name='가상 대안',replaces='900001')]
        self.cache['universe']={'companies':[dict(code='900002',name='가상 대안',market='KOSDAQ',industry='검증 산업')]}
        self.cache['history']['histories']['900002']['prices']=self.cache['history']['histories']['900002']['prices'][-100:]
        original=copy.deepcopy((record,self.cache))
        result=current_risk_views(record,record,self.cache,self.cutoff,'2026-10-07')
        alternative=result['current_risk_alternatives'][0]
        self.assertEqual(alternative['review']['status'],'ready')
        self.assertEqual(alternative['review']['window'],result['current_risk_review']['window'])
        self.assertEqual(alternative['review']['window']['observations'],99)
        self.assertEqual(alternative['review']['proposed']['concentration']['sector_weights']['검증 산업'],40)
        self.assertIn('재검증한 추천이 아닙니다',alternative['advisory'])
        self.assertEqual((record,self.cache),original)
        self.cache['universe']['companies'][0]['name']='다른 기업'
        self.assertEqual(current_risk_views(record,record,self.cache,self.cutoff,'2026-10-07')['current_risk_alternatives'][0]['review']['status'],'pending')

    def test_current_alternative_missing_session_blocks_comparison_deltas(self):
        record=self.composition(self.targets);record['alternatives']=[dict(code='900002',name='가상 대안',replaces='900001')]
        self.cache['universe']={'companies':[dict(code='900002',name='가상 대안',market='KOSPI',industry='다른 산업')]}
        del self.cache['history']['histories']['900002']['prices'][-10]
        result=current_risk_views(record,record,self.cache,self.cutoff,'2026-10-07')
        for review in [result['current_risk_review'],result['current_risk_alternatives'][0]['review']]:
            self.assertEqual(review['status'],'pending');self.assertEqual(review['deltas'],{})

if __name__=='__main__':unittest.main()
