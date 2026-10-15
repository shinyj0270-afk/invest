"""Versioned delivery and cooperative restart; fixtures only, no process termination."""
import json
import tempfile
import threading
import unittest
import time
from pathlib import Path
from http.server import HTTPServer,ThreadingHTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from unittest.mock import patch,MagicMock
from investment.fixture import make_fixture
from investment.live_dashboard import handler_for,dashboard_input_version
from investment.workspace_export import export_workspace


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.data=self.root/'data/unknown';self.data.mkdir(parents=True)
        self.snapshot=make_fixture()

    def tearDown(self):self.temp.cleanup()

    def start(self,**kwargs):
        server_class=kwargs.pop('server_class',HTTPServer)
        self.server=server_class(('127.0.0.1',0),handler_for(self.root,token='test-token',refresh=lambda root,**kw:dict(snapshot=self.snapshot,receipt={}),**kwargs))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.addCleanup(self.stop)

    def stop(self):self.server.shutdown();self.server.server_close();self.thread.join(2)

    def get(self,path,auth=True):return urlopen(Request(self.base+path,headers={'X-Dashboard-Token':'test-token'} if auth else {}))

    def post(self,value,auth=True):return urlopen(Request(self.base+'/restart',data=json.dumps(value).encode(),headers={'Origin':self.base,'Content-Type':'application/json',**({'X-Dashboard-Token':'test-token'} if auth else {})}))

    def test_versioned_cache_and_lazy_auth_invalidation(self):
        calls=[]
        def export(snapshot,**kwargs):
            calls.append(kwargs['live']);kwargs['section_sink']('trend-following',{'rows':[{'code':'900000'}]});return 'fixture'
        with patch('investment.live_dashboard.export_workspace',side_effect=export):
            self.start()
            self.assertEqual(self.get('/dashboard').read(),b'fixture');self.get('/dashboard').close()
            self.assertEqual(len(calls),1)
            endpoint='/dashboard-section?section=trend-following&version='+calls[0]['section_version']
            with self.assertRaises(HTTPError) as error:self.get(endpoint,False)
            self.assertEqual(error.exception.code,403)
            self.assertEqual(json.load(self.get(endpoint))['trend_following']['rows'][0]['code'],'900000')
            wal=self.data/'research.sqlite3-wal';wal.write_bytes(b'changed')
            self.assertEqual(json.load(self.get(endpoint))['trend_following']['rows'][0]['code'],'900000')
            self.get('/dashboard').close();self.assertEqual(len(calls),2)
            wal.unlink();self.get('/dashboard').close();self.assertEqual(len(calls),3)

    def test_company_read_does_not_queue_behind_whole_dashboard_build(self):
        entered=threading.Event();release=threading.Event();errors=[]
        def slow_export(*args,**kwargs):
            entered.set();release.wait(5);return 'fixture'
        def build():
            try:self.get('/dashboard').close()
            except Exception as exc:errors.append(type(exc).__name__)
        with patch('investment.live_dashboard.export_workspace',side_effect=slow_export):
            self.start(server_class=ThreadingHTTPServer)
            thread=threading.Thread(target=build);thread.start()
            try:
                self.assertTrue(entered.wait(2))
                request=Request(self.base+'/company-view?code=900001',headers={'X-Dashboard-Token':'test-token'})
                with urlopen(request,timeout=1) as response:
                    self.assertEqual(json.load(response)['code'],'900001')
            finally:release.set();thread.join(3)
        self.assertFalse(errors)

    def test_restart_preserves_active_company_read(self):
        entered=threading.Event();release=threading.Event()
        from investment.financial_table import build_table
        def slow_table(*args,**kwargs):
            entered.set();release.wait(5);return build_table(*args,**kwargs)
        with patch('investment.live_dashboard.build_table',side_effect=slow_table):
            self.start(server_class=ThreadingHTTPServer)
            thread=threading.Thread(target=lambda:self.get('/company-view?code=900001').close())
            thread.start()
            try:
                self.assertTrue(entered.wait(2))
                with self.assertRaises(HTTPError) as error:self.post({'drafts_saved':True})
                self.assertEqual(error.exception.code,409)
                self.assertIn('기업 자료 조회',error.exception.read().decode())
            finally:release.set();thread.join(3)
        self.assertFalse(thread.is_alive())

    def test_inputs_changed_during_export_never_cached(self):
        def export(snapshot,**kwargs):
            p=self.data/'version.json';p.write_text(str(p.stat().st_size) if p.exists() else 'changed')
            return 'fixture'
        with patch('investment.live_dashboard.export_workspace',side_effect=export) as build:
            self.start();self.get('/dashboard').close();self.get('/dashboard').close()
            self.assertEqual(build.call_count,2)

    def test_external_financial_companion_appearance_invalidates_version(self):
        external=self.root/'outside';external.mkdir()
        (self.root/'config').mkdir()
        (self.root/'config/local.json').write_text(json.dumps({'manual_snapshot_file':str(external/'manual.json')}))
        before=dashboard_input_version(self.root)
        (external/'income.xlsx').write_bytes(b'new financial input')
        self.assertNotEqual(before,dashboard_input_version(self.root))

    def test_in_memory_financial_revision_invalidates_cache(self):
        monitor=MagicMock();monitor.poll.return_value={'revision':'first','versions':{}}
        with patch('investment.live_dashboard.export_workspace',return_value='fixture') as build:
            self.start(financial_monitor=monitor);self.get('/dashboard').close();self.get('/dashboard').close()
            self.assertEqual(build.call_count,1)
            monitor.poll.return_value={'revision':'second','versions':{}}
            self.get('/dashboard').close();self.assertEqual(build.call_count,2)

    def test_read_only_recovery_never_advertises_retry_even_with_services(self):
        daily=MagicMock();financial=MagicMock()
        cache={'universe':{'companies':[{'code':'005930','name':'Fixture','eligibility':'candidate'}]},'history':{'errors':[{'code':'005930','reason':'Fixture failure'}]}}
        with patch('investment.data_recovery.read_market_cache',return_value=cache):
            self.start(daily=daily,financial=financial,read_only=True)
            state=json.load(self.get('/data-recovery'))
            self.assertFalse(state['failures'][0]['can_retry']);daily.poll.assert_not_called()
            request=Request(self.base+'/data-recovery',data=b'{"kind":"price","code":"005930"}',headers={'Origin':self.base,'X-Dashboard-Token':'test-token'})
            with self.assertRaises(HTTPError) as error:urlopen(request)
            self.assertEqual(error.exception.code,403);daily.start.assert_not_called()

    def test_lazy_rows_preserve_home_model_and_static_export(self):
        full={'rows':[{'code':'900000','technical':{'series':[]}}],'markets':[{'market':'KOSPI'}],'as_of':'2026-10-12'}
        sections={};html=export_workspace(self.snapshot,live={'lazy_company_views':True,'lazy_holdings_frame':True},trend_following_data=full,section_sink=lambda key,value:sections.update({key:value}))
        payload=json.JSONDecoder().raw_decode(html.split('const WORKSPACE_DATA=',1)[1])[0]
        self.assertEqual(payload['trend_following']['rows'],[])
        self.assertEqual(payload['trend_following']['markets'],full['markets'])
        self.assertEqual(sections['trend-following'],full);self.assertEqual(len(full['rows']),1)

    def test_restart_requires_auth_saved_drafts_and_idle_collectors(self):
        daily=MagicMock();daily.poll.return_value={'status':'running'}
        self.start(daily=daily)
        for payload,auth,status in [({'drafts_saved':True},False,403),({},True,409),({'drafts_saved':True},True,409)]:
            with self.assertRaises(HTTPError) as error:self.post(payload,auth)
            self.assertEqual(error.exception.code,status)
        self.assertIn('draftsSaved',self.get('/restart').read().decode())

    def test_restart_rejects_cross_process_collection_lock(self):
        from investment.company_financials import acquire_lock
        lock=acquire_lock(self.data/'collection.lock')
        try:
            self.start()
            with self.assertRaises(HTTPError) as error:self.post({'drafts_saved':True})
            self.assertEqual(error.exception.code,409)
        finally:lock.close()

    def test_restart_cooperatively_stops_only_own_server_then_launches_same_port(self):
        self.start()
        marker=self.data/'input.json';marker.write_text('preserved')
        with patch('subprocess.Popen') as launch:
            response=self.post({'drafts_saved':True});self.assertEqual(response.status,202)
            for _ in range(100):
                if launch.called:break
                time.sleep(.02)
            self.assertTrue(launch.called);self.assertEqual(launch.call_count,1)
            command=launch.call_args.args[0]
            self.assertIn(str(self.root/'tools/open_dashboard.py'),command)
            self.assertEqual(command[-2:],['--port',str(self.server.server_port)])
            self.assertIn('--no-browser',command)
            self.assertEqual(marker.read_text(),'preserved');self.assertFalse(self.thread.is_alive())

    def test_launcher_opens_explicit_confirmation_without_stopping_existing_server(self):
        from tools import open_dashboard as launcher
        identity=launcher.build_identity(launcher.ROOT)
        with patch('sys.argv',['open_dashboard.py']),patch.object(launcher,'health',return_value=False),patch.object(launcher,'server_identity',return_value={**identity,'restart_required':True}),patch('socket.socket') as socket,patch('webbrowser.open') as browser,patch('subprocess.Popen') as launch:
            socket.return_value.__enter__.return_value.connect_ex.return_value=0
            launcher.main();browser.assert_called_once_with('http://127.0.0.1:8767/restart');launch.assert_not_called()


if __name__=='__main__':unittest.main()
