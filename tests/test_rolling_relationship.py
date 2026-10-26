import copy
import math
import unittest
from statistics import covariance, variance, correlation
from investment.portfolio_risk import rolling_relationship, time_series, portfolio_risk
from tests.test_portfolio_risk import risk_fixture


class RollingTests(unittest.TestCase):
    def test_full_window_and_independent_statistics(self):
        y=[((i%7)-3)/100 for i in range(252)]
        x=[2*v+.001 for v in y]
        r=rolling_relationship(list(range(253)),x,y)
        for n in (63,126):
            w=r['windows'][str(n)];s=w['series']
            self.assertIsNone(s[n-2]['beta']);self.assertAlmostEqual(s[n-1]['beta'],2)
            self.assertAlmostEqual(w['latest']['beta'],covariance(x[-n:],y[-n:])/variance(y[-n:]))
            self.assertAlmostEqual(w['latest']['correlation'],correlation(x[-n:],y[-n:]))
            self.assertAlmostEqual(w['beta_change'],0)

    def test_opposite_constant_and_short_samples(self):
        y=[(-1)**i*.01 for i in range(126)]
        r=rolling_relationship(list(range(127)),[-v for v in y],y)['windows']['63']['latest']
        self.assertAlmostEqual(r['beta'],-1);self.assertAlmostEqual(r['correlation'],-1)
        r=rolling_relationship(list(range(127)),[0]*126,y)['windows']['63']['latest']
        self.assertEqual(r['beta'],0);self.assertIsNone(r['correlation'])
        r=rolling_relationship(list(range(127)),y,[0]*126)['windows']['63']['latest']
        self.assertIsNone(r['beta']);self.assertIsNone(r['correlation'])
        r=rolling_relationship(list(range(63)),y[:62],y[:62])
        self.assertEqual(r['windows']['63']['status'],'pending')

    def test_calendar_contract_and_pairs_preserved(self):
        targets,cache,cutoff=risk_fixture();before=copy.deepcopy(cache)
        r=portfolio_risk(targets,20,cache,cutoff)
        self.assertEqual(len(r['rolling_pairs']),1)
        self.assertAlmostEqual(r['rolling_pairs'][0]['rolling']['windows']['126']['latest']['correlation'],1)
        prices=cache['history']['histories']['900000']['prices']
        bm=cache['history']['benchmarks']['KOSPI']['prices']
        self.assertIn('rolling',time_series(prices,bm,cutoff))
        self.assertEqual(cache,before)
        del prices[-12]
        r=time_series(prices,bm,cutoff);self.assertEqual(r['status'],'pending');self.assertNotIn('rolling',r)


if __name__=='__main__':unittest.main()
