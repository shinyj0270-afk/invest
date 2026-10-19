import copy,unittest
from datetime import date,timedelta
from investment.industry_phase import classify,trajectory,build,load_config,episodes,validated_prices

def bars(values):
    day=date(2024,1,1);out=[]
    for v in values:
        while day.weekday()>4:day+=timedelta(days=1)
        out.append(dict(date=day.isoformat(),close=v,volume=100,final=True,venue='KRX',adjustment_basis='naver_chart_adjusted'))
        day+=timedelta(days=1)
    return out

class PhaseTests(unittest.TestCase):
    def test_invalid_config_root_rejected(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from unittest.mock import patch
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'phase.json'
            for value in ('null','[]','123','{"version":true}'):
                path.write_text(value,encoding='utf-8')
                with self.assertRaises(ValueError):load_config(path)
                with patch('investment.industry_phase.load_config',lambda:load_config(path)):
                    self.assertEqual(build(None,None)['status'],'invalid')

    def test_birth_requires_observed_death_and_consumes_arm(self):
        ps=bars([100]*270+[60]*70+[100,101])
        path=trajectory(ps,load_config())
        self.assertEqual([p['phase'] for p in path[-3:]],['사','생','사'])
        self.assertNotIn('생',[p['phase'] for p in trajectory(bars([100+i for i in range(400)]),load_config())])

    def test_episodes_exclude_censoring_and_zero_rise(self):
        states=['왕','쇠','생','왕','왕','쇠','왕']
        path=[dict(date=str(i),phase=s,close=v) for i,(s,v) in enumerate(zip(states,[100,90,100,120,110,100,110]))]
        self.assertEqual(episodes(path),[dict(start='2',peak='3',entry='5',rise_days=1,fall_days=2,entry_phase='쇠')])

    def test_invalid_or_stale_or_suspended_prices_fail_closed(self):
        ps=bars([100]*400);t=dict(close=100,as_of=ps[-1]['date'],price_health={'status':'ready'})
        self.assertTrue(validated_prices({'prices':ps},t,t['as_of']))
        for bad in (dict(t,suspended=True),dict(t,as_of='2020-01-01'),dict(t,price_health={'status':'missing'})):
            self.assertFalse(validated_prices({'prices':ps},bad,t['as_of']))
        ps[0]['final']=False
        self.assertFalse(validated_prices({'prices':ps},t,t['as_of']))

    def test_boundaries_and_overlap_are_explicit(self):
        cfg=load_config()
        for close,expected in ((90.01,'왕'),(90,'쇠'),(80,'쇠'),(79.99,'사')):
            self.assertEqual(classify(close,75,70,100,False,False,cfg),expected)
        self.assertEqual(classify(100,70,75,100,False,False,cfg),'사')
        self.assertEqual(classify(100,70,75,100,True,True,cfg),'생')
        self.assertEqual(classify(100,100,100,100,False,False,cfg),'미확인')

    def test_history_has_no_future_leak_and_short_is_unknown(self):
        ps=bars([100+i*.1 for i in range(400)])
        before=trajectory(ps,load_config())
        after=trajectory(ps[:-1]+[dict(ps[-1],close=1)],load_config())
        self.assertEqual(before[:-1],after[:-1])
        self.assertEqual(before[-1]['phase'],'왕')
        self.assertEqual(trajectory(ps[:100],load_config())[-1]['phase'],'미확인')

    def test_missing_price_never_joins_denominator(self):
        ps=bars([100+i*.1 for i in range(400)])
        rows=[dict(code=str(i),name=str(i),market='KOSPI',industry='A',discovery_allowed=True,metrics={'market_cap_eok':100}) for i in range(6)]
        facts={r['code']:{'technical':dict(close=ps[-1]['close'],as_of=ps[-1]['date'],sma={},price_health={'status':'ready'})} for r in rows}
        facts['5']['technical']['close']=None
        d={'snapshot':{'meta':{'price_date':ps[-1]['date']},'companies':rows},'research':{'rows':facts}}
        cache={'history':{'histories':{r['code']:{'kind':'item','prices':ps} for r in rows}}}
        result=build(d,cache)
        g=result['sectors'][0]
        self.assertEqual((g['eligible'],g['missing'],g['growth']['count'],g['growth']['pct']),(5,1,5,100))
        self.assertTrue(g['rankable']);self.assertEqual(g['growth']['cap_pct'],100)
        self.assertNotIn('series',result['rows']['0'])

if __name__=='__main__':unittest.main()
