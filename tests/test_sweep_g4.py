"""Offline regression boundaries for mutation group 4; synthetic fixtures only."""
import copy
import gzip
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout, redirect_stderr
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
import numpy as np
from investment import financial_table as ft, auto_refresh as auto, portfolio_risk as pr
from investment import live_dashboard, market_insights, naver_bands, official_statements
from investment import research_agents, research_inbox, telegram_listen, trend_following, weekly_research
from tests import test_auto_refresh as auto_tests, test_financial_table as table_tests
from tests import test_holding_market as holding_tests, test_naver_bands as band_tests
from tests import test_infomax_history as history_tests
from tests.test_official_statements import packet, ROW
from tests.test_portfolio_risk import risk_fixture
from tests.test_telegram_listen import channel_post, fake_fetch
from tools import overlap_coverage_sim, verify_portfolio_data

CUTOFF='2026-06-30'
DAYS=('2026-06-29',CUTOFF,'2026-07-01')


def setUpModule():
    # Helper-created temporary directories also stay inside the scratch tree.
    temp=patch('tempfile.tempdir',str(Path(__file__).resolve().parents[1]))
    temp.start();unittest.addModuleCleanup(temp.stop)
    clock=patch('tools.infomax_daily.datetime')
    frozen=clock.start();unittest.addModuleCleanup(clock.stop)
    frozen.now.return_value=datetime(2026,9,28,9,tzinfo=auto.KST)


def financial_case(**over):
    c=table_tests.FinancialTableTests();c.setUp()
    c.snapshot['meta']['price_date']=CUTOFF
    record=dict(c.period,period_end='2025-12-31',available_at='2026-06-01',revenue=1e8,**over)
    return c,record


def table_for(c,record):return ft.build_table(c.row,c.snapshot,c.source(record))


def bundle(c,record):return {c.row['code']:c.source(record)}


def five_risk():
    _,cache,cutoff=risk_fixture();targets=[]
    for i in range(5):
        code=str(900000+i)
        cache['history']['histories'][code]=copy.deepcopy(cache['history']['histories']['900000'])
        cache['history']['histories'][code]['symbol']=code
        targets.append(dict(code=code,name=code,market='KOSPI',industry='I'+str(i),weight_pct=19))
    return targets,cache,cutoff


@contextmanager
def auto_case():
    # Reuse the existing isolated store fixture, freeze persistence timestamps,
    # and stub only the refresh transaction outside the cache policy under test.
    fixed=datetime(2026,9,28,10,tzinfo=auto.KST)
    with patch('investment.store.datetime') as clock:
        clock.now.return_value=fixed
        c=auto_tests.AutoRefreshTests();c.setUp()
        def refresh(*args,**kwargs):
            snapshot,_,_=c.provider.fetch()
            return dict(snapshot=snapshot,receipt=dict(status='complete',last_success_at=c.time.isoformat()))
        try:
            with patch('investment.refresh.refresh',side_effect=refresh):yield c
        finally:c.doCleanups()


class FinancialBoundaries(unittest.TestCase):
    def test_M031_period_end_cutoff_inclusive(self):
        for day in DAYS:
            c,r=financial_case();r['period_end']=day
            self.assertEqual(bool(table_for(c,r)['groups']),day<=CUTOFF)

    def test_M032_publication_cutoff_inclusive(self):
        for day in DAYS:
            c,r=financial_case();r['available_at']=day
            self.assertEqual(bool(table_for(c,r)['groups']),day<=CUTOFF)

    def test_M033_cell_publication_cutoff_inclusive(self):
        for day in DAYS:
            c,r=financial_case(cell_provenance={'revenue':dict(source='synthetic',available_at=day)})
            value=table_for(c,r)['groups'][0]['columns'][0]['values']['revenue']
            self.assertEqual(value,1 if day<=CUTOFF else None)

    def test_M034_filing_cutoff_inclusive(self):
        for day in DAYS:
            c,r=financial_case(filing_available_at=day,source_url='https://example.test/report',receipt='synthetic')
            col=table_for(c,r)['groups'][0]['columns'][0]
            self.assertEqual(col['filing_available_at'],day if day<=CUTOFF else None)

    def test_M038_merge_period_cutoff_inclusive(self):
        for day in DAYS:
            c,r=financial_case();r.update(period_end=day,available_at=None)
            value=ft.merge_financials(bundle(c,r),{},as_of=CUTOFF)
            self.assertEqual(len(value[c.row['code']]['periods']),int(day<=CUTOFF))

    def test_M039_merge_publication_cutoff_inclusive(self):
        for day in DAYS:
            c,r=financial_case();r['available_at']=day
            value=ft.merge_financials({},bundle(c,r),as_of=CUTOFF)
            self.assertEqual(len(value[c.row['code']]['periods']),int(day<=CUTOFF))

    def test_M040_difference_exactly_100m_is_noted(self):
        for delta in (99_999_999,100_000_000,100_000_001):
            c,r=financial_case()
            value=ft.merge_financials(bundle(c,dict(r,revenue=1e8+delta)),bundle(c,r))
            self.assertEqual('revenue' in value[c.row['code']]['periods'][0]['cell_notes'],delta>=1e8)


class RefreshBoundaries(unittest.TestCase):
    def test_M074_target_date_is_not_stale(self):
        for day in DAYS:
            result=auto.summary(dict(meta={'price_date':day},companies=[]),None,status='cached',
                checked_at=datetime(2026,7,2,tzinfo=auto.KST),target=CUTOFF,calendar_basis='synthetic')
            self.assertEqual(result['stale'],day<CUTOFF)

    def test_M075_cached_price_equals_target(self):
        with auto_case() as c:
            c.snapshot['meta']['fetched_at']=c.time.isoformat();c.store.save_snapshot(c.snapshot)
            with patch('investment.auto_refresh.target_date',return_value=(c.snapshot['meta']['price_date'],'synthetic')):
                self.assertEqual(c.run_refresh()['receipt']['status'],'cached')
            c.provider.fetch.assert_not_called()

    def test_M076_first_cache_expires_at_ttl(self):
        for age in (899,900,901):
            with auto_case() as c:
                c.snapshot['meta']['fetched_at']=(c.time-timedelta(seconds=age)).isoformat();c.store.save_snapshot(c.snapshot)
                result=c.run_refresh()['receipt']
                self.assertEqual(result['status'],'cached' if age<900 else 'complete')
                self.assertEqual(c.provider.fetch.call_count,int(age>=900))

    def test_M077_success_cache_expires_at_ttl(self):
        with auto_case() as c:
            self.assertEqual(c.run_refresh()['receipt']['status'],'complete')
            c.time+=timedelta(seconds=899)
            self.assertEqual(c.run_refresh()['receipt']['status'],'cached')
            c.time+=timedelta(seconds=1)
            self.assertEqual(c.run_refresh()['receipt']['status'],'complete')
            self.assertEqual(c.provider.fetch.call_count,2)

    def test_M078_retry_at_exact_deadline(self):
        with auto_case() as c:
            c.provider.fetch.side_effect=OSError('synthetic')
            self.assertEqual(c.run_refresh()['receipt']['status'],'failed')
            c.time+=timedelta(seconds=59)
            self.assertEqual(c.run_refresh()['receipt']['status'],'retry_wait')
            c.time+=timedelta(seconds=1)
            self.assertEqual(c.run_refresh()['receipt']['status'],'failed')
            self.assertEqual(c.provider.fetch.call_count,2)

    def test_M079_one_second_interval_is_valid(self):
        for seconds in (0,1,2):
            with auto_case() as c:
                c.config['infomax_refresh']['freshness_seconds']=seconds;c.write_config()
                self.assertEqual(c.run_refresh()['receipt']['success'],seconds>=1)
                self.assertEqual(c.provider.fetch.call_count,int(seconds>=1))


class RiskBoundaries(unittest.TestCase):
    def test_M055_minimum_63_returns(self):
        _,cache,cutoff=risk_fixture();h=cache['history']
        for count in (63,64,65):
            result=pr.time_series(h['histories']['900000']['prices'][-count:],h['benchmarks']['KOSPI']['prices'][-count:],cutoff)
            self.assertEqual(result['status'],'ready' if count>=64 else 'pending')

    def test_M056_five_positions_allowed(self):
        targets,cache,cutoff=five_risk()
        self.assertEqual(pr.portfolio_risk(targets,5,cache,cutoff)['status'],'ready')
        self.assertEqual(pr.portfolio_risk(targets[:4],24,cache,cutoff)['status'],'ready')
        targets.append(dict(targets[0],code='900005'))
        self.assertEqual(pr.portfolio_risk(targets,5,cache,cutoff)['status'],'pending')

    def test_M060_exact_position_policy_limit(self):
        targets,cache,cutoff=five_risk()
        for limit in (4,5):
            policy=dict(state='USER_CONFIRMED',effective_on='2020-01-01',provenance='synthetic',max_positions=limit,max_position_pct=40,min_cash_pct=5)
            value=pr.compare_portfolios(dict(targets=targets,cash_pct=5,created_on=cutoff),None,cache,cutoff,policy)
            self.assertEqual('max_positions' in value['policy_violations'],limit<5)


class OtherBoundaries(unittest.TestCase):
    def test_M134_quote_cache_expires_at_300_seconds(self):
        c=holding_tests.HoldingMarketTests();c.setUp()
        record=dict(symbol='005010',kind='item',prices=[dict(date='2026-09-30',close=120,final=True,venue='KRX',adjustment_basis='naver_chart_adjusted')])
        fetcher=Mock(return_value=record)
        with tempfile.TemporaryDirectory() as tmp,patch('investment.holding_market.time.monotonic',return_value=100) as clock:
            service=c.service(tmp,fetcher)
            self.assertEqual(service.lookup('005010')['row']['price_krw'],120)
            clock.return_value=399;service.lookup('005010');self.assertEqual(fetcher.call_count,1)
            clock.return_value=400;service.lookup('005010');self.assertEqual(fetcher.call_count,2)

    def test_M139_compress_only_above_1024_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            handler=live_dashboard.handler_for(Path(tmp),token='synthetic',read_only=True,report_inbox=Mock())
            for size in (1023,1024,1025):
                out=Mock();out.headers={'Accept-Encoding':'gzip'};out.wfile=io.BytesIO()
                handler.send_body(out,200,'x'*size,'text/plain')
                compressed=('Content-Encoding','gzip') in [call.args for call in out.send_header.call_args_list]
                self.assertEqual(compressed,size>1024)
                body=out.wfile.getvalue()
                self.assertEqual(gzip.decompress(body) if compressed else body,b'x'*size)

    def test_M143_five_observations_enable_percentile(self):
        self.assertIsNone(market_insights.percentile(3,[1,2,3,4]))
        self.assertEqual(market_insights.percentile(3,[1,2,3,4,5]),50)
        self.assertAlmostEqual(market_insights.percentile(3,[1,2,3,4,5,6]),100*2.5/6)

    def test_M147_zero_band_is_preserved(self):
        for amount in (-1,0,1):
            raw=band_tests.BandTests().raw();raw['bandChart1']['val1'][0]['y']=amount
            if amount<0:
                with self.assertRaises(ValueError):naver_bands.parse_bands(raw,'000660','CFS','2026-10-19T16:00:00+09:00')
            else:
                value=naver_bands.parse_bands(raw,'000660','CFS','2026-10-19T16:00:00+09:00')
                self.assertEqual(value['bands']['per']['rows'][0]['values']['band1'],amount)

    def test_M152_single_page_official_document(self):
        for pages in (0,1,2):
            data=packet();data['document']['pages']=pages
            for cell in data['reports'][0]['cells'].values():cell['page']=1
            if pages==0:
                with self.assertRaises(ValueError):official_statements.validate_packet(data,ROW)
            else:
                result=official_statements.validate_packet(data,ROW)
                self.assertEqual(result['document']['pages'],pages)
                self.assertEqual(result['reports'][0]['values']['revenue'],100)

    def test_M157_twenty_review_issues_allowed(self):
        for count in (19,20,21):
            value=dict(verdict='revise',summary='synthetic',issues=['x']*count)
            if count>20:
                with self.assertRaises(ValueError):research_agents.validate_review(value)
            else:self.assertEqual(research_agents.validate_review(value),value)

    def test_M161_exact_metadata_byte_limit(self):
        value={'x':'한'};size=len(json.dumps(value,ensure_ascii=False,indent=2).encode())
        for limit in (size-1,size,size+1):
            with tempfile.TemporaryDirectory() as tmp,patch('investment.research_inbox.LIMIT',limit):
                path=Path(tmp)/'metadata.json'
                if limit<size:
                    with self.assertRaises(ValueError):research_inbox.write(path,value)
                    self.assertFalse(path.exists())
                else:
                    research_inbox.write(path,value)
                    self.assertEqual(json.loads(path.read_text(encoding='utf-8')),value)

    def test_M166_two_hundred_updates_persist_offset(self):
        for count in (199,200,201):
            with tempfile.TemporaryDirectory() as tmp:
                state=Path(tmp)/'state.json';out=Path(tmp)/'out'
                channel=dict(key='c1',expected_name='Synthetic channel',expected_id=-1001234567890)
                fetch=fake_fetch([[channel_post(update_id=i,message_id=i) for i in range(1,count+1)]])
                args=('synthetic',channel,state,out)
                kwargs=dict(fetch=fetch,now=datetime(2026,1,2,tzinfo=timezone.utc))
                if count>200:
                    with self.assertRaises(ValueError):telegram_listen.poll(*args,**kwargs)
                    self.assertFalse(state.exists())
                else:
                    result=telegram_listen.poll(*args,**kwargs)
                    self.assertEqual(result['counts']['accepted'],count)
                    self.assertEqual(json.loads(state.read_text())['last_update_id'],count)

    def test_M173_zero_volume_is_preserved(self):
        for volume in (-1,0,1):
            result=trend_following.chart_series([dict(date='2026-10-02',close=100,volume=volume)])
            self.assertEqual(result[0]['volume'],volume if volume>=0 else None)

    def test_M177_exact_markdown_byte_limit(self):
        for size in (1_999_999,2_000_000,2_000_001):
            raw=b'x'*size;value=dict(research_date='2026-11-02',markdown_sha256=hashlib.sha256(raw).hexdigest(),records=[])
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/'weekly.md';p.write_bytes(raw)
                q=Path(tmp)/'manifest.json';q.write_text(json.dumps(value),encoding='utf-8')
                if size>2_000_000:
                    with self.assertRaises(ValueError):weekly_research.read_bundle(p,q)
                else:self.assertEqual(weekly_research.read_bundle(p,q),value)

    def test_M181_zero_average_parent_equity_rejected(self):
        # Import via the same script path helper used by the existing test.
        from tests import test_company_finish
        import company_finish as finish
        info={'000001':{'name':'synthetic'}}
        parsed={kind:{'000001':{day:{field:10 for field in fields} for day in
            (finish.QUARTERS if kind=='income-extra' else finish.BALANCE_DATES)}} for kind,fields in finish.EXTRAS.items()}
        with tempfile.TemporaryDirectory() as tmp,patch.object(finish,'HERE',Path(tmp)), \
             patch.object(finish,'read_grid',return_value=([],{})),patch.object(finish,'parse_info',return_value=info), \
             patch.object(finish,'parse_extra',side_effect=[parsed[k] for k in finish.EXTRAS]):
            with self.assertRaisesRegex(ValueError,'Non-positive average parent equity'):finish.collect_extra()

    def test_M189_exactly_24_consecutive_quarters(self):
        for count in (23,24,25):
            c=history_tests.HistoryTests();c.setUp()
            source=c.accounts['900001'];days=sorted(d for d in source if d<='2025-12-31')[-count:]
            c.accounts['900001']={day:source[day] for day in days}
            c.base['meta']['financial_period']='2025-12-31'
            c.base['companies'][0]['quarters']=[q for q in c.base['companies'][0]['quarters'] if q['period_end']<='2025-12-31']
            if count<24:
                with self.assertRaisesRegex(ValueError,'24'):c.build()
            else:self.assertEqual(len(c.build()['companies'][0]['observed_financial_history']['quarters']),count)

    def test_M194_two_nonoverlap_samples_are_pending(self):
        for count in (2,4,6):
            result=overlap_coverage_sim.intervals(np.arange(1.,count+1),2,50,np.random.default_rng(1))
            self.assertEqual(np.isnan(result['nonoverlap'][1]),count<=4)

    def test_M200_exact_30_mib_input_is_accepted(self):
        # Exercise CLI file parsing; the unrelated Node-backed verifier is replaced.
        size=30*1024*1024
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'snapshot.json';path.write_bytes(b'{}'+b' '*(size-2))
            args=['verify_portfolio_data','--snapshot',str(path),'--as-of','2026-10-02']
            with patch('sys.argv',args),patch.object(verify_portfolio_data,'verify',return_value={'valid':True}) as verify,redirect_stdout(io.StringIO()) as out:
                verify_portfolio_data.main()
            self.assertEqual(json.loads(out.getvalue()),{'valid':True,'event_cache_connected':False})
            verify.assert_called_once_with({},None,None,'2026-10-02',None)
            with path.open('ab') as stream:stream.write(b' ')
            with patch('sys.argv',args),patch.object(verify_portfolio_data,'verify') as verify,redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:verify_portfolio_data.main()
            self.assertEqual(error.exception.code,1);verify.assert_not_called()


if __name__=='__main__':unittest.main()
