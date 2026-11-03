"""Regression tests for bug-class findings of the 2026-11-03 Codex hunt (reproduced before fixing)."""
import copy
import tempfile
import unittest
from datetime import datetime
from investment.holdings_bridge import holdings_catalog
from investment.holding_market import HoldingMarket
from investment.fixture import make_fixture
from investment.trend_following import build_trend_following
from investment.workspace_research import build_research
from tests.test_holding_market import cache
from tests.test_trend_following import trend_fixture


class IndexTrendArithmeticTests(unittest.TestCase):
    def test_equal_window_averages_do_not_pass_the_strict_slope_condition(self):
        s=trend_fixture();bars=s['benchmarks']['KOSPI'];n=len(bars)
        for i,p in enumerate(bars):                                     # period-21 pattern ending on a high close
            v=2600.01 if (n-1-i)%21==0 else 2500.01
            p.update(close=v,open=v,high=v,low=v)
        s['benchmarks']['KOSDAQ']=copy.deepcopy(bars)
        data=build_trend_following(s,build_research(s))
        for market in data['markets']:
            self.assertEqual(market['status'],'ready')
            # MA200 and the MA200 of 21 sessions earlier are mathematically equal, so the strict '>' must fail.
            self.assertNotEqual(market['regime'],'상승 정렬')


class HoldingQuoteFallbackTests(unittest.TestCase):
    def test_a_failed_refresh_keeps_the_last_successful_quote(self):
        snapshot=make_fixture();snapshot['meta']['data_mode']='user_input'
        state=dict(fail=False)
        def fetch(code,**kw):
            if state['fail']:raise OSError('offline')
            return dict(symbol=code,kind='item',prices=[dict(date='2026-09-30',close=120,final=True,venue='KRX',adjustment_basis='naver_chart_adjusted')])
        with tempfile.TemporaryDirectory() as tmp:
            service=HoldingMarket(tmp,lambda:snapshot,fetcher=fetch,now=lambda:datetime.fromisoformat('2026-10-01T09:00:00+09:00'))
            service.index={r['code']:r for r in holdings_catalog(snapshot,cache(),'2026-10-01')}
            first=service.lookup('005010',force=True)
            self.assertEqual((first['status'],first['row']['price_krw'],first['row']['price_date']),('updated',120,'2026-09-30'))
            state['fail']=True
            after=service.lookup('005010',force=True)
            self.assertEqual(after['status'],'cached')
            self.assertEqual((after['row']['price_krw'],after['row']['price_date']),(120,'2026-09-30'))   # not the older catalog 100 / 2026-09-29


if __name__=='__main__':unittest.main()
