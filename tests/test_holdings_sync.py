"""Synthetic private sync, durable offline queue, CAS retry and loopback auth."""
import copy,json,tempfile,subprocess,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from http.server import HTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from investment.holdings_sync import GitHubStorage,HoldingsService,SyncError,contract
from investment.live_dashboard import handler_for
ROOT=Path(__file__).resolve().parents[1]

def state():
    script="const P=require('./src/portfolio_engine.js'),H=require('./src/holdings_sync.js');let x=P.fixture();x.mode='user_input';console.log(JSON.stringify(H.pack(x,P.DEFAULT)));"
    return json.loads(subprocess.check_output(['node','-e',script],cwd=ROOT,text=True,encoding='utf-8'))

class MemoryBackend:
    def __init__(self):self.state=None;self.revision=None;self.offline=False;self.race=None;self.writes=0
    def read(self):
        if self.offline:raise SyncError('연결 대기')
        return copy.deepcopy(self.state),self.revision
    def write(self,s,sha):
        if self.race:
            self.state=self.race;self.revision='changed';self.race=None;raise SyncError('REMOTE_CHANGED')
        if sha!=self.revision:raise SyncError('REMOTE_CHANGED')
        self.writes+=1;self.state=copy.deepcopy(s);self.revision=str(self.writes);return self.revision

class HoldingsSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.backend=MemoryBackend()
        self.cache=Path(self.temp.name)/'work.json';self.service=HoldingsService(ROOT,self.backend,self.cache)
    def tearDown(self):self.temp.cleanup()
    def test_saved_restart_and_other_pc_read(self):
        a=state();self.assertEqual(self.service.submit(a,None)['status'],'synced')
        restarted=HoldingsService(ROOT,self.backend,self.cache);self.assertEqual(restarted.poll()['state'],a)
        other=HoldingsService(ROOT,self.backend,Path(self.temp.name)/'home.json');self.assertEqual(other.poll()['state'],a)
    def test_offline_queue_survives_restart_and_reconnect(self):
        self.backend.offline=True;a=state();self.assertEqual(self.service.submit(a,None)['status'],'offline')
        self.assertTrue(json.loads(self.cache.read_text(encoding='utf-8'))['pending']);self.backend.offline=False
        restarted=HoldingsService(ROOT,self.backend,self.cache);self.assertEqual(restarted.poll()['status'],'synced');self.assertEqual(self.backend.state,a)
    def test_independent_edits_and_conflict_do_not_overwrite(self):
        b=state();self.service.submit(b,None);l=copy.deepcopy(b);r=copy.deepcopy(b)
        l['input']['holdings'][0]['quantity']=42;r['input']['holdings'][1]['quantity']=12
        self.service.submit(r,b);m=self.service.submit(l,b);self.assertEqual(m['status'],'synced');self.assertEqual(m['state']['input']['holdings'][1]['quantity'],12)
        conflicting=copy.deepcopy(b);conflicting['input']['holdings'][0]['quantity']=99
        writes=self.backend.writes;result=self.service.submit(conflicting,b);self.assertEqual(result['status'],'conflict');self.assertEqual(self.backend.writes,writes)
        self.assertEqual(json.loads(self.cache.read_text(encoding='utf-8'))['state'],conflicting)
    def test_compare_and_swap_retry_keeps_racing_change(self):
        b=state();self.service.submit(b,None);l=copy.deepcopy(b);r=copy.deepcopy(b)
        l['input']['holdings'][0]['quantity']=42;r['input']['holdings'][1]['quantity']=12;self.backend.race=r
        result=self.service.submit(l,b);self.assertEqual(result['status'],'synced');self.assertEqual(result['state']['input']['holdings'][1]['quantity'],12)
    def test_invalid_input_does_not_change_good_local_or_remote(self):
        a=state();self.service.submit(a,None);before=self.cache.read_bytes();a['input']['holdings'][0]['quantity']=-1
        with self.assertRaises(SyncError):self.service.submit(a,None)
        self.assertEqual(self.cache.read_bytes(),before);self.assertEqual(self.backend.writes,1)
    def test_corrupt_cache_not_overwritten(self):
        self.cache.write_text('broken')
        with self.assertRaises(SyncError):HoldingsService(ROOT,self.backend,self.cache)
        self.assertEqual(self.cache.read_text(),'broken')
    def test_remote_file_disappearing_keeps_local(self):
        a=state();self.service.submit(a,None);self.backend.state=None
        result=self.service.poll();self.assertEqual(result['status'],'offline');self.assertEqual(result['state'],a)
    def test_public_repository_never_reads_or_writes_holdings(self):
        calls=[]
        def run(args,**kwargs):calls.append(args);return SimpleNamespace(returncode=0,stdout=json.dumps({'private':False,'full_name':'test/holdings','permissions':{'push':True}}),stderr='')
        backend=GitHubStorage('test/holdings',run=run)
        with self.assertRaises(SyncError):backend.read()
        with self.assertRaises(SyncError):backend.write(state(),None)
        self.assertEqual(len(calls),2);self.assertTrue(all('/contents/' not in ' '.join(a) for a in calls))
    def test_missing_and_permission_failures_are_distinct(self):
        def run(args,**kwargs):return SimpleNamespace(returncode=1,stdout='',stderr='gh: Not Found (HTTP 404)')
        backend=GitHubStorage('test/holdings',run=run)
        self.assertIsNone(backend.api('unused',missing=True))
        with self.assertRaises(SyncError):backend.verify_private()
    def test_loopback_auth_and_request_validation(self):
        server=HTTPServer(('127.0.0.1',0),handler_for(ROOT,holdings=self.service,token='synthetic-token'))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
        try:
            for headers in [{},{'X-Dashboard-Token':'wrong'},{'X-Dashboard-Token':'synthetic-token','Origin':'https://elsewhere.invalid'}]:
                with self.assertRaises(HTTPError) as e:urlopen(Request(base+'/holdings',headers=headers))
                self.assertEqual(e.exception.code,403)
            headers={'X-Dashboard-Token':'synthetic-token','Origin':base,'Content-Type':'application/json'}
            with urlopen(Request(base+'/holdings',data=json.dumps({'state':state(),'base':None}).encode(),headers=headers)) as r:self.assertEqual(json.load(r)['status'],'synced')
            with self.assertRaises(HTTPError) as e:urlopen(Request(base+'/holdings',data=b'{}',headers=headers))
            self.assertEqual(e.exception.code,400)
            with urlopen(Request(base+'/holdings',headers={'X-Dashboard-Token':'synthetic-token'})) as r:self.assertIsNotNone(json.load(r)['state'])
        finally:server.shutdown();server.server_close();thread.join(3)
