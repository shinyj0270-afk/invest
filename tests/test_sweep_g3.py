"""Offline regression boundaries for group 3; verified with mutcheck.py."""
import copy,json,subprocess,tempfile,unittest
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
from unittest.mock import patch
from investment import market_discovery as md,store as storage,industry_phase as phase
from investment import infomax_provider,research_followup,telegram_export,visuals,workspace_research
from investment.fixture import make_fixture
from investment.industry_phase import episodes
from tests.test_market_discovery import bars as discovery_bars
from tools import pc_check

def technical_case(closes,benchmark_closes=None):
    days=[(date(2024,1,1)+timedelta(days=i)).isoformat() for i in range(len(closes))]
    ps=discovery_bars(days);bs=discovery_bars(days,index=True)
    for row,v in zip(ps,closes):row.update(close=v,open=v,high=v,low=v)
    for row,v in zip(bs,benchmark_closes if benchmark_closes is not None else [100]*len(closes)):row.update(close=v,open=v,high=v,low=v)
    return md.technical(dict(kind='item',prices=ps),dict(kind='index',prices=bs),dict(sessions=days,valid_through=days[-1]))

def five_discovery(zero_quote=False):
    days=[(date(2025,1,1)+timedelta(days=i)).isoformat() for i in range(253)]
    rows=[];histories={}
    for i in range(5):
        code=str(900000+i);rows.append(dict(code=code,name=code,market='KOSPI',industry='synthetic',security_type='ordinary_candidate',
            analysis_profile='nonfinancial_candidate',eligibility='candidate',source='synthetic',observed_on=days[-1],metrics={'market_cap_eok':2000},derived_metrics={},trading_status={}))
        histories[code]=dict(symbol=code,kind='item',prices=discovery_bars(days,start=100+i*100))
    benchmarks={m:dict(symbol=m,kind='index',prices=discovery_bars(days,index=True,start=1000),source={'url':'https://example.test/'+m}) for m in ('KOSPI','KOSDAQ')}
    cache=dict(universe=dict(schema_version='naver-universe-0.1',companies=rows,pagination_complete=True,errors=[],retrieved_on=days[-1]),
               history=dict(benchmarks=benchmarks,histories=histories,errors=[]))
    if zero_quote:cache['quotes']={'quotes':{'900000':dict(code='900000',name='900000',market='KOSPI',price=0)}}
    return md.build_discovery(dict(meta=dict(data_mode='user_input',price_date=days[-1],as_of=days[-1]),companies=[]),dict(rows={},rs_label='synthetic'),cache,include_series=False)

def short_phase_path(closes):
    c=phase.load_config();c.update(ma_fast=2,ma_slow=3,high_weeks=1,breakout_days=2)
    ps=[dict(date=(date(2026,1,1)+timedelta(days=i)).isoformat(),close=v,volume=100) for i,v in enumerate(closes)]
    return phase.trajectory(ps,c)

class SweepG3Tests(unittest.TestCase):
    def setUp(self):
        temp_root=patch('tempfile.tempdir',str(Path(__file__).resolve().parents[1]));temp_root.start();self.addCleanup(temp_root.stop)
        # All store timestamps are synthetic, including rejected-input paths.
        clock=patch('investment.store.datetime');self.addCleanup(clock.stop)
        clock.start().now.return_value=datetime(2026,1,1,tzinfo=timezone.utc)

    def test_M023_first_complete_ma20(self):
        for size,expected in [(19,None),(20,100),(21,100)]:
            self.assertEqual(technical_case([100]*size)['series'][-1]['ma20'],expected)

    def test_M024_exact_52_week_coverage(self):
        for size,expected in [(364,None),(365,100),(366,100)]:
            self.assertEqual(technical_case([100]*size)['high_52w_close'],expected)

    def test_M025_exclusive_52_week_lower_edge(self):self.assertEqual(technical_case([1000]+[100]*364)['high_52w_close'],100)

    def test_M026_close_equals_sma50(self):
        for close,expected in [(99,'fail'),(100,'fail'),(101,'pass')]:
            self.assertEqual(technical_case([50]*200+[80]*150+[100]*49+[close])['price_trend_status'],expected)

    def test_M027_flat_sma200_slope(self):self.assertEqual(technical_case([100]*180+[200]*20+[100]*150+[180]*30+[200]*20)['price_trend_status'],'fail')

    def test_M028_zero_relative_return(self):
        c=list(range(100,500));v=technical_case(c,c)
        self.assertEqual(v['rs126_pct'],0);self.assertEqual(v['price_trend_status'],'fail')

    def test_M029_actual_rank_at_five(self):
        v=five_discovery()
        self.assertTrue(all(r['technical']['price_strength']['score'] is not None for r in v['research']['rows'].values()))

    def test_M030_zero_latest_quote(self):self.assertNotIn('latest_quote',five_discovery(True)['snapshot']['companies'][0])

    def test_M061_profile_guard(self):
        for profile,mode in [('invalid','fixture'),('work','invalid')]:
            with tempfile.TemporaryDirectory() as t,self.assertRaises(ValueError):storage.Store(t,profile,mode)

    def test_M062_validate_store_input(self):
        s=make_fixture();s['companies'][0]['code']='invalid'
        with tempfile.TemporaryDirectory() as t:
            st=storage.Store(t,'work','fixture')
            with self.assertRaises(ValueError):st.save_snapshot(s)

    def test_M064_duplicate_snapshot_idempotence(self):
        a=make_fixture();b=copy.deepcopy(a);b['companies'][0]['metrics']['price']+=1
        stamps=[datetime(2026,1,i,tzinfo=timezone.utc) for i in (1,2,3)]
        with tempfile.TemporaryDirectory() as t,patch('investment.store.datetime') as clock:
            clock.now.side_effect=stamps;st=storage.Store(t,'work','fixture')
            st.save_snapshot(a);st.save_snapshot(b);st.save_snapshot(a)
            self.assertEqual(st.latest(),b)

    def test_M069_model_event_identity(self):
        with tempfile.TemporaryDirectory() as t:
            st=storage.Store(t,'work','fixture');a=dict(code='900000',path='technology',quarter='2026-06-30',model='v1')
            self.assertNotEqual(st.event(a),st.event(dict(a,model='v2')))

    def test_M070_event_reevaluation(self):
        with tempfile.TemporaryDirectory() as t:
            st=storage.Store(t,'work','fixture');a=dict(code='900000',path='technology',quarter='2026-06-30',model='v1',status='pending')
            eid=st.event(a);b=dict(a,status='confirmed');self.assertEqual(st.event(b),eid)
            with st.connect() as db:saved=json.loads(db.execute('SELECT payload FROM events WHERE id=?',(eid,)).fetchone()[0])
            self.assertEqual(saved,b)

    def test_M111_equal_phase_windows_rejected(self):
        c=phase.load_config();c['ma_fast']=c['ma_slow']
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'phase.json';p.write_text(json.dumps(c),encoding='utf-8')
            with self.assertRaises(ValueError):phase.load_config(p)

    def test_M116_high_window_excludes_lower_date(self):self.assertEqual(short_phase_path([200]+[100]*7)[-1]['phase'],'미확인')

    def test_M117_breakout_keeps_full_prior_window(self):self.assertEqual(short_phase_path([100]*7+[50,75])[-1]['phase'],'사')

    def test_M118_equal_high_is_not_breakout(self):self.assertEqual(short_phase_path([100]*7+[50,100])[-1]['phase'],'사')

    def test_M119_last_equal_peak(self):
        path=[dict(date=str(i),phase=p,close=v) for i,(p,v) in enumerate(zip(['쇠','생','왕','왕','쇠'],[90,100,120,120,100]))]
        self.assertEqual(episodes(path)[0]['peak'],'3')

    def test_M137_exact_snapshot_limit(self):
        snapshot=make_fixture();raw=json.dumps(snapshot).encode()
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'snapshot.json';p.write_bytes(raw+b' '*(30*1024*1024-len(raw)))
            self.assertEqual(infomax_provider.SavedSnapshotProvider(p).fetch()[0],snapshot)

    def test_M160_exact_thesis_id_length(self):
        with tempfile.TemporaryDirectory() as t:
            for size in (99,100):self.assertEqual(research_followup.plan_path(t,'work','x'*size,1).suffix,'.json')
            with self.assertRaises(ValueError):research_followup.plan_path(t,'work','x'*101,1)

    def test_M165_exact_export_limit(self):
        with tempfile.TemporaryDirectory() as t,patch('investment.telegram_export.MAX_BYTES',7):
            p=Path(t)/'export.json';p.write_bytes(b'{"x":1}');self.assertEqual(telegram_export.read_json(p),{'x':1})

    def test_M176_max_safe_integer(self):
        limit=2**53-1
        for n in (limit-1,limit):
            self.assertEqual(visuals.waterfall_records([dict(code='900000',name='S',cost_krw=n,value_krw=n)])[-1]['end'],n)
        self.assertEqual(visuals.waterfall_records([dict(code='900000',name='S',cost_krw=limit+1,value_krw=limit+1)]),[])

    def test_M180_zero_year_unknown(self):
        self.assertIsNone(workspace_research._period_end('0000Q1'))
        self.assertEqual(workspace_research._period_end('0001Q1'),date(1,3,31))

    def test_M185_20_past_rows_without_today(self):
        from tests import test_infomax_daily as daily_tests
        c=daily_tests.DailyImportTests();self.addCleanup(c.doCleanups);c.setUp();c.values.pop(3)
        self.assertEqual(len(c.values),23);self.assertEqual(len(c.convert()['companies'][0]['prices']),20)

    def test_M209_ahead_only_not_diverged(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            def command(cmd,**kw):
                a=cmd[3:];out=''
                if a==['rev-parse','--show-toplevel']:out=str(root)
                elif a==['remote']:out='origin\n'
                elif a[0]=='symbolic-ref':out='main\n'
                elif a[0]=='rev-parse' and '--abbrev-ref' in a:out='origin/main\n'
                elif a[:2]==['rev-parse','--git-path']:out=str(root/'.git'/a[-1])
                elif a[0]=='rev-list':out='1 0\n'
                return subprocess.CompletedProcess(cmd,0,out,'')
            with patch('tools.pc_check.subprocess.run',side_effect=command):self.assertEqual(pc_check.inspect(root)['state'],'local_ahead')

    def test_M142_maximum_history_span(self):
        from investment.market_history import _request
        start=date(2010,1,1)
        for days in (3699,3700):
            end=start+timedelta(days=days)
            self.assertEqual(_request('900000','item',start.isoformat(),end.isoformat())[1]['endDateTime'],end.strftime('%Y%m%d')+'2359')
        with self.assertRaises(ValueError):_request('900000','item',start.isoformat(),(start+timedelta(days=3701)).isoformat())

    def test_M146_period_end_cutoff_is_inclusive(self):
        from tests.test_fiscal_native_financial import fiscal_report
        from investment.native_financial import fiscal_quarter_records
        report=fiscal_report(fy=2026,month=12,q=1,available='2026-03-31')[0]
        self.assertEqual(fiscal_quarter_records([report],'2026-03-30'),[])
        for cutoff in ('2026-03-31','2026-04-01'):
            rows=fiscal_quarter_records([report],cutoff)
            self.assertEqual([r['period_end'] for r in rows],['2026-03-31'])
            self.assertEqual(rows[0]['revenue'],report['values']['revenue'])

    def test_M151_annual_period_on_retrieval_date(self):
        from tests import test_nice_financial as helpers
        from investment.nice_financial import parse_finance
        raw=helpers.NiceFinancialTests().sample()
        for cutoff,expected in [('2025-12-30',False),('2025-12-31',True),('2026-01-01',True)]:
            result=parse_finance(raw,'900000','synthetic','CFS','1234567',12,cutoff+'T00:00:00+00:00')
            self.assertEqual('2025-12-31' in [c['period_end'] for c in result['columns']],expected)

    def test_M156_scan_caps_observed_reports_at_500(self):
        from tests import test_report_inbox as helpers
        c=helpers.ReportInboxTests();self.addCleanup(c.doCleanups);c.setUp()
        for i in range(501):c.put(f'{i:03d}.html')
        with patch('investment.report_inbox.datetime') as clock,patch('investment.report_inbox.time.time',return_value=100):
            clock.now.return_value=datetime(2026,1,2,tzinfo=timezone.utc)
            view=c.inbox.scan()
        self.assertEqual(len(c.inbox.observed),500)
        self.assertEqual(len(c.inbox.files),500)
        self.assertIn('500',view['error'])

    def test_M172_zero_denominator_is_unknown(self):
        from investment.trend_diagnostics import diagnose
        for denominator,expected in [(-1,None),(0,None),(1,8900)]:
            result=diagnose([dict(close=100)],dict(sma={'150':90,'200':denominator}))
            check=next(c for c in result['checks'] if c['id']=='long_stack')
            self.assertEqual(check['value'],expected)
            self.assertEqual(check['status'],'unknown' if expected is None else 'pass')

    def test_M193_all_snapshot_companies_can_receive_valuation(self):
        from tests import test_valuation as helpers
        from tools.infomax_valuation import build
        c=helpers.ValuationTests();c.setUp();self.addCleanup(c.doCleanups)
        c.snapshot['companies']=[c.row]
        observations=dict(schema_version='infomax-valuation-0.1',companies={c.row['code']:[c.observation()]})
        result=build(c.snapshot,observations)
        self.assertEqual({r['code'] for r in result['companies']},set(observations['companies']))
        self.assertEqual(result['companies'][0]['metrics']['per'],10)

    def test_M199_return_must_be_strictly_positive(self):
        from tools.trend_sensitivity_report import terms,TREND_BASE
        days=[(date(2025,1,1)+timedelta(days=i)).isoformat() for i in range(253)]
        entry=dict(closes=[100]*253,dates=days,bm=dict.fromkeys(days,100))
        for close,expected in [(99,False),(100,False),(101,True)]:
            entry['closes'][-1]=close
            self.assertEqual(terms(entry,TREND_BASE)['back'],expected)


    def test_M131_zero_revisions_are_already_material(self):
        # Characterizes the equivalent mutation; deliberately survives both forms.
        from tests.test_financial_update_policy import bundle
        from investment.financial_update_policy import decide_update
        for old,new in [(0,1),(0,-1),(1,0),(-1,0)]:
            result=decide_update(bundle(old),bundle(new))
            self.assertEqual(result['action'],'update')
            self.assertTrue(result['changes'][0]['material'])
        self.assertEqual(decide_update(bundle(0),bundle(0))['action'],'unchanged')


if __name__=='__main__':unittest.main()
