import copy,json,tempfile,unittest
from datetime import date,datetime,timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
from investment.financial_metrics import common_metrics,apply_common
from investment.market_history import completed_cutoff,parse_history
from investment.market_insights import enrich_market,reconcile_prices
from investment.recommendations import propose,performance,RecommendationBook,minimum_financial_period

def column(day,revenue=100,profit=10,book=100):
    return dict(period_end=day,available_at=day,source='가상 검증 자료',statement_values=dict(revenue=revenue,operating_profit=profit,net_income=profit,parent_net=profit,parent_equity=book,assets=200,equity=book,liabilities=100,ocf=20,total_borrowings=30))

class FinancialContractTests(unittest.TestCase):
    def setUp(self):
        self.row=dict(code='900000',name='가상',market='KOSPI',metrics={'roe_pct':999},latest_quote=dict(price=100,market_cap_eok=200,retrieved_at='2026-10-02T10:00:00+09:00'))
        self.q=[column(d) for d in ('2025-06-30','2025-09-30','2025-12-31','2026-03-31','2026-06-30')]
        self.q[-1]['statement_values']['revenue']=150
        self.table=dict(groups=[dict(basis='CFS',cadence='quarter',columns=self.q)])
        self.t=dict(close=90,as_of='2026-10-01')
    def test_common_period_units_ttm_growth_and_estimate(self):
        r=common_metrics(self.row,self.table,self.t)
        self.assertAlmostEqual(r['metrics']['revenue_growth_pct'],50)
        self.assertAlmostEqual(r['metrics']['roe_pct'],40)
        self.assertAlmostEqual(r['metrics']['per'],4.5)
        self.assertEqual(r['metric_details']['per']['status'],'estimated')
        self.assertEqual(r['amounts']['revenue'],150)
        facts={'fundamental':{}};apply_common(self.row,facts,r)
        self.assertEqual(self.row['metrics']['roe_pct'],facts['fundamental']['metrics']['roe_pct'])
    def test_missing_parent_never_uses_total_profit_or_zero(self):
        for c in self.q:c['statement_values']['parent_net']=None
        r=common_metrics(self.row,self.table,self.t)
        self.assertIsNone(r['metrics']['per']);self.assertIsNone(r['metrics']['roe_pct'])

    def test_tolerated_source_note_keeps_usable_value_and_propagates(self):
        self.q[-1]['cell_notes']={'parent_net':'원문 명시 계정 참고 사용 · 귀속 합계 잔차 1000000원'}
        r=common_metrics(self.row,self.table,self.t)
        self.assertAlmostEqual(r['metrics']['roe_pct'],40)
        self.assertEqual(r['metric_details']['roe_pct']['status'],'reference_with_tolerance')
        self.assertTrue(r['metric_details']['per']['within_tolerance'])
        self.assertIn('잔차',r['metric_details']['per']['reason'])
        self.assertNotIn('within_tolerance',r['metric_details']['pbr'])
    def test_nonconsecutive_ttm_and_stale_cap_withhold(self):
        self.q.pop(-2);self.row['latest_quote']['retrieved_at']='2026-10-10T10:00:00+09:00'
        r=common_metrics(self.row,self.table,self.t)
        self.assertFalse(r['ttm_complete']);self.assertIsNone(r['metrics']['per']);self.assertIsNone(r['metrics']['pbr'])
    def test_standalone_only_keeps_explicit_basis_and_uses_total_profit(self):
        self.table['groups'][0]['basis']='OFS'
        r=common_metrics(self.row,self.table,self.t)
        self.assertEqual(r['basis'],'OFS');self.assertAlmostEqual(r['metrics']['roe_pct'],40)
        self.assertIn('별도',r['metric_details']['roe_pct']['reason'])

    def test_reviewed_priority_requires_identical_period_and_basis(self):
        r=common_metrics(self.row,self.table,self.t);self.row['metric_details']={'roe_pct':dict(status='reviewed',period='2026-06-30',basis='CFS')}
        apply_common(self.row,{'fundamental':{}},r);self.assertEqual(self.row['metrics']['roe_pct'],999)
        self.row['metric_details']['roe_pct'].update(period='2025-12-31');apply_common(self.row,{'fundamental':{}},r);self.assertEqual(self.row['metrics']['roe_pct'],40)

class DailyPolicyTests(unittest.TestCase):
    def test_after_close_boundary_weekend_and_future(self):
        tz=ZoneInfo('Asia/Seoul');morning=datetime(2026,10,2,20,29,tzinfo=tz);evening=datetime(2026,10,2,20,30,tzinfo=tz)
        self.assertEqual(completed_cutoff(datetime(2026,10,2,18,30,tzinfo=tz),True).isoformat(),'2026-10-01')
        self.assertEqual(str(completed_cutoff(morning,True)),'2026-10-01');self.assertEqual(str(completed_cutoff(evening,True)),'2026-10-02')
        self.assertEqual(str(completed_cutoff(datetime(2026,10,3,19,tzinfo=tz),True)),'2026-10-02')
        payload=json.dumps([{'localDate':'20261002','closePrice':100},{'localDate':'20261005','closePrice':999}]).encode()
        r=parse_history(payload,symbol='900000',kind='item',start='2026-10-01',end='2026-10-02',fetched_at=evening,allow_same_day=True)
        self.assertEqual(r['price_date'],'2026-10-02');self.assertEqual(len(r['prices']),1);self.assertIn('공식 확정 보증 아님',r['source']['final_basis'])

class MarketContextTests(unittest.TestCase):
    def test_short_ties_sector_weighting_and_small_sector_wait(self):
        rows=[];facts={};hist={}
        for i in range(6):
            code=str(900000+i);rows.append(dict(code=code,market='KOSPI',industry='가상 산업' if i<5 else '소수',metrics={'market_cap_eok':1000},discovery_allowed=True))
            ps=[dict(date=f'{j:04}',close=100+j,volume=1) for j in range(150)]
            hist[code]={'prices':ps};facts[code]={'technical':dict(close=249,as_of='0149',sma={'50':200,'200':None})}
        d=dict(snapshot={'meta':{'price_date':'0149'},'companies':rows},research={'rows':facts})
        result=enrich_market(d,{'history':{'histories':hist}})
        self.assertEqual(facts['900000']['technical']['short_rs']['1m']['score'],50)
        self.assertEqual(result['sectors'][0]['short_rs']['1m']['score'],50)
        self.assertIsNone(result['sectors'][1]['short_rs']['1m']['score']);self.assertEqual(result['markets'][0]['above']['50']['pct'],100)
    def test_different_basis_is_not_false_price_error(self):
        row={'prices':[dict(date='2026-10-01',close=100,venue='KRX',adjustment_basis='provider_adjusted')]}
        record={'prices':[dict(date='2026-10-01',close=101,venue='KRX',adjustment_basis='naver_chart_adjusted')]}
        check=reconcile_prices(row,record)['checks'][0]
        self.assertFalse(check['comparable']);self.assertEqual(check['status'],'기준 대조 필요')

def recommendation_context():
    rows=[];facts={}
    for i in range(7):
        code=str(900000+i);rows.append(dict(code=code,name='가상'+str(i),market='KOSPI',industry='산업'+str(i//2),discovery_allowed=True,
            common_financial=dict(basis='CFS',period='2026-06-30',ttm_complete=True,ttm_ocf=20,metrics=dict(revenue_growth_pct=20,operating_margin_pct=10,roe_pct=15,debt_ratio_pct=50),metric_details={'roe_pct':{'source':'가상 검증 자료'}})))
        facts[code]={'technical':dict(close=100,price_trend_status='pass',sma={'200':90},price_strength={'score':90-i},short_rs={'1m':{'score':80}},gap_to_52w_high_pct=-5)}
    return dict(snapshot={'meta':{'price_date':'2026-10-01'},'companies':rows},research={'rows':facts})

class RecommendationTests(unittest.TestCase):
    def test_publication_window_keeps_month_start_candidates(self):
        cases=[('2027-01-04','2026-09-30'),('2026-05-04','2025-12-31'),
               ('2026-08-03','2026-03-31'),('2026-11-02','2026-06-30'),
               ('2026-10-02','2026-06-30')]
        for day,period in cases:
            with self.subTest(day=day,period=period):
                c=recommendation_context()
                c['snapshot']['meta']['price_date']=(date.fromisoformat(day)-timedelta(days=1)).isoformat()
                for row in c['snapshot']['companies']:row['common_financial']['period']=period
                r=propose(c,created_on=day)
                self.assertEqual(len(r['targets']),5)
                self.assertEqual(r['cash_pct'],5)

    def test_freshness_floor_changes_after_filing_months(self):
        expected=['2025-09-30']*3+['2025-12-31']*2+['2026-03-31']*3+['2026-06-30']*3+['2026-09-30']
        for month,period in enumerate(expected,1):
            with self.subTest(month=month):
                self.assertEqual(minimum_financial_period(date(2026,month,1)),period)
        c=recommendation_context()
        for row in c['snapshot']['companies']:row['common_financial']['period']='2026-03-31'
        self.assertEqual(propose(c,created_on='2026-10-02')['targets'],[])

    def test_weights_industry_cash_and_exception_reason(self):
        c=recommendation_context();r=propose(c,created_on='2026-10-02')
        self.assertEqual(sum(t['weight_pct'] for t in r['targets'])+r['cash_pct'],100);self.assertEqual(len(r['targets']),5)
        self.assertTrue(all(t['weight_pct']<=40 for t in r['targets']));self.assertGreaterEqual(r['cash_pct'],5)
        with self.assertRaises(ValueError):propose(c,created_on='2026-10-02',kind='exception')
        second=propose(c,created_on='2026-10-02',kind='exception',reason='가상 공시 검토',previous=r)
        self.assertTrue(all(t['action']=='유지' for t in second['changes']))
    def test_no_false_success_with_missing_financials(self):
        c=recommendation_context()
        for r in c['snapshot']['companies']:r.pop('common_financial')
        with self.assertRaises(ValueError):propose(c,created_on='2026-10-02')
    def test_performance_never_uses_price_before_publication_or_missing_as_zero(self):
        from tests.test_portfolio_risk import risk_fixture
        _,cache,cutoff=risk_fixture();bars=cache['history']['histories']['900000']['prices']
        r=dict(created_on=bars[-3]['date'],targets=[dict(code='900000',name='가상',weight_pct=80)],cash_pct=20)
        bars[-3]['close']=10;bars[-2]['close']=100;bars[-1]['close']=110
        value=performance(r,cache);self.assertEqual(value['entry_date'],bars[-2]['date']);self.assertAlmostEqual(value['return_pct'],8)
        cache['history']['histories']['900000']['prices'].pop();self.assertEqual(performance(r,cache)['status'],'missing')
    def test_monthly_idempotency_and_immutable_prior_version(self):
        with tempfile.TemporaryDirectory() as tmp,patch('investment.recommendations.load_local',return_value={'data_dir':Path(tmp),'profile':'test'}):
            book=RecommendationBook('.');c=recommendation_context();a=book.append(c,today='2026-10-02');first=copy.deepcopy(a['records'][0])
            self.assertEqual(len(book.append(c,today='2026-10-03')['records']),1)
            book.append(c,kind='exception',reason='가상 수정 근거',today='2026-10-03');self.assertEqual(book.read()['records'][0],first)

if __name__=='__main__':unittest.main()
