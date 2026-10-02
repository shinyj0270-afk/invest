import unittest
from investment.trend_diagnostics import diagnose,update_rank


class TrendDiagnosticsTests(unittest.TestCase):
    def make(self,price=100,high=125,low=50,score=80,volume=2000):
        bars=[dict(close=20+i*.2,volume=1000) for i in range(252)]+[dict(close=price,volume=volume)]
        t=dict(sma={'50':90,'150':80,'200':70},high_52w_close=high,low_52w_close=low,price_strength={'score':score})
        return bars,t

    def test_high_limits_have_distinct_denominators(self):
        bars,t=self.make(price=100,high=125)
        a=diagnose(bars,t)
        self.assertTrue(a['mmt_high_pass'])
        self.assertEqual(a['status'],'pass')
        bars,t=self.make(price=100,high=100/.75)
        a=diagnose(bars,t)
        self.assertFalse(a['mmt_high_pass'])
        self.assertEqual(next(c['status'] for c in a['checks'] if c['id']=='near_high'),'pass')
        t['high_52w_close']=134
        self.assertEqual(diagnose(bars,t)['status'],'fail')

    def test_low_and_rank_boundaries_unknown_is_not_zero(self):
        bars,t=self.make(price=65,low=50,score=None)
        a=diagnose(bars,t)
        self.assertEqual(next(c['status'] for c in a['checks'] if c['id']=='above_low'),'pass')
        self.assertEqual(next(c['status'] for c in a['checks'] if c['id']=='rs'),'unknown')
        update_rank(a,70)
        self.assertEqual(next(c['status'] for c in a['checks'] if c['id']=='rs'),'pass')
        update_rank(a,69.99)
        self.assertEqual(next(c['status'] for c in a['checks'] if c['id']=='rs'),'fail')

    def test_pivot_excludes_today_and_volume_excludes_today(self):
        bars,t=self.make(volume=1500)
        a=diagnose(bars,t)
        self.assertEqual(a['pivot'],max(b['close'] for b in bars[-21:-1]))
        self.assertEqual(a['volume_multiple'],1.5)
        self.assertEqual(a['phase'],'거래량 동반 돌파')
        bars[-1]['volume']=None
        a=diagnose(bars,t)
        self.assertIsNone(a['volume_multiple'])
        self.assertIn('거래량 확인 대기',a['phase'])
        self.assertIsNone(a['contraction'])

    def test_failed_breakout_uses_previous_fixed_pivot(self):
        bars,t=self.make()
        bars[-2]['close']=110;bars[-1]['close']=60
        self.assertEqual(diagnose(bars,t)['phase'],'돌파 후 되밀림')

    def test_missing_history_and_suspension_do_not_pass(self):
        bars,t=self.make();t['low_52w_close']=None;t['high_52w_close']=None
        a=diagnose(bars,t)
        self.assertNotEqual(a['status'],'pass')
        self.assertEqual(a['mmt_status'],'unknown')
        bars,t=self.make();t['suspended']=True
        a=diagnose(bars,t)
        self.assertEqual(a['status'],'unknown')
        self.assertTrue(a['blocked'])
        self.assertEqual(a['mmt_status'],'unknown')

    def test_no_trade_with_favorable_prices_withholds_both_trend_verdicts(self):
        for no_trade,volume in ((False,0),(True,1000)):
            with self.subTest(no_trade=no_trade,volume=volume):
                bars,t=self.make(volume=volume)
                bars[-1]['no_trade']=no_trade
                a=diagnose(bars,t)
                self.assertTrue(a['mmt_high_pass'])
                self.assertTrue(a['blocked'])
                self.assertEqual(a['status'],'unknown')
                self.assertEqual(a['mmt_status'],'unknown')
                update_rank(a,99)
                self.assertEqual(a['mmt_status'],'unknown')


if __name__=='__main__':unittest.main()
