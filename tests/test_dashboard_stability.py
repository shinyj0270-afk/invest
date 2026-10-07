"""Synthetic stability contracts; no real data, process termination, or collection."""
import copy
import io
import json
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import HTTPServer
from zoneinfo import ZoneInfo

from investment.dashboard_build import source_fingerprint, build_identity
from investment.financial_table import merge_financials, build_table
from investment.fixture import make_fixture
from investment.live_dashboard import handler_for, public_receipt, daily_status
from investment.market_history import DAILY_PUBLICATION_TIME, completed_cutoff
from investment.workspace_export import export_workspace
from tools import open_dashboard as launcher


def record(*periods, **extra):
    return dict(code='900000',name='가상기업',market='KOSPI',notes=[],periods=list(periods),**extra)


def period(**extra):
    return dict(period_end='2026-06-30',basis='CFS',cadence='quarter',**extra)


class FinancialMergeStabilityTests(unittest.TestCase):
    def merge(self,p,o,as_of='2026-10-07'):
        return merge_financials({'900000':p},{'900000':o},as_of=as_of)['900000']

    def test_missing_account_zero_provider_and_provenance(self):
        p=record(period(available_at=None,revenue=0,source='인포맥스'))
        o=record(period(available_at='2026-08-14',revenue=20e8,balance_debt=30e8,source='DART'),collection_health={'status':'ready'})
        before=copy.deepcopy((p,o));r=self.merge(p,o);c=r['periods'][0]
        self.assertEqual(c['revenue'],0);self.assertEqual(c['balance_debt'],30e8)
        self.assertEqual(c['cell_provenance']['balance_debt']['available_at'],'2026-08-14')
        self.assertIsNone(c['cell_provenance']['revenue']['available_at'])
        self.assertEqual(r['collection_health'],{'status':'ready'});self.assertEqual((p,o),before)

    def test_future_official_period_does_not_leak_through_unknown_provider_date(self):
        r=self.merge(record(period(available_at=None,revenue=10,source='인포맥스')),
            record(period(available_at='2026-10-08',balance_debt=99,source='DART')))
        self.assertNotIn('balance_debt',r['periods'][0]);self.assertEqual(r['periods'][0]['revenue'],10)

    def test_future_individual_cell_is_withheld(self):
        o=record(period(available_at='2026-08-14',balance_debt=99,source='DART',
            cell_provenance={'balance_debt':{'available_at':'2026-10-08','source':'DART'}}))
        self.assertIsNone(self.merge(record(period(available_at=None,revenue=10)),o)['periods'][0].get('balance_debt'))

    def test_unknown_official_publication_is_not_past_evidence(self):
        r=self.merge(record(period(available_at=None,revenue=10)),record(period(available_at=None,balance_debt=99,source='DART')))
        self.assertNotIn('balance_debt',r['periods'][0])

    def test_earlier_view_cutoff_rechecks_each_merged_cell(self):
        snapshot=make_fixture();row=snapshot['companies'][0]
        row.update(code='900000',name='가상기업',market='KOSPI',annual=[],quarters=[])
        merged=self.merge(record(period(available_at=None,revenue=0,source='인포맥스')),
            record(period(available_at='2026-10-03',balance_debt=99e8,source='DART')))
        table=build_table(row,snapshot,merged)
        column=table['groups'][0]['columns'][0]
        self.assertEqual(column['statement_values']['revenue'],0)
        self.assertIsNone(column['statement_values']['balance_debt'])
        self.assertNotIn('balance_debt',column['cell_provenance'])
        self.assertIsNone(column['filing_available_at'])
        self.assertIsNone(column['cell_provenance']['revenue']['available_at'])

    def test_identity_and_currency_fiscal_boundaries(self):
        p=record(period(available_at=None,revenue=10,source='인포맥스'))
        for extra in ({'native_currency':'USD'},{'period_start':'2026-04-01'},{'fiscal_segment':'FY26Q2'}):
            o=record(period(available_at='2026-08-14',balance_debt=99,**extra))
            self.assertNotIn('balance_debt',self.merge(p,o)['periods'][0])
        o=record(period(available_at='2026-08-14',balance_debt=99));o['name']='다른 기업'
        self.assertNotIn('balance_debt',self.merge(p,o)['periods'][0])

    def test_duplicate_in_either_source_fails_closed(self):
        p=period(available_at=None,revenue=10);o=period(available_at='2026-08-14',balance_debt=99)
        for a,b in ((record(p,p),record(o)),(record(p),record(o,o))):
            r=self.merge(a,b);self.assertEqual(r['periods'],[]);self.assertTrue(r['merge_rejected'])

    def test_eps_has_own_tolerance_and_merging_is_idempotent(self):
        p=record(period(available_at=None,eps=1200,revenue=1e9,source='인포맥스'))
        o=record(period(available_at='2026-08-14',eps=1100,revenue=1e9+99e6,balance_debt=99,source='DART'))
        first=self.merge(p,o);self.assertIn('EPS',first['periods'][0]['cell_notes']['eps'])
        self.assertNotIn('revenue',first['periods'][0]['cell_notes'])
        self.assertEqual(self.merge(p,first),first)


class ServerBuildStabilityTests(unittest.TestCase):
    def test_all_three_live_paths_use_cutoff_checked_account_merge(self):
        snapshot=make_fixture();row=snapshot['companies'][0]
        row.update(annual=[],quarters=[])
        provider={row['code']:dict(code=row['code'],name=row['name'],market=row['market'],notes=[],
            periods=[period(available_at=None,revenue=10,source='인포맥스')])}
        official={row['code']:dict(code=row['code'],name=row['name'],market=row['market'],notes=[],
            periods=[period(available_at='2026-08-14',balance_debt=99,source='DART')])}
        from unittest.mock import MagicMock
        book=MagicMock();book.view.return_value={'records':[]}
        with patch('investment.live_dashboard.load_market_cache',return_value={}), \
             patch('investment.live_dashboard.load_local_financials',return_value=provider), \
             patch('investment.live_dashboard.load_company_financials',return_value=official), \
             patch('investment.live_dashboard.export_workspace',return_value='synthetic root'), \
             patch('investment.live_dashboard.merge_financials',wraps=merge_financials) as merge, \
             patch('investment.recommendations.RecommendationBook',return_value=book), \
             patch('investment.recommendations.research_context',return_value={}) as context:
            server=HTTPServer(('127.0.0.1',0),handler_for('.',refresh=lambda root:dict(snapshot=snapshot,receipt={}),token='synthetic',financial=object()))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}';headers={'X-Dashboard-Token':'synthetic','Origin':base,'Content-Type':'application/json'}
            try:
                urlopen(base+'/dashboard').read()
                data=json.load(urlopen(Request(base+'/company-view?code='+row['code'],headers=headers)))
                column=data['table']['groups'][0]['columns'][0]
                self.assertEqual(column['statement_values']['balance_debt'],99/1e8)
                json.load(urlopen(Request(base+'/recommendations',data=b'{"kind":"monthly"}',headers=headers)))
                self.assertEqual(merge.call_count,3)
                self.assertTrue(all(call.kwargs.get('as_of') for call in merge.call_args_list))
                finances=context.call_args.args[2]
                self.assertEqual(finances[row['code']]['periods'][0]['balance_debt'],99)
            finally:server.shutdown();server.server_close();thread.join(2)

    def test_fingerprint_tracks_source_not_private_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'src').mkdir();(root/'data').mkdir()
            ui=root/'src/workspace.js';ui.write_text('v1');before=source_fingerprint(root)
            (root/'data/private.json').write_text('private');self.assertEqual(source_fingerprint(root),before)
            ui.write_text('v2');self.assertNotEqual(source_fingerprint(root),before)

    def test_v1_and_changed_build_never_reused(self):
        expected=build_identity(launcher.ROOT)
        for value in ({**expected,'version':1},{**expected,'build_id':'old'},{**expected,'restart_required':True}):
            with patch.object(launcher,'urlopen',return_value=io.BytesIO(json.dumps(value).encode())):
                self.assertFalse(launcher.health(8767))

    def test_new_ui_with_old_python_refused_before_export_and_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'src').mkdir();ui=root/'src/workspace.js';ui.write_text('old')
            snapshot=make_fixture();calls=[]
            def refresh(root,force=False):calls.append(force);return dict(snapshot=snapshot,receipt={})
            server=HTTPServer(('127.0.0.1',0),handler_for(root,refresh=refresh,token='synthetic'))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            try:
                loaded=json.load(urlopen(base+'/health'));ui.write_text('new TrendFollowingUI dependency')
                health=json.load(urlopen(base+'/health'));self.assertEqual(health['build_id'],loaded['build_id'])
                self.assertNotEqual(health['build_id'],health['source_build_id']);self.assertTrue(health['restart_required'])
                with self.assertRaises(HTTPError) as caught:urlopen(base+'/')
                self.assertEqual(caught.exception.code,503);self.assertIn('open-investment.cmd',caught.exception.read().decode())
                with self.assertRaises(HTTPError) as caught:urlopen(Request(base+'/refresh',data=b'',headers={'Origin':base,'X-Dashboard-Token':'synthetic'}))
                self.assertEqual(caught.exception.code,503);self.assertEqual(calls,[])
            finally:server.shutdown();server.server_close();thread.join(2)

    def test_holdings_frame_requires_auth_and_preserves_contract(self):
        snapshot=make_fixture();snapshot['meta']['data_mode']='user_input'
        server=HTTPServer(('127.0.0.1',0),handler_for('.',refresh=lambda root:dict(snapshot=snapshot,receipt={}),token='synthetic'))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with self.assertRaises(HTTPError) as caught:urlopen(base+'/holdings-frame')
            self.assertEqual(caught.exception.code,403)
            text=urlopen(Request(base+'/holdings-frame',headers={'X-Dashboard-Token':'synthetic'})).read().decode()
            self.assertIn('INVESTMENT_GET_HOLDINGS',text);self.assertIn('INVESTMENT_RESTORE_DRAFT',text)
        finally:server.shutdown();server.server_close();thread.join(2)

    def test_public_errors_and_retry_are_actionable_without_credentials(self):
        value=public_receipt({'error':'https://provider.example/?token=secret'})
        self.assertNotIn('secret',value['error']);self.assertIn('다시 시도',value['error'])
        import time
        class Service:
            last_attempt=time.monotonic()
            def poll(self):return {'status':'failed'}
        self.assertIn('next_retry_at',daily_status(Service()))

    def test_one_cutoff_contract_in_export_and_calculation(self):
        self.assertEqual(DAILY_PUBLICATION_TIME,(20,30))
        kst=ZoneInfo('Asia/Seoul')
        self.assertEqual(str(completed_cutoff(datetime(2026,10,7,20,29,tzinfo=kst),True)),'2026-10-06')
        self.assertEqual(str(completed_cutoff(datetime(2026,10,7,20,30,tzinfo=kst),True)),'2026-10-07')
        html=export_workspace(make_fixture());self.assertNotIn('18:30',html)
        self.assertIn('"same_day_after":"20:30"',html)


if __name__=='__main__':unittest.main()
