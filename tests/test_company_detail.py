import copy, unittest
from investment.fixture import make_fixture
from investment.company_detail import chart_history, build_details
from investment.financial_table import build_table


class CompanyDetailTests(unittest.TestCase):
    def setUp(self):
        self.s=make_fixture();self.r=self.s['companies'][0]
        for p in self.r['prices']:p.update(final=True,open=p['close'])

    def test_chart_preserves_source_and_volume(self):
        original=copy.deepcopy(self.s);chart=chart_history(self.r,self.s)
        self.assertEqual(len(chart['bars']),280);self.assertEqual(chart['bars'][-1]['volume'],100000)
        self.assertIsNotNone(chart['low_52w']);self.assertEqual(self.s,original)

    def test_missing_ohlc_keeps_close_without_fake_candles(self):
        self.r['prices'][0]['open']=None
        chart=chart_history(self.r,self.s)
        self.assertIsNone(chart['bars'][0]['high']);self.assertGreater(chart['bars'][0]['close'],0)

    def test_financial_cutoff_today_uses_last_complete_price_session(self):
        from datetime import date,timedelta
        final_day=self.s['meta']['price_date']
        self.s['meta']['price_date']=(date.fromisoformat(final_day)+timedelta(days=1)).isoformat()
        cache={'history':{'histories':{self.r['code']:dict(kind='item',symbol=self.r['code'],prices=self.r['prices'])},
            'benchmarks':{market:dict(kind='index',symbol=market,source={'url':'https://example.test/index'},
                prices=[dict(p,final=True,venue='KRX',adjustment_basis='index_level') for p in prices])
                for market,prices in [('KOSPI',self.s['benchmarks']['KOSPI']),('KOSDAQ',self.s['benchmarks']['KOSPI'])]}}}
        chart=chart_history(self.r,self.s,cache)
        self.assertEqual(chart['as_of'],final_day)
        self.assertIsNotNone(chart['high_52w'])
        del cache['history']['histories'][self.r['code']]['prices'][-8]
        self.assertIsNone(chart_history(self.r,self.s,cache)['high_52w'])

    def test_invalid_ohlc_falls_back_to_close(self):
        self.r['prices'][0]['low']=self.r['prices'][0]['high']*2
        self.assertIsNone(chart_history(self.r,self.s)['bars'][0]['open'])

    def test_future_price_is_excluded(self):
        p=dict(self.r['prices'][-1],date='2026-10-01');self.r['prices'].append(p)
        self.assertEqual(chart_history(self.r,self.s)['bars'][-1]['date'],'2026-09-23')

    def test_duplicate_or_provisional_price_invalidates(self):
        self.r['prices'][0]['final']=False
        self.assertEqual(chart_history(self.r,self.s)['bars'],[])

    def test_missing_session_does_not_claim_complete_52_week_range(self):
        del self.r['prices'][-8]
        chart=chart_history(self.r,self.s)
        self.assertTrue(chart['bars'])
        self.assertIsNone(chart['high_52w'])
        self.r['prices'][0]['final']=True;self.r['prices'].append(self.r['prices'][-1])
        self.assertEqual(chart_history(self.r,self.s)['bars'],[])

    def test_identity_mismatch_does_not_connect_other_history(self):
        p=dict(self.r['prices'][-1],close=99999999)
        cache={'history':{'histories':{self.r['code']:{'kind':'item','symbol':'other','prices':[p]}}}}
        self.assertNotEqual(chart_history(self.r,self.s,cache)['bars'][-1]['close'],99999999)

    def test_statements_use_krw_to_eok_and_availability(self):
        tables={r['code']:build_table(r,self.s) for r in self.s['companies']}
        result=build_details(self.s,tables)
        value=result[self.r['code']]['groups'][0]['columns'][0]['values']['revenue']
        self.assertEqual(value,self.r['annual'][0]['revenue']/1e8)
        self.assertEqual(result[self.r['code']]['dividends'][-1]['period_end'],'2025-12-31')

    def test_bad_supplement_identity_and_duplicates_stay_missing(self):
        table=build_table(self.r,self.s,dict(code='other',name=self.r['name'],market=self.r['market'],periods=[]))
        self.assertIn('식별',table['notes'][0])
        self.r['quarters'].append(self.r['quarters'][0]);tables={r['code']:build_table(r,self.s) for r in self.s['companies']}
        self.assertEqual(build_details(self.s,tables)[self.r['code']]['groups'],[])
