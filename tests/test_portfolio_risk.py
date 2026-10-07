"""Independent arithmetic checks using labelled synthetic prices only."""
import copy,json,math,unittest
from datetime import date,timedelta
from unittest.mock import patch
from investment.portfolio_risk import portfolio_risk,time_series
from investment.recommendations import RecommendationBook,propose,performance
from tests.test_dashboard_upgrade import recommendation_context


def risk_fixture():
    days=[];d=date(2025,1,1)
    while len(days)<253:
        if d.weekday()<5:days.append(d.isoformat())
        d+=timedelta(days=1)
    def bars(sign=1,flat=False):
        close=100.;out=[]
        for i,day in enumerate(days):
            if i:close*=1+(0 if flat else sign*(.1 if i%2 else -.1))
            out.append(dict(date=day,close=close,final=True,venue='KRX',adjustment_basis='naver_chart_adjusted'))
        return out
    indexes={m:dict(symbol=m,kind='index',source={'url':'https://example.test/synthetic-index'},
        prices=[dict(p,adjustment_basis='index_level') for p in bars(flat=True)]) for m in ('KOSPI','KOSDAQ')}
    histories={code:dict(symbol=code,kind='item',source={'provider':'가상 검증 가격'},prices=bars(sign))
        for code,sign in [('900000',1),('900001',1),('900002',-1)]}
    cache={'history':dict(benchmarks=indexes,histories=histories,calendar={'valid_through':days[-1]})}
    targets=[dict(code=code,name='가상 '+code,market='KOSPI',industry='가상 산업',weight_pct=40) for code in ('900000','900001')]
    return targets,cache,days[-1]


class PerformancePriceContractTests(unittest.TestCase):
    def setUp(self):
        self.targets,self.cache,self.cutoff=risk_fixture()
        self.record=dict(created_on='2025-01-01',targets=self.targets,cash_pct=20)

    def test_fixed_initial_weights_use_verified_first_following_session(self):
        before=copy.deepcopy(self.cache);r=performance(self.record,self.cache)
        self.assertEqual(r['status'],'ready');self.assertEqual(r['entry_date'],'2025-01-02')
        expected=sum((self.cache['history']['histories'][t['code']]['prices'][-1]['close']/self.cache['history']['histories'][t['code']]['prices'][1]['close']-1)*t['weight_pct'] for t in self.targets)
        self.assertAlmostEqual(r['return_pct'],expected);self.assertEqual(r['benchmark_returns'],dict(KOSPI=0,KOSDAQ=0));self.assertEqual(self.cache,before)

    def test_unverified_price_identity_venue_basis_and_calendar_are_pending(self):
        for field,value in [('symbol','999999'),('kind','index'),('venue','NXT'),('adjustment_basis','unverified'),('final',False),('close',float('nan')),('close',0)]:
            with self.subTest(field=field,value=value):
                cache=copy.deepcopy(self.cache);series=cache['history']['histories']['900000']
                (series if field in ('symbol','kind') else series['prices'][-1])[field]=value
                result=performance(self.record,cache);self.assertEqual(result['status'],'pending');self.assertNotIn('return_pct',result)
        for market in ('KOSPI','KOSDAQ'):
            cache=copy.deepcopy(self.cache);cache['history']['benchmarks'][market]['prices'][-1]['final']=False
            self.assertEqual(performance(self.record,cache)['status'],'pending')
        cache=copy.deepcopy(self.cache);cache['history']['histories']['900001']['prices']=[dict(p,adjustment_basis='split_adjusted') for p in cache['history']['histories']['900001']['prices']]
        self.assertEqual(performance(self.record,cache)['status'],'pending')

    def test_missing_intermediate_entry_or_last_session_never_becomes_zero(self):
        for index in (1,-10,-1):
            cache=copy.deepcopy(self.cache);del cache['history']['histories']['900000']['prices'][index]
            result=performance(self.record,cache);self.assertEqual(result['status'],'missing');self.assertNotIn('return_pct',result)
        cache=copy.deepcopy(self.cache);cache['history']['histories']['900000']['prices'].append(copy.deepcopy(cache['history']['histories']['900000']['prices'][-1]))
        self.assertEqual(performance(self.record,cache)['status'],'pending')

    def test_no_minimum_risk_window_or_future_price_leakage(self):
        self.record['created_on']=self.cache['history']['histories']['900000']['prices'][-3]['date']
        before=performance(self.record,self.cache);self.assertEqual(before['status'],'ready')
        for series in self.cache['history']['histories'].values():series['prices'].append(dict(series['prices'][-1],date='2030-01-01',close=1e9,final=False))
        self.assertEqual(performance(self.record,self.cache),before)


class PortfolioRiskTests(unittest.TestCase):
    def setUp(self):self.targets,self.cache,self.cutoff=risk_fixture()

    def test_identical_returns_covariance_cash_and_known_path(self):
        original=copy.deepcopy(self.cache)
        r=portfolio_risk(self.targets,20,self.cache,self.cutoff)
        self.assertEqual(r['status'],'ready');self.assertEqual(r['observations'],252)
        # Exactly 126 pairs +8%/-8%, mean 0, sample variance with n-1.
        expected_vol=.08*math.sqrt(252/251)*math.sqrt(252)*100
        self.assertAlmostEqual(r['annual_volatility_pct'],expected_vol)
        self.assertAlmostEqual(r['return_pct'],((1.08*.92)**126-1)*100)
        # The first up day is the historical peak; every pair subsequently declines.
        self.assertAlmostEqual(r['max_drawdown_pct'],((1.08*.92)**126/1.08-1)*100)
        self.assertAlmostEqual(r['correlations'][0][1],1)
        self.assertAlmostEqual(sum(p['volatility_contribution_pp'] for p in r['risk_contributions']),expected_vol)
        self.assertEqual(r['concentration']['equity_hhi'],.5)
        self.assertEqual(r['concentration']['sector_weights'],{'가상 산업':80})
        self.assertEqual(self.cache,original);json.dumps(r,allow_nan=False)

    def test_negative_correlation_reduces_total_risk(self):
        self.targets[1]['code']='900002'
        r=portfolio_risk(self.targets,20,self.cache,self.cutoff)
        self.assertAlmostEqual(r['correlations'][0][1],-1)
        self.assertAlmostEqual(r['annual_volatility_pct'],0,places=10)
        self.assertAlmostEqual(r['max_drawdown_pct'],0,places=10)

    def test_flat_price_correlation_is_unknown(self):
        for p in self.cache['history']['histories']['900000']['prices']:p['close']=100
        r=portfolio_risk(self.targets,20,self.cache,self.cutoff)
        self.assertIsNone(r['correlations'][0][1])
        self.assertAlmostEqual(r['risk_contributions'][0]['volatility_contribution_pp'],0)

    def test_hedging_name_can_have_negative_risk_contribution(self):
        self.targets[0]['weight_pct']=20
        self.targets[1].update(code='900002',weight_pct=60)
        r=portfolio_risk(self.targets,20,self.cache,self.cutoff)
        self.assertLess(r['risk_contributions'][0]['volatility_contribution_pp'],0)
        self.assertAlmostEqual(sum(p['volatility_contribution_pp'] for p in r['risk_contributions']),r['annual_volatility_pct'])

    def test_missing_session_or_last_price_never_uses_zero_return(self):
        for index in (-10,-1):
            cache=copy.deepcopy(self.cache);del cache['history']['histories']['900000']['prices'][index]
            r=portfolio_risk(self.targets,20,cache,self.cutoff)
            self.assertEqual(r['status'],'pending');self.assertNotIn('annual_volatility_pct',r)
            self.assertIn('900000',r['reason']);self.assertIn('concentration',r)

    def test_invalid_identity_basis_dates_prices_and_calendar(self):
        for field,value in [('final',False),('close',float('nan')),('close',float('inf')),('close',0),('venue','NXT'),('adjustment_basis','unverified')]:
            cache=copy.deepcopy(self.cache);cache['history']['histories']['900000']['prices'][-1][field]=value
            self.assertEqual(portfolio_risk(self.targets,20,cache,self.cutoff)['status'],'pending')
        cache=copy.deepcopy(self.cache);cache['history']['histories']['900000']['prices'].append(copy.deepcopy(cache['history']['histories']['900000']['prices'][-1]))
        self.assertEqual(portfolio_risk(self.targets,20,cache,self.cutoff)['status'],'pending')
        cache=copy.deepcopy(self.cache);cache['history']['histories']['900000']['symbol']='other'
        self.assertEqual(portfolio_risk(self.targets,20,cache,self.cutoff)['status'],'pending')
        cache=copy.deepcopy(self.cache);del cache['history']['benchmarks']['KOSDAQ']['prices'][-8]
        self.assertEqual(portfolio_risk(self.targets,20,cache,self.cutoff)['status'],'pending')

    def test_no_future_leakage_and_too_short_history(self):
        before=portfolio_risk(self.targets,20,self.cache,self.cutoff)
        for rec in self.cache['history']['histories'].values():
            rec['prices'].append(dict(rec['prices'][-1],date='2030-01-01',close=999999,final=False))
        self.assertEqual(portfolio_risk(self.targets,20,self.cache,self.cutoff),before)
        self.cache['history']['histories']['900000']['prices']=self.cache['history']['histories']['900000']['prices'][-30:-1]
        self.assertEqual(portfolio_risk(self.targets,20,self.cache,self.cutoff)['status'],'pending')

    def test_invalid_weights_duplicate_six_names_and_cash_only(self):
        for targets,cash in [(self.targets,0),(self.targets+[self.targets[0]],20),([dict(self.targets[0],code=str(i),weight_pct=10) for i in range(6)],40),([dict(self.targets[0],weight_pct=True)],99)]:
            self.assertEqual(portfolio_risk(targets,cash,self.cache,self.cutoff)['status'],'pending')
        r=portfolio_risk([],100,None,None);self.assertEqual(r['status'],'cash_only');self.assertIsNone(r['concentration']['equity_hhi'])

    def test_time_series_known_returns_rolling_warmup_and_gaps(self):
        ps=self.cache['history']['histories']['900000']['prices'];bm=self.cache['history']['benchmarks']['KOSPI']['prices']
        r=time_series(ps,bm,self.cutoff)
        self.assertEqual(r['status'],'ready')
        self.assertAlmostEqual(r['return_pct'],(.99**126-1)*100)
        self.assertAlmostEqual(r['series'][-1]['excess_return_pp'],r['return_pct'])
        self.assertIsNone(r['series'][19]['volatility20_pct'])
        self.assertAlmostEqual(r['series'][20]['volatility20_pct'],.1*math.sqrt(20/19)*math.sqrt(252)*100)
        del ps[-8];self.assertEqual(time_series(ps,bm,self.cutoff)['status'],'pending')

    def test_recommendation_initial_and_current_risk_do_not_rewrite_book(self):
        context=recommendation_context();context['_risk_cache']=self.cache
        # Existing screening may choose other fixture codes; explicit absent series stay pending.
        record=propose(context,created_on='2026-10-02')
        self.assertIn('portfolio_risk',record);self.assertNotIn('_risk_cache',record)
        record['targets']=self.targets;record['cash_pct']=20
        stored={'version':1,'records':[record]};original=copy.deepcopy(stored)
        book=object.__new__(RecommendationBook)
        with patch.object(book,'read',return_value=stored),patch('investment.recommendations.performance',return_value={'status':'pending'}):
            view=book.view(self.cache)
        self.assertEqual(view['records'][0]['current_portfolio_risk']['status'],'ready')
        self.assertEqual(stored,original)


if __name__=='__main__':unittest.main()
