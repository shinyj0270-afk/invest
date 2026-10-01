"""Synthetic company lookup; no user holdings or live provider calls."""
import copy,json,tempfile,unittest,threading
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from http.server import HTTPServer
from investment.fixture import make_fixture
from investment.holdings_bridge import holdings_catalog
from investment.holding_market import HoldingMarket
from investment.live_dashboard import handler_for


def cache():
    rows=[dict(code=c,name=n,market='KOSPI',industry='가상 산업',security_type='ordinary_candidate',
        analysis_profile='nonfinancial_candidate',eligibility='candidate',metrics={},source='가상 공개 목록')
        for c,n in [('005010','가상 휴스틸'),('010950','가상 S-Oil')]]
    bar=dict(date='2026-09-29',close=100,final=True,venue='KRX',adjustment_basis='naver_chart_adjusted')
    return dict(universe=dict(schema_version='naver-universe-0.1',companies=rows),
        history=dict(histories={r['code']:dict(symbol=r['code'],kind='item',prices=[copy.deepcopy(bar)]) for r in rows}))


class HoldingMarketTests(unittest.TestCase):
    def setUp(self):
        self.snapshot=make_fixture();self.snapshot['meta']['data_mode']='user_input'
    def test_catalog_kept_separate_with_candidate_classification(self):
        before=copy.deepcopy(self.snapshot);rows=holdings_catalog(self.snapshot,cache(),'2026-10-01')
        r=next(r for r in rows if r['code']=='005010')
        self.assertEqual(r['name'],'가상 휴스틸');self.assertEqual(r['security_type'],'ordinary_candidate')
        self.assertEqual(r['price_krw'],100);self.assertEqual(r['review']['thesis'],'unknown')
        self.assertEqual(r['evidence'],[]);self.assertEqual(self.snapshot,before)
    def test_duplicate_future_and_unconfirmed_prices_not_connected(self):
        for patcher in ['duplicate','future','provisional','mismatch']:
            c=cache();h=c['history']['histories']['005010'];b=h['prices'][0]
            if patcher=='duplicate':h['prices'].append(copy.deepcopy(b))
            if patcher=='future':b['date']='2026-10-01'
            if patcher=='provisional':b['final']=False
            if patcher=='mismatch':h['symbol']='010950'
            r=next(r for r in holdings_catalog(self.snapshot,c,'2026-10-01') if r['code']=='005010')
            self.assertIsNone(r['price_krw'],patcher)
    def test_existing_infomax_identity_and_price_win(self):
        c=cache();r=c['universe']['companies'][0];r['code']=self.snapshot['companies'][0]['code'];r['name']='wrong'
        actual=holdings_catalog(self.snapshot,c,'2026-10-01')
        self.assertEqual(actual[0]['name'],self.snapshot['companies'][0]['name'])
    def test_bad_and_excluded_codes_not_exposed(self):
        c=cache();c['universe']['companies'] += [dict(c['universe']['companies'][0],code='0123N0'),dict(c['universe']['companies'][0],code='000009',eligibility='excluded')]
        codes=[r['code'] for r in holdings_catalog(self.snapshot,c)]
        self.assertNotIn('0123N0',codes);self.assertNotIn('000009',codes)
    def service(self,tmp,fetcher):
        service=HoldingMarket(tmp,lambda:self.snapshot,fetcher=fetcher,now=lambda:datetime.fromisoformat('2026-10-01T09:00:00+09:00'))
        service.index={r['code']:r for r in holdings_catalog(self.snapshot,cache(),'2026-10-01')}
        return service
    def test_new_quote_and_ttl_does_not_change_catalog_or_input(self):
        calls=[]
        def fetch(code,**kw):
            calls.append(kw);return dict(symbol=code,kind='item',prices=[dict(date='2026-09-30',close=120,final=True,venue='KRX',adjustment_basis='naver_chart_adjusted')])
        with tempfile.TemporaryDirectory() as tmp:
            s=self.service(tmp,fetch);a=s.lookup('005010');self.assertEqual(a['status'],'updated');self.assertEqual(a['row']['price_krw'],120)
            a['row']['name']='mutated';self.assertEqual(s.lookup('005010')['row']['name'],'가상 휴스틸');self.assertEqual(len(calls),1)
            self.assertTrue(calls[0]['cache_dir'].as_posix().endswith('.local/holding-market'));self.assertEqual(s.index['005010']['price_krw'],100)
            s.lookup('005010',force=True);self.assertEqual(len(calls),2);self.assertTrue(calls[-1]['force'])
    def test_failure_keeps_dated_cache_and_unknown_code_never_fetches(self):
        def fetch(*args,**kwargs):raise OSError('synthetic provider failure')
        with tempfile.TemporaryDirectory() as tmp:
            s=self.service(tmp,fetch);self.assertEqual(s.lookup('005010')['status'],'cached');self.assertEqual(s.lookup('005010')['row']['price_krw'],100)
            self.assertIsNone(s.lookup('999999')['row'])
            with self.assertRaises(ValueError):s.lookup('../key')
    def test_invalid_provider_quote_never_replaces_cache(self):
        for value in [0,float('inf'),-1]:
            with tempfile.TemporaryDirectory() as tmp:
                s=self.service(tmp,lambda code,**kw:dict(symbol=code,kind='item',prices=[dict(date='2026-09-30',close=value,final=True,venue='KRX',adjustment_basis='naver_chart_adjusted')]))
                self.assertEqual(s.lookup('005010')['row']['price_krw'],100)
    def test_http_auth_and_exact_code(self):
        class Quotes:
            def lookup(self,code,*,force=False):
                if code!='005010':raise ValueError()
                return dict(status='updated',code=code,row=None)
        server=HTTPServer(('127.0.0.1',0),handler_for(Path('.'),quotes=Quotes(),token='synthetic'))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url=f'http://127.0.0.1:{server.server_port}/holding-market?code=005010'
        try:
            for headers in [{},{'X-Dashboard-Token':'synthetic','Origin':'https://elsewhere.invalid'}]:
                with self.assertRaises(HTTPError) as e:urlopen(Request(url,headers=headers))
                self.assertEqual(e.exception.code,403)
            with urlopen(Request(url,headers={'X-Dashboard-Token':'synthetic'})) as r:self.assertEqual(json.load(r)['code'],'005010')
            with self.assertRaises(HTTPError) as e:urlopen(Request(url+'&code=010950',headers={'X-Dashboard-Token':'synthetic'}))
            self.assertEqual(e.exception.code,400)
        finally:server.shutdown();server.server_close();thread.join(3)

if __name__=='__main__':unittest.main()
