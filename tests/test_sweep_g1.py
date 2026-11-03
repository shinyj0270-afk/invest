"""Deterministic regression boundaries for group 1; verified with mutcheck.py."""
import copy,json,tempfile,unittest
from pathlib import Path
from datetime import date,datetime,timezone,timedelta
from unittest.mock import Mock,patch
from investment import company_financials as cf,leader_strategy as leader
from investment import agent_providers,company_events,financial_health,holdings_bridge,market_events
from investment import recommendation_allocation as allocation,research_library,thesis_monitor,dashboard_build
from investment import market_refresh,naver_reference,research_catalog,valuation,workspace_events
from investment.company_financials import history_targets
from tests.test_industry_phase import bars
from tests.test_fiscal_native_financial import fiscal_report
from tests import test_naver_reference as reference_tests,test_research_catalog as catalog_tests
from tests import test_returns_history as returns_tests,test_valuation as valuation_tests
from tests import test_workspace_events as event_tests
from tools import company_statements,infomax_import,returns_history

FIXED=datetime(2026,11,4,12,tzinfo=timezone(timedelta(hours=9)))

class FixedDatetime(datetime):
    @classmethod
    def now(cls,tz=None):return FIXED.astimezone(tz) if tz else FIXED.replace(tzinfo=None)

class FixedDate(date):
    @classmethod
    def today(cls):return FIXED.date()

def filing_page(page,total_pages,total):
    return (f'<input id="totalCnt" value="{total}"><span class="pageInfo">[{page}/{total_pages}]</span>'
        +f"<tr><td><a onclick=\"openCorpInfoNew('12345678')\">S</a></td>"
        +f'<td><a href="/dsaf001/main.do?rcpNo=20261002{page:06d}">synthetic</a></td></tr>')

def inventory_at_cutoff(test):
    record,_,args=fiscal_report(fy=2026,month=12,q=2,available='2026-06-30')
    row=dict(code='900000',name='가상 기업',market='KOSPI')
    with tempfile.TemporaryDirectory() as t:
        dest=Path(t);inv=dest/'inventory.json'
        inv.write_text(json.dumps(dict(schema='dart-fiscal-inventory-1',**row,reports=[args])),encoding='utf-8')
        with patch('investment.company_financials.folder',return_value=dest),patch('tools.company_statements.collect_receipt',return_value=record):
            test.assertEqual(cf._collect_inventory(dest,row,'2026-06-30',inv)['action'],'update')

def leader_case():
    ps=bars([100+i*.1 for i in range(300)]);cutoff=ps[-1]['date'];rows=[];facts={};histories={}
    for i in range(5):
        code=str(900000+i)
        details={k:dict(period='2026-06-30',basis='CFS',price_date=cutoff,currency='KRW',status='estimated') for k in ('per','pbr')}
        rows.append(dict(code=code,name=code,market='KOSPI',industry='I',discovery_allowed=True,metrics={'market_cap_eok':2000,'per':i+1,'pbr':i+1},metric_details=details))
        facts[code]={'technical':dict(close=ps[-1]['close'],as_of=cutoff,price_health={'status':'ready'})};histories[code]={'prices':ps}
    return dict(snapshot=dict(meta={'price_date':cutoff},companies=rows),research={'rows':facts}),{'history':{'histories':histories}}

class SweepGroup1Tests(unittest.TestCase):
    def setUp(self):
        # Keep even reused helper temp directories inside this extracted scratch tree.
        for target,value in [('tempfile.tempdir',str(Path(__file__).resolve().parents[1])),
                             ('investment.company_financials.datetime',FixedDatetime),
                             ('tools.company_statements.date',FixedDate)]:
            p=patch(target,value);p.start();self.addCleanup(p.stop)
        p=patch('requests.sessions.Session.request',side_effect=AssertionError('network forbidden'))
        p.start();self.addCleanup(p.stop)
        p=patch('investment.company_financials.time.sleep')
        p.start();self.addCleanup(p.stop)

    def test_M041_may_report(self):
        for month in (4,5,6):self.assertEqual((2026,1) in history_targets(f'2026-{month:02d}-01'),month>=5)
    def test_M042_august_report(self):
        for month in (7,8,9):self.assertEqual((2026,2) in history_targets(f'2026-{month:02d}-01'),month>=8)
    def test_M043_november_report(self):
        for month in (10,11,12):self.assertEqual((2026,3) in history_targets(f'2026-{month:02d}-01'),month>=11)
    def test_M101_equal_lag_window(self):
        c=leader.load_config()
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'config.json'
            for offset in (-1,0,1):
                c['momentum_lag']=c['window']+offset;p.write_text(json.dumps(c),encoding='utf-8')
                if offset<0:
                    with self.assertRaisesRegex(ValueError,'lag'):leader.load_config(p)
                else:self.assertEqual(leader.load_config(p),c)
    def test_M102_exact_history_length(self):
        c=leader.load_config()
        for offset in (-1,0,1):
            ps=bars([100]*(c['window']+c['momentum_lag']+offset))
            t=dict(close=100,as_of=ps[-1]['date'],price_health={'status':'ready'})
            values,reason=leader.raw_features({'prices':ps},t,t['as_of'],c)
            if offset<0:self.assertTrue(reason)
            else:self.assertEqual((values['momentum_pct'],values['turnover_change_pct'],reason),(0,0,''))
    def test_M049_exact_100_pages(self):
        for pages in (99,100,101):
            session=Mock()
            session.post.side_effect=lambda *a,**kw:Mock(content=filing_page(int(kw['data']['currentPage']),pages,pages).encode('utf-8'))
            with self.subTest(pages=pages):
                if pages<=100:self.assertEqual(len(cf.fetch_filings('2026-10-02',session=session)),pages)
                else:
                    with self.assertRaises(ValueError):cf.fetch_filings('2026-10-02',session=session)
    def test_M050_last_page_stops(self):
        session=Mock();session.post.return_value.content=filing_page(1,1,1).encode('utf-8')
        self.assertEqual(len(cf.fetch_filings('2026-10-02',session=session)),1)
        self.assertEqual(session.post.call_count,1)
    def test_M048_exact_retry_deadline(self):
        row=dict(code='900000',name='S',market='KOSPI',eligibility='candidate',metrics={'market_cap_eok':2000})
        for retry,deadline in ((True,60),(False,3600)):
            for elapsed in (deadline-1,deadline,deadline+1):
                with self.subTest(retry=retry,elapsed=elapsed),tempfile.TemporaryDirectory() as tmp, \
                     patch('investment.company_financials.load_market_cache',return_value={'universe':{'companies':[row]}}), \
                     patch('investment.company_financials.folder',return_value=Path(tmp)), \
                     patch('investment.company_financials.time.monotonic',return_value=40+elapsed), \
                     patch('investment.company_financials.Thread'):
                    service=cf.CompanyFinancials(tmp);service.jobs['900000']=dict(status='failed',attempt=40)
                    self.assertEqual(service.start('900000',retry=retry)['status'],'failed' if elapsed<deadline else 'running')
    def test_M044_cfs_publication_on_cutoff(self):
        with tempfile.TemporaryDirectory() as t:
            dest=Path(t);row=dict(code='900000',name='S',market='KOSPI')
            def collect(*a,**kw):return dict(basis=a[2],year=a[3],quarter=a[4],available_at='2026-06-30',values={'revenue':1})
            with patch('investment.company_financials.folder',return_value=dest), \
                 patch('investment.company_financials.history_targets',return_value=[(2026,2)]), \
                 patch('investment.company_financials.resolve_company',return_value=('12345678','S')), \
                 patch('investment.company_financials.time.sleep'),patch('tools.company_statements.collect',side_effect=collect) as fetch:
                cf._collect_company(dest,row,'2026-06-30')
                self.assertEqual(fetch.call_count,1)
            saved=json.loads((dest/'900000.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['companies']['900000']['reports'][0]['basis'],'CFS')
    def test_M046_native_publication_on_cutoff(self):inventory_at_cutoff(self)
    def test_M047_native_period_on_cutoff(self):inventory_at_cutoff(self)
    def test_M108_value_upper_tail_equality(self):
        d,c=leader_case();v=leader.build(d,c)
        self.assertEqual(next(r for r in v['rows'] if r['code']=='900001')['value_band'],'저평가')
    def test_M109_value_lower_tail_equality(self):
        d,c=leader_case();v=leader.build(d,c)
        self.assertEqual(next(r for r in v['rows'] if r['code']=='900003')['value_band'],'고평가')
    def test_M110_both_axes_required(self):
        for volume,expected in ((1,False),(1000,True)):
            d,c=leader_case();prices=copy.deepcopy(c['history']['histories']['900002']['prices'])
            for bar in prices[-21:]:bar.update(close=1000,volume=volume)
            c['history']['histories']['900002']['prices']=prices
            d['research']['rows']['900002']['technical']['close']=1000
            row=next(r for r in leader.build(d,c)['rows'] if r['code']=='900002')
            self.assertEqual(row['momentum_band'],'상');self.assertEqual(row['value_band'],'중립')
            self.assertEqual(row['turnover_band'],'상' if expected else '하')
            self.assertEqual(row['candidate'],expected)
    def test_M122_zero_usage_valid(self):
        value=dict(status='completed',output=[dict(type='message',content=[dict(type='output_text',text='{}')])])
        for count in (-1,0,1):
            value['usage']={'input_tokens':count,'output_tokens':count}
            if count<0:
                with self.assertRaises(agent_providers.ProviderError):agent_providers.decode_response('openai',value)
            else:self.assertEqual(agent_providers.decode_response('openai',value)['usage'],value['usage'])
    def test_M124_exact_100_clusters(self):
        for size in (99,100):
            self.assertEqual(company_events.parse({'clusters':[{'items':[]} for _ in range(size)]},'900000','news',FIXED),[])
        with self.assertRaisesRegex(ValueError,'news_size'):
            company_events.parse({'clusters':[{'items':[]} for _ in range(101)]},'900000','news',FIXED)
    def test_M126_zero_denominator(self):
        from investment.core import ratio
        self.assertIsNone(ratio(1,-1));self.assertIsNone(ratio(1,0));self.assertEqual(ratio(1,1),1)
    def test_M129_exact_record_limit(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'record.json'
            for size in (4_999_999,5_000_000,5_000_001):
                p.write_bytes(b'{"x":1}'+b' '*(size-7))
                self.assertEqual(financial_health.read_record(p),{'x':1} if size<=5_000_000 else {})
    def test_M135_zero_saved_close(self):
        for close in (-1,0,1):
            bar=dict(date='2026-10-01',close=close,final=True,venue='KRX',adjustment_basis='naver_chart_adjusted')
            record=dict(symbol='900000',kind='item',prices=[bar])
            self.assertEqual(holdings_bridge.saved_naver_close(record,'900000','2026-10-02'),bar if close>0 else None)
    def test_M140_exact_url_length(self):
        prefix='https://example.test/'
        for size in (3999,4000):
            url=prefix+'x'*(size-len(prefix));self.assertEqual(market_events.safe_url(url),url)
        with self.assertRaises(ValueError):market_events.safe_url(prefix+'x'*(4001-len(prefix)))
    def test_M162_exact_text_limit(self):
        for size in (1999,2000):self.assertEqual(research_library.text('x'*size),'x'*size)
        with self.assertRaises(ValueError):research_library.text('x'*2001)
    def test_M154_cap_equality_rounding(self):
        self.assertEqual(allocation.capped_weights([4.0,1.5000000005,3.9999999995],95,40),[40,15.00000001,39.99999999])
    def test_M169_zero_year_ago_profit(self):
        current=dict(period_end='2026-06-30',statement_values={'operating_profit':10})
        for value,expected in ((-1,0),(0,0),(1,900)):
            prior=dict(period_end='2025-06-30',statement_values={'operating_profit':value})
            self.assertEqual(thesis_monitor._yoy([prior,current],current,'operating_profit',turnaround=True),expected)
    def test_M203_ignore_non_source_file(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'investment').mkdir();p=root/'investment/notes.txt';p.write_text('a')
            before=dashboard_build.source_fingerprint(root);p.write_text('b');self.assertEqual(dashboard_build.source_fingerprint(root),before)

    def test_M144_zero_quote_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            folder=Path(t);row=dict(code='900000',name='Synthetic',market='KOSPI',eligibility='candidate')
            (folder/'universe.json').write_text(json.dumps(dict(companies=[row])),encoding='utf-8')
            for price in (-1,0,1):
                fresh=dict(row,metrics={'price':price},retrieved_at=FIXED.isoformat(),source='synthetic')
                fetch=Mock(return_value=dict(pagination_complete=True,errors=[],retrieved_at=FIXED.isoformat(),companies=[fresh]))
                with self.subTest(price=price):
                    if price<=0:
                        with self.assertRaisesRegex(ValueError,'no_valid_quotes'):
                            market_refresh.collect_quotes(folder,lambda _:None,fetch=fetch)
                    else:
                        self.assertEqual(market_refresh.collect_quotes(folder,lambda _:None,fetch=fetch)['updated_companies'],1)
                        self.assertEqual(json.loads((folder/'latest-quotes.json').read_text(encoding='utf-8'))['quotes']['900000']['price'],1)

    def test_M148_name_length_boundary(self):
        fixture=reference_tests.NaverReferenceTests();fixture.setUp()
        for size in (199,200,201):
            raw=dict(fixture.raw,itemname='x'*size)
            with self.subTest(size=size):
                if size<=200:self.assertEqual(naver_reference.parse_reference(raw,'900001',fixture.now)['name'],'x'*size)
                else:
                    with self.assertRaises(ValueError):naver_reference.parse_reference(raw,'900001',fixture.now)

    def test_M158_thirty_unique_catalog_tags(self):
        # An in-memory persistence seam returns the actual validated annotation payload.
        library=Mock();library.history.return_value=[];library.get.return_value={}
        library._put.side_effect=lambda kind,key,payload,revision:payload
        for size in (29,30,31):
            value=catalog_tests.metadata();value.update(tags=['tag'+str(i) for i in range(size)],persons=[])
            with self.subTest(size=size):
                if size<=30:
                    self.assertEqual(research_catalog.annotate(library,'source','s1',value)['tags'],value['tags'])
                else:
                    with self.assertRaises(ValueError):research_catalog.annotate(library,'source','s1',value)

    def test_M174_hundred_distinct_observations(self):
        fixture=valuation_tests.ValuationTests();fixture.setUp()
        records=[fixture.observation(source='synthetic-'+str(i)) for i in range(101)]
        for size in (99,100):self.assertEqual(valuation.validate_observations(records[:size]),records[:size])
        with self.assertRaises(ValueError):valuation.validate_observations(records)

    def test_M178_cached_event_text_limits(self):
        fixture=event_tests.WorkspaceEventTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.database()
        for size in (-1,0,1):
            # Separate event identities let both title and source boundaries be exercised.
            fixture.add('title'+str(size),event='title'+str(size),kind='news',title='t'*(1000+size),source='source',
                        observed='2026-09-25T10:00:00+09:00',published_on='2026-09-25')
            fixture.add('source'+str(size),event='source'+str(size),kind='news',title='title',source='s'*(200+size),
                        observed='2026-09-25T10:00:00+09:00',published_on='2026-09-25')
        items=workspace_events.load_cached_events(fixture.root,fixture.snapshot)['005930']
        self.assertEqual(sorted(len(i['title']) for i in items),[5,5,999,1000])
        self.assertEqual(sorted(len(i['source']) for i in items),[6,6,199,200])

    def test_M182_exact_main_document_size(self):
        record,viewer,args=fiscal_report(month=6,q=4,available='2026-09-22')
        entry=dict(basis='CFS',year=2026,quarter=4,period_contract=args['period_contract'])
        corp='12345678';receipt=record['receipt']
        main=f"<span onclick=\"openCorpInfoNew('{corp}', 'winCorpInfo', '/dsae001/selectPopup.ax');\">가상 기업</span>"
        main+=''.join("node1['"+k+"'] = \""+v+"\";" for k,v in dict(rcpNo=receipt,dcmNo='123',eleId='19',offset='10',length='999',dtd='dart4.xsd').items())
        main+="node1['tocNo']='19';"
        for size in (4*1024*1024-1,4*1024*1024,4*1024*1024+1):
            session=Mock();session.get.side_effect=[Mock(content=main.encode().ljust(size,b' ')),Mock(content=viewer.encode())]
            with self.subTest(size=size),tempfile.TemporaryDirectory() as t, \
                 patch('investment.company_financials.resolve_company',return_value=(corp,'가상 기업')), \
                 patch('investment.company_financials.fetch_filings',return_value=[dict(receipt=receipt,corp=corp,name='가상 기업',title='사업보고서 (2026.06)')]):
                if size<=4*1024*1024:
                    result=company_statements.collect_receipt(session,entry,Path(t),code='900000',name='가상 기업',market='KOSPI')
                    self.assertEqual(result['basis'],'CFS');self.assertEqual(result['values'],record['values'])
                else:
                    with self.assertRaisesRegex(ValueError,'목차 크기 초과'):
                        company_statements.collect_receipt(session,entry,Path(t),code='900000',name='가상 기업',market='KOSPI')

    def test_M190_exact_expanded_xlsx_size(self):
        from openpyxl import Workbook
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'fixture.xlsx';book=Workbook();book.active['A1']='ok';book.save(path);book.close()
            for size in (100*1024*1024-1,100*1024*1024,100*1024*1024+1):
                # Mock only the preflight metadata, keeping the actual XLSX parser real.
                with self.subTest(size=size),patch('tools.infomax_import.ZipFile') as archive:
                    archive.return_value.__enter__.return_value.infolist.return_value=[Mock(file_size=size)]
                    if size<=100*1024*1024:self.assertEqual(infomax_import.read_grid(path)[0][0][0],'ok')
                    else:
                        with self.assertRaisesRegex(ValueError,'압축 해제 크기 제한'):infomax_import.read_grid(path)

    def test_M196_zero_cash_preserves_positive_invested_capital(self):
        fixture=returns_tests.ReturnsHistoryTests();fixture.setUp()
        row=fixture.base['companies'][0]
        for year in ('2024','2025'):
            row['financial_accounts']['balance'][year+'-12-31']['현금및현금성자산']=0
            fixture.review['companies'][row['code']]['balances'][year]['cash']=0
        result=returns_history.build(fixture.base,fixture.review,fixture.balance_review,'review','balance')['companies'][0]
        self.assertEqual(result['financial_accounts']['balance']['2025-12-31']['현금및현금성자산'],0)
        self.assertAlmostEqual(result['observed_returns_history']['roic_proxy_2025_pct'],8_000_000_000_000/125_000_000_000_000*100)

    def test_M045_current_parser_keeps_small_revision_deferred(self):
        # Representative equivalence check; the proof is in REPORT_g1.md.
        record,_,_=fiscal_report(month=12,q=2,available='2026-06-30')
        record['parser_version']=cf.PARSER_VERSION
        revised=copy.deepcopy(record);revised['values']['revenue']*=1.01
        with tempfile.TemporaryDirectory() as t:
            dest=Path(t);path=dest/'900000.json'
            path.write_text(json.dumps(dict(companies={'900000':{'reports':[record]}})),encoding='utf-8')
            before=path.read_bytes()
            with patch('investment.company_financials.folder',return_value=dest), \
                 patch('investment.company_financials.history_targets',return_value=[(2026,2)]), \
                 patch('investment.company_financials.resolve_company',return_value=('12345678','가상 기업')), \
                 patch('tools.company_statements.collect',return_value=revised):
                result=cf._collect_company(dest,dict(code='900000',name='가상 기업',market='KOSPI'),'2026-06-30')
            self.assertEqual((result['action'],result['reason']),('defer','below_threshold'))
            self.assertEqual(path.read_bytes(),before)

if __name__=='__main__':unittest.main()
