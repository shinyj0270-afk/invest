import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from investment.core import *
from investment.store import Store
from investment.fixture import make_fixture
from investment import research,trend
from investment.adapters import Reader,AdapterError,SetupPending,normalize_dart
from investment.report import onepager
from investment.metrics import additional

class CoreTests(unittest.TestCase):
    def test_credentials_not_persisted(self):
        s=make_fixture(); s['meta']['access_token']='not-a-real-token'
        with self.assertRaises(ValueError): validate_snapshot(s)
    def test_extended_metrics_and_missing_capex(self):
        s=make_fixture(); row=s['companies'][0]
        values,reasons=additional(row,s)
        self.assertAlmostEqual(values['revenue_cagr_3y_pct'],10)
        self.assertEqual(values['fcf_proxy_eok'],70)
        row['annual'][-1]['capex']=None
        self.assertIsNone(additional(row,s)[0]['fcf_proxy_eok'])
    def test_flow_units_and_missing_session(self):
        s=make_fixture(); row=s['companies'][0]
        row['flows']=[dict(date=b['date'],foreign_net_won=1e8,institution_net_won=-1e8,venue='KRX',final=True) for b in row['prices']]
        for b in row['prices']: b['final']=True
        values,_=additional(row,s); self.assertEqual(values['foreign_net_5d_eok'],5); self.assertEqual(values['institution_net_60d_eok'],-60)
        row['flows'].pop()
        self.assertIsNone(additional(row,s)[0]['foreign_net_5d_eok'])
    def test_three_state_and_js_parity(self):
        for value in (None,0,10,20):
            r={'metrics':{'roe_pct':value}}; rules=[{'metric':'roe_pct','op':'gte','value':10}]
            script="const e=require('./src/engine.js');console.log(e.evaluate("+json.dumps(r)+','+json.dumps(rules)+",'AND'))"
            actual=subprocess.check_output(['node','-e',script],text=True).strip()
            self.assertEqual(evaluate(r,rules)[0],actual)
        self.assertEqual(combine(['unknown','pass'],'OR'),'pass')
        self.assertEqual(combine(['unknown','fail']),'fail')
    def test_csv_injection(self): self.assertIn("'=SUM",safe_csv([{'text':'=SUM(1)'}]))
    def test_snapshot_invalid_code_date_duplicate(self):
        for change in ('code','date','duplicate'):
            s=make_fixture()
            if change=='code': s['companies'][0]['code']='12'
            if change=='date': s['meta']['price_date']='2026-02-30'
            if change=='duplicate': s['companies'].append(s['companies'][0])
            with self.assertRaises(ValueError): validate_snapshot(s)
    def test_peers_unfiltered(self):
        s=make_fixture(); self.assertEqual(len(peers(s,s['companies'][0])),8)
        self.assertIsNone(percentile(1,[1,2,3,4]))
        self.assertEqual(percentile(1,[1]*5),.5)
    def test_quarter_cumulative_and_balance(self):
        rows=[dict(period_end=d,available_at=d,basis='CFS',x=x) for d,x in [('2025-03-31',10),('2025-06-30',30),('2025-09-30',60),('2025-12-31',100)]]
        self.assertEqual([r['x'] for r in quarterly(rows,'x','2026-01-01',True)],[10,20,30,40])
        self.assertEqual([r['x'] for r in quarterly(rows,'x','2026-01-01',True,True)],[10,30,60,100])
        self.assertEqual(ttm(quarterly(rows,'x','2026-01-01',True),'x'),100)
    def test_vintage_future_revision(self):
        rows=[dict(period_end='2025-03-31',available_at='2025-05-01',x=10),dict(period_end='2025-03-31',available_at='2026-05-01',x=99)]
        self.assertEqual(select_vintage(rows,'2025-06-01')[0]['x'],10)
    def test_store_staging_and_mode_separation(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root,'work','fixture'); s=make_fixture(); store.save_snapshot(s)
            changed=copy.deepcopy(s); changed['companies'][0]['name']='new'; store.save_snapshot(changed,False)
            self.assertEqual(store.latest()['companies'][0]['name'],s['companies'][0]['name'])
            self.assertIsNone(Store(root,'home','fixture').latest())
            with self.assertRaises(ValueError): Store(root,'work','user_input').save_snapshot(s)
    def test_event_dedup(self):
        with tempfile.TemporaryDirectory() as root:
            s=Store(root,'work','fixture'); ev=dict(code='900000',path='turnaround',quarter='2026-03-31',model='v1')
            self.assertEqual(s.event(ev),s.event(ev))
            with s.connect() as db: self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0],1)
    def test_batch_idempotency_and_lock(self):
        import batch
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); Store(root/'data','work','fixture').save_snapshot(make_fixture())
            (root/'config').mkdir(); (root/'config/local.json').write_text('{"profile":"work"}',encoding='utf-8')
            with patch.object(batch,'ROOT',root):
                first=batch.run('work','fixture','weekly'); second=batch.run('work','fixture','weekly')
                self.assertEqual(first['run_id'],second['run_id']); self.assertEqual(second['change_reason'],'변경 없음')
                lock=root/'data/work/fixture/batch.lock'; lock.write_text('test')
                with self.assertRaises(ValueError): batch.run('work','fixture','weekly')
                self.assertTrue(lock.exists())
    def test_valuation_excludes_target(self):
        s=make_fixture(); row=s['companies'][0]
        self.assertEqual(valuation(s,row)['peer_count'],7)
        row['metrics']['eps_ttm']=-1; self.assertIsNone(valuation(s,row)['scenarios'])

class ResearchTests(unittest.TestCase):
    def test_thirteen_quarters_required(self):
        rows=make_fixture()['companies'][0]['quarters'][-12:]
        self.assertIsNone(research.financial_signals(rows,'2026-09-23')['cross_up'])
    def test_weighted_margin(self):
        rows=make_fixture()['companies'][0]['quarters']; out=research.financial_signals(rows,'2026-09-23')
        self.assertAlmostEqual(out['opm3'],100*sum(r['op'] for r in rows[-12:])/sum(r['revenue'] for r in rows[-12:]))
    def test_negative_cross_not_profit_turn(self):
        rows=make_fixture()['companies'][0]['quarters'][-13:]
        for r in rows: r.update(revenue=100,op=-10)
        rows[-1]['op']=-1
        out=research.financial_signals(rows,'2026-09-23')
        self.assertTrue(out['cross_up']); self.assertFalse(out['profit_turn'])
    def test_quarter_gap(self):
        rows=make_fixture()['companies'][0]['quarters']; del rows[-5]
        self.assertIsNone(research.financial_signals(rows,'2026-09-23')['cross_up'])
    def test_future_evidence_blocked(self):
        r=make_fixture()['companies'][0]
        for e in r['evidence']: e['first_seen_at']='2027-01-01'
        self.assertEqual(research.evidence_status(r,'domestic','2026-09-23'),'pending')
    def test_missing_quality_does_not_remove_paths(self):
        s=make_fixture(); s['companies'][0]['annual']=[]
        r=research.analyze(s)[0]; self.assertIsNone(r['quality_score']); self.assertEqual(r['paths']['domestic']['signal_status'],'pass')
    def test_quality_ties_and_alias(self):
        s=make_fixture(); out=research.analyze(s)
        self.assertTrue(all(r['S_long']==r['quality_score'] for r in out))
        self.assertTrue(all(0<=r['quality_score']<=100 for r in out))
    def test_returns_zero_dividend_and_gap(self):
        rows=make_fixture()['companies'][0]['annual']; rows[-4]['dps']=0
        out=research.annual_signals(rows,'2026-09-23')
        self.assertTrue(out['dividend_start']); self.assertIsNone(out['returns_signal'])
    def test_balanced_unique_limit_and_empty(self):
        out=research.analyze(make_fixture()); selected=research.balanced_list(out)
        self.assertEqual(len({r['code'] for r in selected}),len(selected)); self.assertLessEqual(len(selected),10)
        for p in research.PATHS: self.assertLessEqual(sum(r['selected_path']==p for r in selected),2)
        self.assertEqual(research.balanced_list([]),[])
        self.assertEqual(selected,research.balanced_list(list(reversed(out))))
    def test_report_escapes_text(self):
        s=make_fixture(); s['companies'][0]['name']='<script>alert(1)</script>'
        html=onepager(s,s['companies'][0],research.analyze(s)[0])
        self.assertNotIn('<script>',html); self.assertIn('가상 테스트',html)

class TrendTests(unittest.TestCase):
    def test_fixture_and_short_history(self):
        s=make_fixture(); r=trend.analyze(s); self.assertTrue(any(v['status']=='pass' for v in r))
        s['companies'][0]['prices']=s['companies'][0]['prices'][-60:]
        self.assertEqual(next(v for v in trend.analyze(s) if v['code']=='900000')['status'],'unknown')
    def test_today_excluded_from_breakout(self):
        s=make_fixture(); row=s['companies'][0]; b=row['prices'][-1]
        b.update(close=max(v['high'] for v in row['prices'][-21:-1])*1.02,high=1e9,volume=200000)
        result=trend.calculate(row,s['benchmarks']['KOSPI'],s['sessions'],s['meta']['price_date'])
        self.assertTrue(result['breakout'])
    def test_mixed_adjustment_and_missing_day(self):
        s=make_fixture(); row=s['companies'][0]; row['prices'][-1]['adjustment_basis']='raw'
        self.assertEqual(trend.calculate(row,s['benchmarks']['KOSPI'],s['sessions'],s['meta']['price_date'])['status'],'unknown')
    def test_future_prices_no_past_change(self):
        s=make_fixture(); before=trend.analyze(s); s['companies'][0]['prices'].append(dict(s['companies'][0]['prices'][-1],date='2027-01-01',close=1e9))
        self.assertEqual(before,trend.analyze(s))

class FakeResponse:
    def __init__(self,code,body,headers=None): self.status_code=code; self.body=body; self.headers=headers or {}
    def json(self): return self.body
class FakeSession:
    def __init__(self,responses): self.responses=list(responses); self.calls=0
    def request(self,*args,**kwargs): self.calls+=1; return self.responses.pop(0)

class AdapterTests(unittest.TestCase):
    def test_orders_blocked_before_network(self):
        with self.assertRaisesRegex(AdapterError,'allowlist'): Reader('work',{}).kiwoom('kt10000',{})
    def test_unknown_profile_blocked(self):
        with self.assertRaises(SetupPending): Reader('unknown',{'dart':True}).dart('financial',{})
    @patch.dict(os.environ,{'OPENDART_API_KEY':'SECRET_NOT_TO_LOG'})
    def test_auth_no_retry_and_sanitized(self):
        session=FakeSession([FakeResponse(401,{})]); r=Reader('work',{'dart':True},session,lambda _:None)
        with self.assertRaisesRegex(AdapterError,'^authentication_failed$'): r.dart('financial',{})
        self.assertEqual(session.calls,1)
    @patch.dict(os.environ,{'OPENDART_API_KEY':'test'})
    def test_rate_limit_retry(self):
        session=FakeSession([FakeResponse(429,{}),FakeResponse(200,{'status':'000','list':[{'x':1}]})])
        self.assertEqual(Reader('work',{'dart':True},session,lambda _:None).dart('financial',{}),[{'x':1}])
    @patch.dict(os.environ,{'KIWOOM_ACCESS_TOKEN':'test'})
    def test_broken_pagination(self):
        session=FakeSession([FakeResponse(200,{'return_code':0},{'cont-yn':'Y'})])
        with self.assertRaisesRegex(AdapterError,'pagination'): Reader('work',{'kiwoom':True,'kiwoom_spec_verified':True},session,lambda _:None).kiwoom('ka10081',{})
    def test_dart_account_not_guessed(self):
        r=normalize_dart([dict(account_id='unknown',currency='KRW',thstrm_amount='100')],'2026-06-30','2026-08-15')
        self.assertEqual(r['unmapped'],['unknown']); self.assertNotIn('op',r)

if __name__=='__main__': unittest.main()
