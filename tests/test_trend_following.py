import copy,json,unittest
from investment.fixture import make_fixture
from investment.workspace_research import build_research
from investment.trend_following import build_trend_following,chart_series


def trend_fixture(count=28):
    snapshot=make_fixture();base=snapshot['companies'][-1];rows=[]
    for i in range(count):
        r=copy.deepcopy(base);r.update(code=f'91{i:04d}',name=f'가상 추세기업 {i+1}',industry=f'가상 산업 {i%3+1}')
        r['metrics']['market_cap_eok']=1000+i*100
        for j,p in enumerate(r['prices']):
            value=p['close']*(1+i*.02*j/279)
            p.update(close=value,open=value*.998,high=value*1.02,low=value*.98,final=True,
                     volume=100000+(j%13)*2000)
        rows.append(r)
    snapshot['companies']=rows;snapshot['meta']['universe_total']=count
    for p in snapshot['benchmarks']['KOSPI']:p.update(final=True,venue='KRX',adjustment_basis='index_level')
    snapshot['benchmarks']['KOSDAQ']=copy.deepcopy(snapshot['benchmarks']['KOSPI'])
    return snapshot


class TrendFollowingTests(unittest.TestCase):
    def test_default_thousand_and_complete_chart_metadata(self):
        s=trend_fixture();research=build_research(s);before=copy.deepcopy((s,research))
        data=build_trend_following(s,research)
        self.assertEqual(data['default_cap_eok'],1000)
        self.assertEqual(data['default_rs'],70)
        self.assertEqual(len(data['markets']),2)
        self.assertEqual(data['markets'][0]['status'],'ready')
        self.assertTrue(all(r['ready'] for r in data['rows']))
        self.assertEqual(len(data['rows'][0]['analysis']['checks']),8)
        self.assertLessEqual(len(data['previews']),21)
        self.assertEqual((s,research),before);json.dumps(data,allow_nan=False)

    def test_thousand_boundary_and_previews_bounded_to_twenty_one(self):
        s=trend_fixture(32);research=build_research(s)
        for r in research['rows'].values():r['technical']['price_strength']['score']=80
        s['companies'][0]['metrics']['market_cap_eok']=999.99
        s['companies'][1]['metrics']['market_cap_eok']=1000
        s['companies'][2]['metrics']['market_cap_eok']=None
        data=build_trend_following(s,research)
        self.assertEqual(len(data['previews']),21)
        self.assertNotIn(s['companies'][0]['code'],data['previews'])
        self.assertIn(s['companies'][1]['code'],data['previews'])
        self.assertNotIn(s['companies'][2]['code'],data['previews'])
        self.assertTrue(all(len(ps)==253 for ps in data['previews'].values()))

    def test_unknown_missing_provisional_or_no_trade_cannot_pass(self):
        for edit in ('gap','provisional','no_trade','wrong_basis','wrong_price'):
            s=trend_fixture(8);research=build_research(s);code=s['companies'][-1]['code'];ps=s['companies'][-1]['prices']
            if edit=='gap':del ps[-10]
            elif edit=='provisional':ps[-1]['final']=False
            elif edit=='no_trade':ps[-1]['no_trade']=True
            elif edit=='wrong_basis':ps[-1]['adjustment_basis']='unknown'
            else:ps[-1]['close']+=1
            row=next(r for r in build_trend_following(s,research)['rows'] if r['code']==code)
            self.assertFalse(row['ready'],edit)

    def test_market_missing_or_stale_does_not_show_positive_regime(self):
        s=trend_fixture(8);research=build_research(s);s['benchmarks']['KOSPI'][-1]['final']=False
        data=build_trend_following(s,research)
        self.assertEqual(data['markets'][0]['status'],'pending')
        self.assertEqual(data['markets'][0]['series'],[])
        self.assertTrue(all(not r['ready'] for r in data['rows']))

    def test_date_cutoff_and_known_moving_average(self):
        s=trend_fixture(8);research=build_research(s);before=build_trend_following(s,research)
        for r in s['companies']:r['prices'].append(dict(r['prices'][-1],date='2030-01-01',close=999999,final=False))
        self.assertEqual(build_trend_following(s,research),before)
        bars=[dict(date=str(i),close=i+1) for i in range(300)]
        series=chart_series(bars)
        self.assertEqual(series[-1]['ma50'],275.5)
        self.assertEqual(series[-1]['ma200'],200.5)
        self.assertEqual(len(series),253)

    def test_cached_identity_cannot_attach_another_company(self):
        s=trend_fixture(8);research=build_research(s);r=s['companies'][-1]
        cache={'history':{'histories':{r['code']:dict(symbol='wrong',kind='item',prices=r['prices'])}}}
        row=build_trend_following(s,research,cache)['rows'][-1]
        self.assertFalse(row['ready']);self.assertIn('식별',row['reason'])

if __name__=='__main__':unittest.main()
