import base64,json,os,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from investment.report_inbox import ReportInbox
from investment.company_reports import listing,register


class ReportInboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.cfg=dict(profile='work',data_dir=self.root/'data',goose_report_inbox=str(self.root/'inbox'))
        def identity(root,code):
            if code not in ('900001','900002'):raise ValueError('저장된 기업을 선택하세요.')
            return self.cfg,dict(code=code,name='가상'+code,market='KOSPI')
        for target,value in [('investment.report_inbox.load_local',lambda root:self.cfg),('investment.report_inbox.company',identity),('investment.company_reports.company',identity)]:
            p=patch(target,side_effect=value);p.start();self.addCleanup(p.stop)
        self.inbox=ReportInbox(self.root);self.inbox.folder.mkdir()
    def html(self,code='900001',name=None,day='2026-01-01',suffix=''):
        data=dict(company=dict(ticker=code,name=name or '가상'+code),as_of=day,status='limited',sources=[])
        encoded=base64.b64encode(json.dumps(data).encode()).decode()
        return f'<h1>가상 보고서{suffix}</h1><a download="report-input.json" href="data:application/json;base64,{encoded}">data</a>'
    def put(self,name='arbitrary.html',html=None):
        p=self.inbox.folder/name;p.write_text(html or self.html(),encoding='utf-8');os.utime(p,(1,1));return p
    def finish(self):self.inbox.scan();return self.inbox.scan()
    def test_stable_file_goes_to_its_company_not_filename(self):
        path=self.put('삼성전자-005930.html')
        self.assertEqual(self.inbox.scan()['files'][0]['status'],'waiting');self.assertEqual(listing(self.root,'900001')['reports'],[])
        view=self.inbox.scan();self.assertEqual(view['files'][0]['status'],'registered');self.assertEqual(len(listing(self.root,'900001')['reports']),1)
        self.assertEqual(listing(self.root,'900002')['reports'],[]);self.assertTrue(path.exists())
    def test_same_content_deduplicates_existing_manual_and_renamed_files(self):
        html=self.html();register(self.root,dict(code='900001',title='수동 제목',authored_on='2026-01-01',source_label='GOOSE',source_urls=[],filename='manual.html',html=html))
        self.put('one.html',html);self.put('two.html',html);view=self.finish()
        self.assertTrue(all(f['status']=='duplicate' for f in view['files']));self.assertEqual(len(listing(self.root,'900001')['reports']),1)
        fresh=ReportInbox(self.root);fresh.scan();self.assertEqual(len(listing(self.root,'900001')['reports']),1)
    def test_windows_line_endings_and_bom_do_not_make_a_new_version(self):
        html=self.html()+'\n<p>line</p>\n'
        register(self.root,dict(code='900001',title='수동 제목',authored_on='2026-01-01',source_label='GOOSE',source_urls=[],filename='manual.html',html=html))
        path=self.inbox.folder/'windows.html';path.write_bytes(('\ufeff'+html.replace('\n','\r\n')).encode('utf-8'));os.utime(path,(1,1))
        self.assertEqual(self.finish()['files'][0]['status'],'duplicate');self.assertEqual(len(listing(self.root,'900001')['reports']),1)
    def test_changed_report_keeps_versions_and_matches_two_companies(self):
        path=self.put();self.finish();path.write_text(self.html(suffix='수정'),encoding='utf-8');os.utime(path,(2,2));self.finish()
        self.put('second.htm',self.html('900002'));self.finish()
        self.assertEqual(len(listing(self.root,'900001')['reports']),2);self.assertEqual(len(listing(self.root,'900002')['reports']),1)
    def test_unidentified_mismatched_unknown_future_and_invalid_files_preserved(self):
        values=['<h1>900001</h1>',self.html(name='다른회사'),self.html(code='999999'),self.html(day='2099-01-01')]
        for i,html in enumerate(values):self.put(f'bad{i}.html',html)
        invalid=self.inbox.folder/'invalid.html';invalid.write_bytes(b'\xff');os.utime(invalid,(1,1))
        view=self.finish();self.assertEqual(len(view['files']),5);self.assertTrue(all(f['status']=='error' for f in view['files']));self.assertTrue(all((self.inbox.folder/f['filename']).exists() for f in view['files']))
        self.assertEqual(listing(self.root,'900001')['reports'],[])
    def test_partial_file_retries_after_new_save_and_ignores_other_extensions(self):
        path=self.put(html='<h1>partial</h1>');self.finish();self.assertEqual(self.inbox.view()['files'][0]['status'],'error')
        path.write_text(self.html(),encoding='utf-8');os.utime(path,(2,2));self.put('unfinished.crdownload');self.finish()
        self.assertEqual(len(listing(self.root,'900001')['reports']),1);self.assertEqual(len(self.inbox.view()['files']),1)
    def test_read_only_and_pause_do_not_create_or_import(self):
        self.cfg['goose_report_inbox']=str(self.root/'readonly-folder');other=ReportInbox(self.root,read_only=True)
        other.start();self.assertFalse(other.folder.exists());self.assertFalse(other.view()['enabled'])
        with self.assertRaises(ValueError):other.scan()
        self.put();self.inbox.pause();self.inbox.scan();self.assertEqual(listing(self.root,'900001')['reports'],[])
    def test_background_lifecycle(self):
        event=threading.Event()
        with patch('investment.dashboard_build.source_fingerprint',return_value='test'),patch.object(self.inbox,'scan',side_effect=event.set):
            self.inbox.start();self.assertTrue(event.wait(2));self.inbox.stop();self.assertFalse(self.inbox.thread.is_alive())
    def test_authenticated_inbox_route_read_only_post_refused(self):
        from http.server import ThreadingHTTPServer
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        from investment.live_dashboard import handler_for
        root=Path(__file__).resolve().parents[1]
        for readonly in (False,True):
            service=ReportInbox(self.root,read_only=readonly)
            server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(root,token='test-inbox-token',read_only=readonly,report_inbox=service));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
            try:
                with self.assertRaises(HTTPError):urlopen(base+'/report-inbox')
                request=Request(base+'/report-inbox',headers={'X-Dashboard-Token':'test-inbox-token'})
                with urlopen(request) as response:self.assertEqual(json.load(response)['enabled'],not readonly)
                request=Request(base+'/report-inbox',data=b'',headers={'X-Dashboard-Token':'test-inbox-token','Origin':base})
                if readonly:
                    with self.assertRaises(HTTPError) as e:urlopen(request)
                    self.assertEqual(e.exception.code,403)
                else:
                    with urlopen(request) as response:self.assertEqual(response.status,200)
            finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
