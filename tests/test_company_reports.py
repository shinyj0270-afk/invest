import base64,json,sqlite3,tempfile,threading,unittest
from contextlib import closing
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from unittest.mock import patch
from investment.company_reports import register,listing,read,location,embedded

class CompanyReportsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.cfg={'data_dir':self.root/'data','profile':'work'}
        self.identity=lambda root,code:(self.cfg,dict(code=code,name='가상'+code,market='KOSPI'))
        self.patcher=patch('investment.company_reports.company',side_effect=self.identity);self.patcher.start();self.addCleanup(self.patcher.stop)
        self.payload=dict(code='900001',title='가상 보고서',authored_on='2026-01-01',source_label='가상 작성자',source_urls=['https://example.com/report'],filename='report.html',html='<h1>내용</h1>')
    def test_register_reopen_dedup_and_company_isolation(self):
        self.assertEqual(listing(self.root,'900001')['reports'],[]);self.assertFalse(location(self.cfg).exists())
        result=register(self.root,self.payload);self.assertFalse(result['duplicate'])
        self.assertNotIn('html',result['reports'][0]);self.assertEqual(len(listing(self.root,'900002')['reports']),0)
        self.assertTrue(register(self.root,self.payload)['duplicate'])
        with self.assertRaises(ValueError):read(self.root,'900002',result['id'])
        view=read(self.root,'900001',result['id']);self.assertIn('<h1>내용</h1>',view['document'])
        self.assertEqual(view['report']['source_urls'],['https://example.com/report'])
    def test_invalid_metadata_and_file_boundaries(self):
        for key,value in [('authored_on','2099-01-01'),('source_urls',['javascript:alert(1)']),('filename','../escape.html'),('html','x'* (3*1024*1024+1)),('title','')]:
            with self.subTest(key=key),self.assertRaises(ValueError):register(self.root,{**self.payload,key:value})
    def test_static_view_blocks_scripts_navigation_network_and_checks_hash(self):
        self.payload['html']="""<base href="https://example.com"><meta http-equiv="refresh" content="0;url=https://example.com"><script>parent.pwned=1</script><form><input value="secret"></form><iframe src="https://example.com"></iframe><a href="javascript:alert(1)" onclick="alert(1)">外部</a><img src="https://example.com/track"><svg viewBox="0 0 10 10"><rect width="10" height="5"/></svg>"""
        result=register(self.root,self.payload);doc=read(self.root,'900001',result['id'])['document']
        for marker in ['<script','<iframe','<form','onclick','javascript:','https://example.com/track','http-equiv="refresh"','<base']:self.assertNotIn(marker,doc)
        self.assertIn("default-src &#x27;none&#x27;",doc);self.assertIn('<svg',doc)
        with closing(sqlite3.connect(location(self.cfg))) as db:
            db.execute("UPDATE reports SET html='tampered'");db.commit()
        with self.assertRaises(ValueError):read(self.root,'900001',result['id'])
    def attachment(self,name,value):
        encoded=base64.b64encode(json.dumps(value).encode()).decode()
        return f'<a href="data:application/json;base64,{encoded}" download="{name}">data</a>'
    def doc(self,**changes):
        return dict(company={'ticker':'900001'},as_of='2026-01-01',status='limited',sources=[{'title':'원문 <제목>','url':'https://example.com/source','publisher':'발행처','published_at':'2026-01-01'}],**changes)
    def test_existing_report_metadata_is_derived_without_rewriting_original(self):
        doc=self.doc();self.payload['html']=self.attachment('report-input.json',doc)+self.attachment('source-ledger.json',doc)
        result=register(self.root,self.payload);view=read(self.root,'900001',result['id'])
        self.assertEqual(result['reports'][0]['review_status'],'limited')
        self.assertEqual(view['report']['embedded_sources'][0]['title'],'원문 <제목>')
        self.assertEqual(len(view['report']['embedded_sources']),1)
        self.assertNotIn('data:application/json',view['document'])
        with closing(sqlite3.connect(location(self.cfg))) as db:self.assertEqual(db.execute('SELECT html FROM reports').fetchone()[0],self.payload['html'])
    def test_status_is_authors_declaration_and_generic_html_remains_supported(self):
        for status,label in [('draft','초안'),('limited','조사 한계 있음'),('verified','검증본')]:
            doc=self.doc();doc['status']=status
            value=embedded(self.attachment('report-input.json',doc),'900001')
            self.assertEqual(value['review_label'],'작성자 표기: '+label)
        self.assertEqual(embedded('<h1>ordinary</h1>','900001')['review_status'],'unknown')
    def test_mismatched_company_date_or_duplicate_attachments_are_not_used(self):
        for kind in ['company','date','duplicate']:
            with self.subTest(kind=kind):
                doc=self.doc();ledger=self.doc()
                if kind=='company':ledger['company']={'ticker':'900002'}
                if kind=='date':ledger['as_of']='2026-01-02'
                html=self.attachment('report-input.json',doc)+self.attachment('source-ledger.json',ledger)
                if kind=='duplicate':html+=self.attachment('report-input.json',doc)
                value=embedded(html,'900001')
                self.assertEqual(value['embedded_sources'],[]);self.assertEqual(value['review_status'],'unknown');self.assertTrue(value['embedded_notice'])
    def test_unsafe_duplicate_and_non_url_sources(self):
        doc=self.doc();doc['sources'] += [{'url':u} for u in ['javascript:alert(1)','https://localhost/x','https://example.com/?token=secret','https://example.com/with space','https://example.com/source',None]]
        value=embedded(self.attachment('report-input.json',doc),'900001')
        self.assertEqual(len(value['embedded_sources']),1);self.assertIn('4개',value['embedded_notice'])
    def test_malformed_and_oversized_attachments_do_not_break_listing(self):
        for html in ['<a download="report-input.json" href>bad</a>','<a download="report-input.json" href="data:application/json;base64,!!!">bad</a>',self.attachment('report-input.json',[]),'<a download="report-input.json" href="data:application/json;base64,'+'a'*(2*1024*1024)+'">large</a>']:
            with self.subTest(length=len(html)):
                self.payload['html']=html;result=register(self.root,self.payload)
                row=next(v for v in result['reports'] if v['id']==result['id'])
                self.assertEqual(row['review_status'],'unknown');self.assertTrue(row['embedded_notice'])

    def test_http_auth_and_read_only(self):
        from investment.live_dashboard import handler_for
        root=Path(__file__).resolve().parents[1]
        for readonly in (False,True):
            server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(root,token='synthetic-report-token',read_only=readonly))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(server.server_port)
            try:
                with self.assertRaises(HTTPError) as e:urlopen(base+'/company-reports?code=900001')
                self.assertEqual(e.exception.code,403)
                headers={'X-Dashboard-Token':'synthetic-report-token','Origin':base,'Content-Type':'application/json'}
                req=Request(base+'/company-reports',data=json.dumps(self.payload).encode(),headers=headers)
                if readonly:
                    with self.assertRaises(HTTPError) as e:urlopen(req)
                    self.assertEqual(e.exception.code,403)
                else:
                    with urlopen(req) as response:self.assertTrue(json.load(response)['id'])
            finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
