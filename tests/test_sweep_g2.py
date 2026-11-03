"""Boundary regressions for group 2; synthetic inputs and isolated external effects."""
import base64,json,tempfile,unittest
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import Mock,MagicMock,patch
from investment import research,refresh as rf,adapters,company_detail,daily_dashboard
from investment import holdings_sync,research_drop,shared_dashboard,trend_checkpoints,verification,data_recovery
from investment import company_reports,financial_metrics,market_explanation,metrics,naver_review,report,workspace_export
from investment.fixture import make_fixture
from tests import test_refresh as refresh_tests, test_dashboard_upgrade as upgrade_tests
from tests import test_naver_review as naver_tests, test_marketcap_history as cap_tests
from tools import complete_financials,infomax_review,trend_history

class FixedDateTime(datetime):
    @classmethod
    def now(cls,tz=None):
        value=cls(2026,10,2,12,tzinfo=timezone.utc)
        return value.astimezone(tz) if tz else value.replace(tzinfo=None)

@contextmanager
def refresh_case():
    # Reuse the existing synthetic workbook and temporary SQLite fixture.
    with patch('investment.refresh.datetime',FixedDateTime),patch('investment.store.datetime',FixedDateTime),patch('batch.run',return_value={'snapshot_id':'synthetic'}):
        c=refresh_tests.RefreshTests();c.setUp()
        try:yield c
        finally:c.doCleanups()

def quarters(op=10):
    out=[]
    for k in range(13):
        y=2022+k//4; q=k%4+1; end=f'{y}-{q*3:02d}-{30 if q in (2,3) else 31}'
        out.append(dict(period_end=end,available_at=end,basis='CFS',revenue=100,op=op))
    return out

def annual(revenues,ops,dps):
    return [dict(period_end=f'{2022+i}-12-31',available_at=f'{2022+i}-12-31',basis='CFS',revenue=r,op=o,dps=d,dps_basis='ordinary',
                 equity=100,debt=0,cash=0,effective_tax_rate=0,tax_verified=True,ocf=10) for i,(r,o,d) in enumerate(zip(revenues,ops,dps))]


class Group2Tests(unittest.TestCase):
    def setUp(self):
        # Keep even reused helpers' temporary files within this scratch copy.
        temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.addCleanup(temp.cleanup)
        self.enterContext(patch('tempfile.tempdir',temp.name))
        self.enterContext(patch('requests.sessions.Session.request',side_effect=AssertionError('network forbidden')))
        self.enterContext(patch('subprocess.run',side_effect=AssertionError('child tools forbidden')))

    def test_M011_equal_current_margins(self):
        for op in (9,10,11):
            q=quarters();q[-1]['op']=op
            self.assertEqual(research.financial_signals(q,'2026-12-31')['cross_up'],op>10)

    def test_M013_zero_profit(self):
        for op in (-1,0,1):
            q=quarters(0);q[-1]['op']=op
            self.assertEqual(research.financial_signals(q,'2026-12-31')['profit_turn'],op>0)

    def test_M014_zero_sales_growth(self):
        a=annual([100]*4,[10,20,30,40],[1,2,4,8])
        for revenue in (99,100,101):
            a[-1]['revenue']=revenue
            self.assertEqual(research.annual_signals(a,'2026-12-31')['returns_signal'],revenue>=100)

    def test_M015_equal_growth(self):
        a=annual([100,200,400,800],[10,20,40,80],[1,4,16,64])
        for op in (79,80,81):
            a[-1]['op']=op
            self.assertEqual(research.annual_signals(a,'2026-12-31')['returns_signal'],op>80)

    def test_M016_cutoff_evidence(self):
        row={'evidence':[dict(path='technology',available_at='2026-10-02',first_seen_at='2026-10-02',reviewed_at='2026-10-02',
                            review_status='confirmed',document='doc',location='p1',summary='synthetic')]}
        for cutoff in ('2026-10-01','2026-10-02','2026-10-03'):
            self.assertEqual(research.evidence_status(row,'technology',cutoff),'pending' if cutoff<'2026-10-02' else 'confirmed')

    def test_M017_same_day_review(self):
        row={'evidence':[dict(path='technology',available_at='2026-10-01',first_seen_at='2026-10-01',reviewed_at='2026-10-01',
                            review_status='confirmed',document='doc',location='p1',summary='synthetic')]}
        for reviewed in ('2026-09-30','2026-10-01','2026-10-02'):
            row['evidence'][0]['reviewed_at']=reviewed
            self.assertEqual(research.evidence_status(row,'technology','2026-10-02'),'pending' if reviewed<'2026-10-01' else 'confirmed')

    def test_M018_zero_tax(self):
        row={'annual':annual([100]*4,[10]*4,[1]*4),'metrics':{'eps_ttm':1,'price':10,'net_debt_equity_pct':0},'valuation_basis':'CFS'}
        for tax in (-1,0,1):
            for record in row['annual']:record['effective_tax_rate']=tax
            self.assertEqual(research.quality_factors(row,'2026-12-31')['Q'],None if tax<0 else .1*(1-tax))

    def test_M019_zero_eps(self):
        row={'annual':[],'metrics':{'eps_ttm':0,'price':10,'net_debt_equity_pct':0},'valuation_basis':'CFS'}
        for eps in (-1,0,1):
            row['metrics']['eps_ttm']=eps
            self.assertEqual(research.quality_factors(row,'2026-12-31')['V'],.1 if eps>0 else None)

    def test_M020_both_balanced_rounds(self):
        rows=[]
        for i,path in enumerate(research.PATHS):
            for j in range(2):
                rows.append(dict(code=f'{i}{j}',name=f'{i}{j}',paths={p:dict(eligible=p==path,sort=(2-j,0)) for p in research.PATHS}))
        chosen=research.balanced_list(rows)
        self.assertEqual(len(chosen),10)
        self.assertEqual([r['code'] for r in chosen],[f'{i}{j}' for j in range(2) for i in range(5)])

    def test_M084_zero_price_rejected(self):
        with refresh_case() as c:
            c.daily['companies'][0]['metrics']['price']=0
            with self.assertRaises(ValueError):rf.refresh(c.root)

    def test_M085_observation_date_equals_price_date(self):
        with refresh_case() as c:
            c.daily['meta']['as_of']=c.daily['meta']['price_date']
            with c.store.connect() as db:db.execute('DELETE FROM snapshots')
            provider=Mock();provider.fetch.return_value=(c.daily,{'synthetic':1},'synthetic.json')
            with patch('batch.run',return_value={'snapshot_id':'synthetic'}):r=rf.refresh(c.root,provider=provider)
            self.assertEqual(r['snapshot']['meta']['price_date'],r['snapshot']['meta']['as_of'])

    def test_M086_observation_today(self):
        with refresh_case() as c:
            today='2026-10-02';c.daily['meta']['as_of']=today
            with c.store.connect() as db:db.execute('DELETE FROM snapshots')
            provider=Mock();provider.fetch.return_value=(c.daily,{'synthetic':1},'synthetic.json')
            with patch('batch.run',return_value={'snapshot_id':'synthetic'}):r=rf.refresh(c.root,provider=provider)
            self.assertEqual(r['snapshot']['meta']['as_of'],today)

    def test_M087_financial_metadata_preserved(self):
        with refresh_case() as c:
            c.daily['meta']['financial_period']='2025-12-31'
            self.assertEqual(rf.merge_daily(c.previous,c.daily)['meta']['financial_period'],'2026-06-30')

    def test_M090_mismatched_batch_snapshot_is_partial(self):
        with refresh_case() as c,patch('batch.run',return_value={'snapshot_id':'wrong'}):
            r=rf.refresh(c.root);self.assertEqual(r['receipt']['status'],'partial');self.assertEqual(len(r['receipt']['errors']),2)

    def test_M121_retry_http_500(self):
        session=Mock();ok=Mock(status_code=200,headers={});ok.json.return_value={'ok':1}
        session.request.side_effect=[Mock(status_code=500),ok]
        value=adapters.Reader('work',{},session=session,sleep=lambda _:None)._request('GET','https://example.test')
        self.assertEqual(value[0],{'ok':1});self.assertEqual(session.request.call_count,2)

    def test_M123_zero_chart_close(self):
        row=dict(code='900000',market='KOSPI',prices=[dict(date='2026-10-01',close=0,final=True,venue='KRX',adjustment_basis='naver_chart_adjusted')])
        for close in (-1,0,1):
            row['prices'][0]['close']=close
            bars=company_detail.chart_history(row,{'meta':{'price_date':'2026-10-01'}})['bars']
            self.assertEqual([p['close'] for p in bars],[1] if close>0 else [])

    def test_M136_exact_remote_limit(self):
        value={'kind':'investment-holdings-sync','version':1,'state':{}};raw=json.dumps(value).encode();raw+=b' '*(holdings_sync.LIMIT-len(raw))
        remote=holdings_sync.GitHubStorage('fixture/example');remote.verify_private=Mock()
        remote.api=Mock(return_value=dict(type='file',encoding='base64',size=len(raw),sha='a'*40,content=base64.b64encode(raw).decode()))
        self.assertEqual(remote.read(),({},'a'*40))

    def test_M159_exact_drop_size(self):
        with tempfile.TemporaryDirectory() as t,patch('investment.research_drop.MAX_BYTES',3):
            p=Path(t)/'source.txt'
            for size in (2,3,4):
                p.write_bytes(b'x'*size)
                self.assertEqual(list(research_drop._items(Path(t)))[0]['status'],'pending' if size<=3 else 'too_large')

    def test_M164_exact_payload_limit(self):
        v={'x':1}
        for limit in (6,7,8):
            with patch('investment.shared_dashboard.MAX_RESULT_EXPANDED',limit):
                if limit<7:
                    with self.assertRaises(ValueError):shared_dashboard.encode_result_payload(v)
                else:self.assertEqual(shared_dashboard.restore_result_payload(shared_dashboard.encode_result_payload(v)),v)

    def test_M127_exact_upload_limit(self):
        fake=MagicMock();fake.session_state={};fake.button.side_effect=[True,False];fake.form_submit_button.return_value=False
        def columns(n):
            cols=[Mock() for _ in range(n)]
            for col in cols:col.number_input.side_effect=lambda *a,**k:a[3]
            return cols
        fake.columns.side_effect=columns;uploaded=Mock();uploaded.name='synthetic.json';uploaded.size=12*1024*1024
        raw=b'{"mode":"user_input"}';uploaded.getvalue.return_value=raw+b' '*(uploaded.size-len(raw));fake.file_uploader.return_value=uploaded
        with patch('investment.daily_dashboard.st',fake),patch('investment.daily_dashboard.verify'):
            self.assertEqual(daily_dashboard._inputs({},dict(pending=[]),'input')[0],{'mode':'user_input'})

    def test_M171_zero_price_not_ready(self):
        r=dict(market='KOSPI',code='900000',name='S',ready=True,cap_eok=2000,rs=80,technical={'as_of':'2026-10-02','close':0})
        for close in (-1,0,1):
            r['technical']['close']=close
            self.assertEqual(trend_checkpoints.summarize(dict(as_of='2026-10-02',rows=[r]))['rows'][0]['ready'],close>0)

    def test_M175_zero_revenue_is_missing(self):
        for revenue in (-1,0,1):
            result=verification._recompute(dict(amounts={'revenue':revenue,'operating_profit':1},metrics={'operating_margin_pct':100}))
            self.assertEqual(result['kind'],'ok' if revenue>0 else 'missing')

    def test_M204_invalid_code_before_delegation(self):
        with tempfile.TemporaryDirectory() as t:
            daily=Mock();r=data_recovery.DataRecovery(t,daily,Mock())
            with patch.object(r,'view',return_value={'failures':[dict(kind='price',code='bad',can_retry=True)]}):
                with self.assertRaises(ValueError):r.retry('price','bad')
            daily.start.assert_not_called()

    def test_M125_exact_embedded_link_limit(self):
        prefix=company_reports.EmbeddedJSON.prefix;limit=2*1024*1024
        # At the exact limit the Base64 length is not divisible by four; strict decoding rejects it.
        raw=b'{} '+b' '*(((limit-len(prefix))//4)*3-3)
        href=prefix+base64.b64encode(raw).decode()
        valid=company_reports.EmbeddedJSON()
        valid.feed('<a download="report-input.json" href="'+href+'">report</a>')
        self.assertFalse(valid.invalid)
        self.assertEqual(valid.documents,{'report-input.json':{}})
        href+='='*(limit-len(href))
        self.assertEqual(len(href),limit)
        parser=company_reports.EmbeddedJSON()
        parser.feed('<a download="report-input.json" href="'+href+'">report</a>')
        self.assertTrue(parser.invalid)
        self.assertEqual(parser.documents,{'report-input.json':None})

    def test_M130_market_cap_must_be_positive(self):
        c=upgrade_tests.FinancialContractTests();c.setUp()
        for cap in (-1,0,1):
            with self.subTest(cap=cap):
                c.row['latest_quote']['market_cap_eok']=cap
                value=financial_metrics.common_metrics(c.row,c.table,c.t)['metrics']['per']
                if cap<=0:self.assertIsNone(value)
                else:self.assertGreater(value,0)

    def test_M141_exact_breadth_history_window(self):
        row=dict(market='KOSPI',code='900000',ready=True)
        for size in (49,50,51):
            with self.subTest(size=size):
                bars=[dict(close=100)]*(size-1)+[dict(close=101)]
                result=market_explanation.build_market_explanation('2026-10-02',[],[row],{'900000':bars},{},'synthetic')
                above=result['markets'][0]['breadth']['above']['50']
                self.assertEqual(above['eligible'],int(size>=50))
                self.assertEqual(above['count'],int(size>=50))

    def test_M145_period_ending_on_observation_date(self):
        history=dict(scope='current_observation',basis='CFS',income_basis='standalone_quarters',
                     observed_on='2025-12-31',annual=annual([100]*4,[10]*4,[1]*4),
                     quarters=[dict(period_end=d) for d in ('2025-03-31','2025-06-30','2025-09-30','2025-12-31')])
        row={'observed_financial_history':history};snapshot={'meta':dict(data_mode='user_input',as_of='2026-01-01')}
        self.assertEqual(metrics.current_history(row,snapshot),history)
        history['observed_on']='2025-12-30'
        self.assertIsNone(metrics.current_history(row,snapshot))
        history['observed_on']='2026-01-01'
        self.assertEqual(metrics.current_history(row,snapshot),history)

    def test_M149_zero_daily_close_rejected(self):
        c=naver_tests.NaverReviewTests();c.setUp();payload=c.daily[c.code]
        for close in (-1,0,1):
            with self.subTest(close=close):
                payload['items'][0]['closingPrice']=str(close)
                if close<=0:
                    with self.assertRaises(ValueError):naver_review.daily_values(payload,cutoff='2026-09-28')
                else:self.assertEqual(naver_review.daily_values(payload,cutoff='2026-09-28')[payload['items'][0]['tradingDateKst']]['close'],1)

    def test_M155_single_observation_has_no_chart(self):
        snapshot=make_fixture();row=snapshot['companies'][0];facts=research.analyze(snapshot)[0]
        row['prices']=row['prices'][-1:]
        self.assertIn('\uac00\uaca9 \uc774\ub825 \ubbf8\ud655\ubcf4',report.onepager(snapshot,row,facts))

    def test_M179_two_benchmark_closes_suffice(self):
        bars=[dict(date=d,close=v,final=True) for d,v in [('2026-10-01',100),('2026-10-02',110)]]
        snapshot=dict(meta=dict(data_mode='user_input'),benchmarks={m:bars for m in ('KOSPI','KOSDAQ')})
        result=workspace_export.market_summary(snapshot,{},'2026-10-02')
        self.assertEqual([r['market'] for r in result],['KOSPI','KOSDAQ'])
        for row in result:self.assertAlmostEqual(row['change_pct'],10)
        snapshot['benchmarks']={m:bars[-1:] for m in ('KOSPI','KOSDAQ')}
        self.assertEqual(workspace_export.market_summary(snapshot,{},'2026-10-02'),[])

    def test_M183_may_requires_current_first_quarter(self):
        with tempfile.TemporaryDirectory() as t:
            dest=Path(t);row=dict(code='900000',name='Synthetic',market='KOSPI',metrics={'market_cap_eok':2000})
            reports=[dict(basis='CFS',year=2025,quarter=q) for q in range(1,5)]
            (dest/'900000.json').write_text(json.dumps({'companies':{'900000':{'reports':reports}}}),encoding='utf-8')
            cache=dict(quotes={'quotes':{}},universe={'companies':[row]})
            with patch.object(complete_financials,'folder',return_value=dest),patch.object(complete_financials,'acquire_lock',return_value=Mock()), \
                 patch.object(complete_financials,'repair_saved',return_value=dict(repaired_companies=0,validated_sources=0,revalidation_failures=[])), \
                 patch.object(complete_financials,'saved_data',return_value={'snapshot':{}}),patch.object(complete_financials,'load_market_cache',return_value=cache), \
                 patch.object(complete_financials,'discovery_candidate',return_value=True),patch.object(complete_financials,'datetime') as clock, \
                 patch.object(complete_financials.time,'time',return_value=0),patch.object(complete_financials,'uuid4',return_value=Mock(hex='synthetic')), \
                 patch.object(complete_financials,'_collect_company',return_value={'action':'update'}) as collect:
                clock.now.return_value=datetime(2026,5,1)
                result=complete_financials.main(dest)
                self.assertEqual((result['total'],result['completed'],result['updated']),(1,1,1))
                collect.assert_called_once_with(dest,row,'2026-05-01')

    def test_M191_zero_market_cap_rejected(self):
        c=cap_tests.MarketCapHistoryTests();c.setUp()
        for value in (-1,0,1):
            with self.subTest(value=value):
                c.grid[3][1]=value
                if value<=0:
                    with self.assertRaises(ValueError):infomax_review.parse_marketcap_history(c.grid,c.info,c.dates)
                else:self.assertEqual(infomax_review.parse_marketcap_history(c.grid,c.info,c.dates)['005930']['2026-09-23'],1)

    def test_M198_exact_chart_response_limit_is_saved(self):
        payload=b' '*(20*1024*1024)
        with tempfile.TemporaryDirectory() as t,patch('requests.get',return_value=Mock(content=payload)) as get:
            files=trend_history.fetch_charts(t)
            self.assertEqual(set(files),set(trend_history.SYMBOLS.values())|{trend_history.INDEX})
            self.assertEqual(get.call_count,len(files))
            for path in files.values():self.assertEqual(path.read_bytes(),payload)


if __name__=='__main__':unittest.main()
