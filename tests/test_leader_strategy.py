import copy,unittest
from investment.leader_strategy import raw_features,standardize,band,build,load_config
from tests.test_industry_phase import bars

class LeaderTests(unittest.TestCase):
    def test_invalid_config_root_rejected(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from unittest.mock import patch
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'leader.json'
            for value in ('null','[]','123','{"version":true}'):
                path.write_text(value,encoding='utf-8')
                with self.assertRaises(ValueError):load_config(path)
                with patch('investment.leader_strategy.load_config',lambda:load_config(path)):
                    self.assertEqual(build(None,None)['status'],'invalid')

    def test_stored_turnover_and_missing_history(self):
        ps=bars([100]*300)
        for p in ps:p['turnover']=1000
        for p in ps[-21:]:p['turnover']=1500
        t=dict(close=100,as_of=ps[-1]['date'],price_health={'status':'ready'})
        v,reason=raw_features({'prices':ps},t,t['as_of'],load_config())
        self.assertFalse(reason);self.assertEqual(v['turnover_method'],'stored_turnover')
        self.assertEqual(v['turnover_change_pct'],50)
        self.assertTrue(raw_features({'prices':ps[-272:]},t,t['as_of'],load_config())[1])
        self.assertTrue(raw_features({'prices':ps},dict(t,suspended=True),t['as_of'],load_config())[1])

    def test_winsor_and_size_order_known_values(self):
        from statistics import mean,pstdev
        cfg=load_config();cfg['winsor_tail']=.25
        # raw/size gives [0, 2, 2, 2, 10], then 25/75% clipping gives constant 2.
        caps=[100,200,300,400,500];cfg['size_floor']=.5
        self.assertEqual(standardize([0,1.25,1.5,1.75,10],caps,cfg),[None]*5)
        cfg['winsor_tail']=.02
        clipped=[.08,1,2,3,92.24];avg=mean(clipped);sd=pstdev(clipped)
        self.assertEqual(standardize([0,1,2,3,100],[100]*5,cfg),[(v-avg)/sd for v in clipped])
        self.assertEqual(standardize([1,2,3,4],[100]*4,cfg),[None]*4)

    def test_vwap_offset_and_turnover_proxy(self):
        ps=bars([100]*279+[200]*21)
        for p in ps[-21:]:p['volume']=200
        t=dict(close=200,as_of=ps[-1]['date'],price_health={'status':'ready'})
        values,reason=raw_features({'kind':'item','prices':ps},t,ps[-1]['date'],load_config())
        self.assertFalse(reason);self.assertAlmostEqual(values['momentum_pct'],100)
        self.assertAlmostEqual(values['turnover_change_pct'],300)
        self.assertEqual(values['turnover_method'],'adjusted_close_volume_proxy')
        ps[-1]['volume']=0
        self.assertTrue(raw_features({'prices':ps},t,t['as_of'],load_config())[1])

    def test_z_boundaries_constant_and_winsor(self):
        self.assertEqual([band(v,1.5) for v in (-1.5,-1.499,1.499,1.5)],['하','중','중','상'])
        self.assertEqual(standardize([1]*5,[100]*5,load_config()),[None]*5)
        zs=standardize([0,1,2,3,100],[100]*5,load_config())
        self.assertAlmostEqual(sum(zs),0,places=10)

    def test_market_separation_and_invalid_value(self):
        ps=bars([100+i*.1 for i in range(300)])
        rows=[];facts={};histories={}
        for market in ('KOSPI','KOSDAQ'):
            for i in range(6):
                code=market+str(i);prices=copy.deepcopy(ps)
                for p in prices[-21:]:p['close']*=1+i*.1;p['volume']*=1+i*.2
                details={k:dict(period='2026-06-30',basis='CFS',price_date=ps[-1]['date'],currency='KRW',status='estimated') for k in ('per','pbr')}
                rows.append(dict(code=code,name=code,market=market,industry='A',discovery_allowed=True,
                    metrics={'market_cap_eok':2000,'per':-1 if i==0 else i*2,'pbr':i+1},metric_details=details))
                facts[code]={'technical':dict(close=prices[-1]['close'],as_of=ps[-1]['date'],price_health={'status':'ready'})}
                histories[code]={'kind':'item','prices':prices}
        d={'snapshot':{'meta':{'price_date':ps[-1]['date']},'companies':rows},'research':{'rows':facts}}
        cache={'history':{'histories':histories}}
        both=build(d,cache);single=copy.deepcopy(d);single['snapshot']['companies']=rows[:6]
        a=build(single,cache)
        self.assertEqual([r['momentum_z'] for r in both['rows'][:6]],[r['momentum_z'] for r in a['rows']])
        self.assertEqual(both['rows'][0]['value_band'],'미확인')
        self.assertFalse(both['rows'][0]['candidate'])
        self.assertEqual(sum(m['classified']+m['missing'] for m in both['markets']),12)

    def test_valuation_date_and_basis_cannot_be_mixed(self):
        cutoff='2026-10-16';rows=[]
        for i in range(6):
            rows.append(dict(code=str(i),name=str(i),market='KOSPI',industry='A',discovery_allowed=True,
                metrics=dict(market_cap_eok=2000,per=i+1,pbr=i+1),
                metric_details={k:dict(period='2026-06-30',basis='CFS',price_date=cutoff,status='estimated') for k in ('per','pbr')}))
        rows[0]['metric_details']['pbr']['price_date']='2026-10-15'
        d={'snapshot':{'meta':{'price_date':cutoff},'companies':rows},'research':{'rows':{}}}
        result=build(d,None)
        self.assertEqual(result['rows'][0]['value_band'],'미확인')
        self.assertTrue(all(r['value_band']!='미확인' for r in result['rows'][1:]))
        for r in rows:r['metric_details']['per']['basis']='OFS'
        self.assertTrue(all(r['value_band']=='미확인' for r in build(d,None)['rows']))

if __name__=='__main__':unittest.main()
