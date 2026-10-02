import copy
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

from investment.fixture import make_fixture
from investment.market_refresh import collect_daily, collect_quotes, DailyMarketRefresh
from investment.market_history import completed_cutoff


class DailyRefreshTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)
        days=make_fixture()['sessions']
        self.last=days[-1]
        self.next=(datetime.fromisoformat(self.last).date()+timedelta(days=1)).isoformat()
        self.now=datetime.fromisoformat(self.next).replace(tzinfo=ZoneInfo('Asia/Seoul'))+timedelta(days=1)
        def record(symbol,kind):
            return dict(symbol=symbol,kind=kind,price_date=self.last,
                prices=[dict(date=d,close=100+i,final=True,venue='KRX',adjustment_basis='index_level' if kind=='index' else 'naver_chart_adjusted') for i,d in enumerate(days)],
                source=dict(url='https://source.example/'+symbol))
        self.old=dict(schema_version='market-history-bundle-0.1',start=days[0],end=self.last,
            benchmarks={s:record(s,'index') for s in ('KOSPI','KOSDAQ')},
            histories={s:record(s,'item') for s in ('005930','000660')},errors=[])
        (self.folder/'universe.json').write_text(json.dumps(dict(schema_version='naver-universe-0.1',pagination_complete=True,
            companies=[dict(code=s,eligibility='candidate') for s in self.old['histories']])),encoding='utf-8')
        self.path=self.folder/'histories.json';self.path.write_text(json.dumps(self.old),encoding='utf-8')
        self.before=self.path.read_bytes();self.calls=[]
    def fetch(self,symbol,**kw):
        self.calls.append((symbol,kw))
        r=copy.deepcopy((self.old['benchmarks'] if kw['kind']=='index' else self.old['histories'])[symbol])
        r['prices']=[p for p in r['prices'] if p['date']>=kw['start']]
        r['prices'].append(dict(r['prices'][-1],date=self.next,close=999))
        r['price_date']=self.next
        return r
    def test_incremental_update_preserves_history_and_evidence(self):
        progress=[];r=collect_daily(self.folder,progress.append,fetch=self.fetch,now=self.now,pace=0)
        saved=json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(r['target_date'],self.next)
        self.assertEqual(progress[-1]['completed'],2)
        self.assertEqual(len(saved['histories']['005930']['prices']),len(self.old['histories']['005930']['prices'])+1)
        self.assertEqual(len(saved['histories']['005930']['source_segments']),2)
        self.assertTrue(all(c[1]['start']>self.old['start'] and c[1]['force'] for c in self.calls))
    def test_all_failed_companies_keep_bundle_byte_identical(self):
        def fetch(s,**kw):
            if kw['kind']=='item':raise OSError('private-path-must-not-leak')
            return self.fetch(s,**kw)
        with self.assertRaises(ValueError):collect_daily(self.folder,lambda _:None,fetch=fetch,now=self.now,pace=0)
        self.assertEqual(self.path.read_bytes(),self.before)
    def test_partial_failure_keeps_failed_company_old_observations(self):
        def fetch(s,**kw):
            if s=='005930':raise OSError('private-path-must-not-leak')
            return self.fetch(s,**kw)
        result=collect_daily(self.folder,lambda _:None,fetch=fetch,now=self.now,pace=0)
        saved=json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(result['failed'],1)
        self.assertEqual(result['updated_companies'],1)
        self.assertEqual(saved['histories']['005930'],self.old['histories']['005930'])
        self.assertEqual(saved['histories']['000660']['price_date'],self.next)
    def test_overlap_price_correction_refetches_entire_series(self):
        def fetch(s,**kw):
            r=self.fetch(s,**kw)
            if s=='005930':
                for p in r['prices']:p['close']/=2
            return r
        collect_daily(self.folder,lambda _:None,fetch=fetch,now=self.now,pace=0)
        saved=json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(saved['histories']['005930']['prices'][0]['close'],50)
        self.assertTrue(any(s=='005930' and kw['start']==self.old['start'] for s,kw in self.calls))
    def test_benchmark_mismatch_keeps_bundle(self):
        def fetch(s,**kw):
            r=self.fetch(s,**kw)
            if s=='KOSDAQ':r['prices'].pop(0)
            return r
        with self.assertRaises(ValueError):collect_daily(self.folder,lambda _:None,fetch=fetch,now=self.now,pace=0)
        self.assertEqual(self.path.read_bytes(),self.before)
    def test_duplicate_start_only_runs_one_job(self):
        entered=threading.Event();release=threading.Event();done=threading.Event();calls=[]
        def collect(folder,progress):
            calls.append(folder);entered.set();release.wait(3);return dict(status='complete')
        service=DailyMarketRefresh('.',collector=collect)
        cfg=dict(data_dir=self.folder,profile='work')
        with patch('investment.market_refresh.load_local',return_value=cfg):
            service.start();self.assertTrue(entered.wait(2));service.start();self.assertEqual(len(calls),1)
            release.set()
            for _ in range(100):
                if service.poll()['status']!='running':break
                done.wait(.01)
            self.assertEqual(service.poll()['status'],'complete')
        self.assertFalse((self.folder/'work/market-expansion/daily-refresh.lock').exists())
    def test_auto_refresh_reuses_today_success_after_restart(self):
        folder=self.folder/'work/market-expansion';folder.mkdir(parents=True)
        day=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
        target=completed_cutoff(datetime.now(ZoneInfo('Asia/Seoul')),True).isoformat()
        (folder/'daily-refresh-status.json').write_text(json.dumps(dict(status='complete',checked_on=day,target_date=target,requested_end=target,failed=0)),encoding='utf-8')
        service=DailyMarketRefresh('.')
        with patch('investment.market_refresh.load_local',return_value=dict(data_dir=self.folder,profile='work')):
            self.assertEqual(service.ensure_due()['status'],'complete')
        self.assertEqual(service.last_attempt,0)
    def test_latest_quotes_do_not_change_daily_or_financials(self):
        def fetch(**kwargs):
            return dict(pagination_complete=True,errors=[],retrieved_at='2026-10-02T10:00:00+09:00',companies=[
                dict(code=c,name='company',market='KOSPI',metrics=dict(price=123,change_pct=1),retrieved_at='2026-10-02T09:59:59+09:00',source='Npay') for c in self.old['histories']])
        listing=json.loads((self.folder/'universe.json').read_text(encoding='utf-8'))
        for r in listing['companies']:r.update(name='company',market='KOSPI')
        (self.folder/'universe.json').write_text(json.dumps(listing),encoding='utf-8')
        before=(self.folder/'universe.json').read_bytes()
        result=collect_quotes(self.folder,lambda _:None,fetch=fetch)
        self.assertEqual(result['updated_companies'],2)
        saved=json.loads((self.folder/'latest-quotes.json').read_text(encoding='utf-8'))
        self.assertFalse(saved['quotes']['005930']['final'])
        self.assertIsNone(saved['quotes']['005930']['price_time'])
        self.assertEqual(self.path.read_bytes(),self.before)
        self.assertEqual((self.folder/'universe.json').read_bytes(),before)
    def test_incomplete_latest_listing_preserves_previous_quotes(self):
        p=self.folder/'latest-quotes.json';p.write_text('previous')
        with self.assertRaises(ValueError):
            collect_quotes(self.folder,lambda _:None,fetch=lambda **_:dict(pagination_complete=False))
        self.assertEqual(p.read_text(),'previous')
