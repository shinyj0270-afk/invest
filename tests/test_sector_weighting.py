import copy
import unittest
from investment.market_insights import enrich_market


class SectorWeightingTests(unittest.TestCase):
    def make(self,flat=False):
        rows=[];facts={};history={}
        for i in range(6):
            code=str(900000+i);cap=(i+1)*1000 if i<5 else None
            ret=0 if flat else (i-2)*5
            prices=[dict(date=str(j),close=100,volume=1) for j in range(150)]
            prices[-1]['close']=100+ret
            rows.append(dict(code=code,name='Synthetic',market='KOSPI',industry='Synthetic sector',metrics=dict(market_cap_eok=cap),discovery_allowed=True))
            facts[code]=dict(technical=dict(close=prices[-1]['close'],as_of='149',sma={'50':100,'200':100}))
            history[code]=dict(prices=prices)
        d=dict(snapshot=dict(meta={'price_date':'149'},companies=rows),research=dict(rows=facts))
        return d,dict(history=dict(histories=history))

    def test_known_weighted_equal_median_and_signed_contributions(self):
        d,c=self.make();before=copy.deepcopy(c)
        s=enrich_market(d,c)['sectors'][0]['short_rs']['1m']
        self.assertEqual(s['count'],5);self.assertEqual(s['excluded'],1)
        self.assertAlmostEqual(s['equal_weight_return_pct'],0)
        self.assertAlmostEqual(s['median_return_pct'],0)
        self.assertAlmostEqual(s['return_pct'],(-10-10+0+20+50)/15)
        self.assertAlmostEqual(s['top3_contribution_pp'],70/15)
        self.assertAlmostEqual(s['top3_absolute_share_pct'],70/90*100)
        self.assertEqual(s['positive_count'],2);self.assertEqual(c,before)

    def test_zero_contributions_not_invented_concentration(self):
        d,c=self.make(flat=True);s=enrich_market(d,c)['sectors'][0]['short_rs']['3m']
        self.assertEqual(s['top3_contribution_pp'],0)
        self.assertIsNone(s['top3_absolute_share_pct'])


if __name__=='__main__':unittest.main()
