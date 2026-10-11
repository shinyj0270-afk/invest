import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from investment.research_library import Library
from investment.research_library_view import view
from tests.test_research_library import source, thesis, card


class ViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'config').mkdir()
        (self.root/'config'/'local.json').write_text(json.dumps(dict(profile='work',project_root='.',data_dir='data',enabled_data_adapters=[],scheduled_jobs_enabled=False)),encoding='utf-8')

    def tearDown(self):self.temp.cleanup()

    def test_empty_does_not_create_any_db(self):
        result=view(self.root)
        self.assertEqual(result['status'],'empty')
        self.assertEqual(len(result['masters']),8)
        self.assertFalse((self.root/'.local').exists())

    def test_readonly_and_home_database_not_imported(self):
        lib=Library(self.root/'.local'/'research-library','work')
        lib.source('s1',source());lib.master('m1',card());lib.thesis('t1',thesis())
        before=hashlib.sha256(lib.path.read_bytes()).hexdigest()
        result=view(self.root)
        self.assertEqual(len(result['theses']),1)
        self.assertEqual(hashlib.sha256(lib.path.read_bytes()).hexdigest(),before)
        self.assertFalse((self.root/'.local'/'research-library'/'home').exists())

    def test_work_blocks_imported_telegram(self):
        lib=Library(self.root/'.local'/'research-library','work')
        lib._put('source','restricted',dict(origin='telegram'))
        with self.assertRaises(ValueError):view(self.root)

    def test_seed_id_format_and_historical_source_display(self):
        lib=Library(self.root/'.local'/'research-library','work')
        lib.source('s1',source());lib.master('m1',card())
        initial=thesis();initial['seed_source_ids']=[{}]
        with self.assertRaises(ValueError):lib.thesis('t1',initial)
        initial['seed_source_ids']=['s1'];initial['master_ids']=[]
        lib.thesis('t1',initial)
        revised=dict(initial,seed_source_ids=[])
        lib.thesis('t1',revised,1)
        self.assertIn('s1:',lib.draft('t1'))
        self.assertIn('이전 revision 출처',lib.draft('t1'))

    def test_readonly_server_never_initializes_services(self):
        from investment.live_dashboard import serve
        with patch('investment.live_dashboard.ThreadingHTTPServer') as server, patch('investment.live_dashboard.load_service') as sync, patch('investment.live_dashboard.DailyMarketRefresh') as refresh:
            serve(self.root,port=8768,read_only=True)
            sync.assert_not_called();refresh.assert_not_called()
            server.return_value.__enter__.return_value.serve_forever.assert_called_once()

    def test_authenticated_route_and_readonly_mutation_rejection(self):
        import threading
        from http.server import HTTPServer
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        from investment.live_dashboard import handler_for
        with HTTPServer(('127.0.0.1',0),handler_for(self.root,token='fixture',read_only=True)) as server:
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(server.server_port)
            try:
                with self.assertRaises(HTTPError) as error:urlopen(base+'/research-library')
                self.assertEqual(error.exception.code,403)
                with urlopen(Request(base+'/research-library',headers={'X-Dashboard-Token':'fixture'})) as response:
                    self.assertEqual(json.load(response)['status'],'empty')
                with self.assertRaises(HTTPError) as error:urlopen(Request(base+'/refresh',data=b'',headers={'X-Dashboard-Token':'fixture','Origin':base}))
                self.assertEqual(error.exception.code,403)
                self.assertFalse((self.root/'.local').exists())
            finally:server.shutdown();thread.join()
