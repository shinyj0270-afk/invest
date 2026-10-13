"""Synthetic HTTPS/mobile access boundaries; no real credentials or data."""
import base64
import json
import io
from pathlib import Path
import shutil
import ssl
import subprocess
import tempfile
import threading
import unittest
from http.server import HTTPServer
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scripts.mobile_dashboard import Access, TLSServer, LimitedServer, handler_for, lan_address, password_record, password_pair_error, configure, detect_address
from investment.fixture import make_fixture
from investment.live_dashboard import handler_for as dashboard_handler

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = 'synthetic-test-password'


class MobileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT/'validation/current').mkdir(parents=True,exist_ok=True)
        cls.folder = tempfile.TemporaryDirectory(dir=ROOT/'validation/current')
        folder = Path(cls.folder.name)
        openssl = shutil.which('openssl') or 'C:/Program Files/Git/usr/bin/openssl.exe'
        subprocess.run([openssl,'req','-x509','-newkey','rsa:2048','-sha256','-nodes',
                        '-days','1','-subj','/CN=synthetic-test', '-addext','subjectAltName=IP:127.0.0.1',
                        '-out',str(folder/'cert.pem'),'-keyout',str(folder/'key.pem')],check=True,capture_output=True)
        cls.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        cls.context.minimum_version = ssl.TLSVersion.TLSv1_2
        cls.context.load_cert_chain(str(folder/'cert.pem'),str(folder/'key.pem'))
        cls.client_context = ssl.create_default_context(cafile=str(folder/'cert.pem'))
        cls.record = password_record(PASSWORD)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def setUp(self):
        self.calls = []
        def refresh(root, force=False):
            self.calls.append(force)
            return dict(snapshot=make_fixture(),receipt=dict(status='cached',success=True))
        self.backend = HTTPServer(('127.0.0.1',0),dashboard_handler(ROOT,refresh=refresh,token='synthetic-token',read_only=True))
        self.backend_thread = threading.Thread(target=self.backend.serve_forever,daemon=True)
        self.backend_thread.start()
        # Reserve the actual port, then configure the exact authority before serving.
        self.access = Access('https://127.0.0.1:8770',self.record)
        self.server = TLSServer(('127.0.0.1',0),handler_for(self.access,self.backend.server_port),self.context)
        self.base = f'https://127.0.0.1:{self.server.server_port}'
        self.access.origin = self.base
        self.access.authority = self.base.removeprefix('https://')
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.auth = 'Basic '+base64.b64encode(('investment:'+PASSWORD).encode()).decode()

    def tearDown(self):
        for server in (self.server,self.backend):
            server.shutdown();server.server_close()
        self.thread.join(timeout=3);self.backend_thread.join(timeout=3)

    def request(self,path='/',headers=None,data=None):
        return urlopen(Request(self.base+path,headers=headers or {},data=data),context=self.client_context,timeout=10)

    def rejected(self,code,path='/',headers=None,data=None):
        with self.assertRaises(HTTPError) as caught:
            self.request(path,headers,data)
        self.assertEqual(caught.exception.code,code)
        caught.exception.body=caught.exception.read()
        caught.exception.close()
        return caught.exception

    def test_no_page_token_health_or_api_without_login(self):
        for path in ('/','/dashboard','/health','/holdings','/company-view?code=900000'):
            response=self.rejected(401,path)
            self.assertIn('Basic',response.headers['WWW-Authenticate'])
            self.assertNotIn(b'synthetic-token',response.body)
        self.assertEqual(self.calls,[])

    def test_lazy_section_preserves_version_query_and_token_without_mutations(self):
        headers={'Authorization':self.auth,'X-Dashboard-Token':'synthetic-token'}
        html=self.request('/dashboard',headers=headers).read().decode()
        live=json.JSONDecoder().raw_decode(html.split('const INVESTMENT_LIVE=',1)[1])[0]
        path='/dashboard-section?section=trend-following&version='+live['section_version']
        payload=json.load(self.request(path,headers=headers))
        self.assertIn('rows',payload['trend_following'])
        self.rejected(403,path,headers={'Authorization':self.auth})
        self.rejected(404,'/restart',headers=headers)
        self.rejected(403,'/data-recovery',headers=headers,data=b'{"kind":"price","code":"900000"}')

    def test_wrong_malformed_and_oversized_credentials(self):
        for value in ('Basic invalid!', 'Bearer synthetic', 'Basic '+base64.b64encode(b'wrong:wrong').decode(), 'x'*3000):
            self.rejected(401,headers={'Authorization':value})
        self.assertEqual(self.calls,[])

    def test_allowlisted_host_and_origin_ignore_forwarded_headers(self):
        for headers in ({'Host':'elsewhere.invalid'}, {'Origin':'https://elsewhere.invalid'}, {'Sec-Fetch-Site':'cross-site'}):
            self.rejected(403,headers={'Authorization':self.auth,**headers})
        with self.request(headers={'Authorization':self.auth,'X-Forwarded-Host':'elsewhere.invalid','X-Forwarded-Proto':'http'}) as response:
            self.assertEqual(response.status,200)
        with self.request(headers={'Authorization':self.auth,'Sec-Fetch-Site':'cross-site','Sec-Fetch-Mode':'navigate'}) as response:
            self.assertEqual(response.status,200)

    def test_tls_authenticated_dashboard_and_preserved_api_token(self):
        with self.request('/dashboard',{'Authorization':self.auth}) as response:
            html=response.read().decode()
            self.assertIn('synthetic-token',html)
            self.assertIn('mobile-readonly',html)
            self.assertIn('[data-rec-exception],[data-recovery-code]{display:none!important}',html)
            self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.rejected(403,'/company-view?code=900000',{'Authorization':self.auth})
        code=make_fixture()['companies'][0]['code']
        with self.request('/company-view?code='+code,{'Authorization':self.auth,'X-Dashboard-Token':'synthetic-token','Origin':self.base}) as response:
            self.assertEqual(json.load(response)['code'],code)

    def test_mutations_unknown_routes_and_refresh_get_are_blocked(self):
        for path in ('/holdings','/refresh','/market-refresh','/company-financials?code=900000'):
            self.rejected(403,path,{'Authorization':self.auth,'Origin':self.base,'X-Dashboard-Token':'synthetic-token'},b'')
        self.rejected(404,'/private_data/file',{'Authorization':self.auth})
        self.rejected(400,'//elsewhere.invalid/',{'Authorization':self.auth})
        self.rejected(403,'/holding-market?code=900000&refresh=1',{'Authorization':self.auth})
        self.assertEqual(self.calls,[])

    def test_login_throttle(self):
        for _ in range(8):
            self.rejected(401,headers={'Authorization':'Basic invalid!'})
        self.rejected(429,headers={'Authorization':self.auth})
        self.access.failures=[x-61 for x in self.access.failures]
        with self.request(headers={'Authorization':self.auth}) as response:
            self.assertEqual(response.status,200)

    def test_validation_and_no_config_overwrite(self):
        for address in ('0.0.0.0','8.8.8.8','127.0.0.1','::1'):
            with self.assertRaises(ValueError):lan_address(address)
        userinfo=''.join(('https:', '//', 'synthetic', ':', 'synthetic', '@', '192.168.0.1:8770'))
        for origin in ('http://192.168.0.1:8770','https://192.168.0.1:8770/',userinfo):
            with self.assertRaises(ValueError):Access(origin,self.record)
        with self.assertRaises(ValueError):password_record('short')
        folder=Path(self.folder.name)/'existing';folder.mkdir(exist_ok=True)
        (folder/'config.json').write_text('original')
        with self.assertRaises(ValueError):configure(folder,'192.168.0.1',8770)
        self.assertEqual((folder/'config.json').read_text(),'original')

    def test_initial_configuration_creates_hash_and_certificate_only(self):
        folder=Path(self.folder.name)/'configured'
        with patch('scripts.mobile_dashboard.getpass.getpass',side_effect=[PASSWORD,PASSWORD]):
            configure(folder,'192.168.0.10',8770)
        data=json.loads((folder/'config.json').read_text())
        self.assertNotIn(PASSWORD,(folder/'config.json').read_text())
        self.assertEqual(data['origin'],'https://192.168.0.10:8770')
        self.assertEqual(Access(data['origin'],data['password']).authenticate(self.auth),200)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(folder/'cert.pem'),str(folder/'key.pem'))

    def test_short_password_retries_without_creating_incomplete_config(self):
        folder=Path(self.folder.name)/'short-retry'
        output=io.StringIO()
        with patch('scripts.mobile_dashboard.getpass.getpass',side_effect=['short',PASSWORD,PASSWORD]) as prompt, patch('sys.stdout',output):
            configure(folder,None,8771,'https://synthetic.trycloudflare.com')
        self.assertEqual(prompt.call_count,3)
        self.assertNotIn(PASSWORD,output.getvalue())
        self.assertNotIn('short',output.getvalue())
        data=json.loads((folder/'config.json').read_text())
        self.assertEqual(Access(data['origin'],data['password']).authenticate(self.auth),200)

    def test_confirmation_mismatch_retries_without_exposing_password(self):
        folder=Path(self.folder.name)/'confirmation-retry'
        output=io.StringIO()
        with patch('scripts.mobile_dashboard.getpass.getpass',side_effect=[PASSWORD,'synthetic-other-password',PASSWORD,PASSWORD]) as prompt, patch('sys.stdout',output):
            configure(folder,None,8771,'https://synthetic.trycloudflare.com')
        self.assertEqual(prompt.call_count,4)
        self.assertNotIn(PASSWORD,output.getvalue())
        self.assertNotIn('synthetic-other-password',output.getvalue())
        data=json.loads((folder/'config.json').read_text())
        self.assertEqual(Access(data['origin'],data['password']).authenticate(self.auth),200)

    def test_gui_password_pair_validation(self):
        self.assertTrue(password_pair_error('short','short'))
        self.assertTrue(password_pair_error(PASSWORD,'different'))
        self.assertFalse(password_pair_error(PASSWORD,PASSWORD))

    def test_gui_configuration_does_not_use_console_or_store_plaintext(self):
        folder=Path(self.folder.name)/'gui-config'
        with patch('scripts.mobile_dashboard.request_password_window',return_value=PASSWORD), patch('scripts.mobile_dashboard.getpass.getpass') as console:
            configure(folder,None,8771,'https://synthetic.trycloudflare.com',internet=True,password_window=True)
        console.assert_not_called()
        data=json.loads((folder/'config.json').read_text())
        self.assertEqual(data['mode'],'internet')
        self.assertNotIn(PASSWORD,(folder/'config.json').read_text())
        self.assertEqual(Access(data['origin'],data['password']).authenticate(self.auth),200)

    def test_gui_cancel_preserves_unconfigured_state(self):
        folder=Path(self.folder.name)/'gui-cancel'
        with patch('scripts.mobile_dashboard.request_password_window',side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            configure(folder,None,8771,'https://synthetic.trycloudflare.com',password_window=True)
        self.assertFalse((folder/'config.json').exists())

    def test_actual_gui_entries_mask_input_and_confirm_button_fits(self):
        import tkinter as tk
        from tkinter import ttk
        from scripts.mobile_dashboard import request_password_window
        root=tk.Tk();root.withdraw()
        checks=[]
        def widgets(widget):
            result=[widget]
            for child in widget.winfo_children():result.extend(widgets(child))
            return result
        def enter():
            controls=widgets(root)
            entries=[x for x in controls if isinstance(x,ttk.Entry)]
            checks.append(len(entries)==2 and all(str(x.cget('show'))=='*' for x in entries))
            height=int(root.geometry().split('+')[0].split('x')[1])
            checks.append(height>=root.winfo_reqheight())
            for entry in entries:entry.insert(0,PASSWORD)
            button=next(x for x in controls if isinstance(x,ttk.Button) and x.cget('text')=='설정하고 접속 시작')
            button.invoke()
        root.after(200,enter)
        with patch('tkinter.Tk',return_value=root):
            self.assertEqual(request_password_window(),PASSWORD)
        self.assertEqual(checks,[True,True])

    def test_external_https_configuration_and_exact_host(self):
        folder=Path(self.folder.name)/'external'
        with patch('scripts.mobile_dashboard.getpass.getpass',side_effect=[PASSWORD,PASSWORD]):
            configure(folder,None,8771,'https://synthetic.trycloudflare.com')
        data=json.loads((folder/'config.json').read_text())
        self.assertEqual(data['mode'],'proxy')
        self.assertEqual(data['bind'],'127.0.0.1')
        self.assertFalse((folder/'key.pem').exists())
        self.access.origin=data['origin'];self.access.authority='synthetic.trycloudflare.com'
        with self.request('/dashboard',{'Authorization':self.auth,'Host':self.access.authority,'Origin':self.access.origin}) as response:
            self.assertIn(b'WORKSPACE_DATA',response.read())
        self.rejected(403,headers={'Authorization':self.auth,'Host':'127.0.0.1:8771','X-Forwarded-Host':self.access.authority})

    @unittest.skipUnless(__import__('os').name=='nt','Windows physical adapter detection')
    def test_vpn_address_is_not_selected_as_lan(self):
        with patch('scripts.mobile_dashboard.subprocess.run',return_value=type('Result',(),{'stdout':'["210.1.2.3"]'})()):
            with self.assertRaises(ValueError):detect_address()
        with patch('scripts.mobile_dashboard.subprocess.run',return_value=type('Result',(),{'stdout':'["192.168.0.10"]'})()):
            self.assertEqual(detect_address(),'192.168.0.10')

    def test_external_loopback_worker_slots_are_released(self):
        access=Access('https://synthetic.trycloudflare.com',self.record)
        server=LimitedServer(('127.0.0.1',0),handler_for(access,self.backend.server_port))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            for _ in range(20):
                request=Request(f'http://127.0.0.1:{server.server_port}/health',headers={'Authorization':self.auth,'Host':access.authority})
                with urlopen(request,timeout=10) as response:self.assertEqual(response.status,200)
        finally:
            server.shutdown();server.server_close();thread.join(timeout=3)

    def test_synthetic_mobile_browser(self):
        from playwright.sync_api import sync_playwright,expect
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
            context=browser.new_context(ignore_https_errors=True,http_credentials={'username':'investment','password':PASSWORD},viewport={'width':390,'height':844})
            page=context.new_page();errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(self.base,wait_until='load')
            expect(page.locator('#home')).to_be_visible(timeout=20000)
            expect(page.locator('.mobile-readonly').first).to_be_visible()
            page.locator('#pageSelect').select_option('finder')
            expect(page.locator('[data-watch] svg').first).to_be_visible()
            page.locator('#pageSelect').select_option('company')
            expect(page.locator('#sdSettings')).to_be_visible()
            page.locator('#sdSettings').click();expect(page.locator('.sd-settings')).to_be_visible()
            for width in (390,320):
                page.set_viewport_size({'width':width,'height':844})
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
            self.assertEqual(errors,[])
            page.screenshot(path=str(ROOT/'validation/current/mobile-access-synthetic.png'))
            browser.close()


if __name__ == '__main__':
    (ROOT/'validation/current').mkdir(parents=True,exist_ok=True)
    unittest.main()
