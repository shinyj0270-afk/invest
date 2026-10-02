"""Automatic financial revision reload uses the shared page restoration path."""
import os,sys,threading
from pathlib import Path
from http.server import HTTPServer
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from investment.fixture import make_fixture
from investment.live_dashboard import handler_for
from playwright.sync_api import sync_playwright,expect

snapshot=make_fixture();snapshot['meta']['data_mode']='user_input'
class Monitor:
    revision=None
    checks=0
    def poll(self):return dict(status='complete',checked_on='2026-10-02',revision=self.revision,updated=int(bool(self.revision)),deferred=2,failed=1,partial=1)
    def ensure_due(self):self.checks+=1;return self.poll()
monitor=Monitor();reads=[]
def refresh(root,force=False):reads.append(1);return dict(snapshot=snapshot,receipt={})
server=HTTPServer(('127.0.0.1',0),handler_for(ROOT,refresh=refresh,financial_monitor=monitor))
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
        page=browser.new_page(viewport={'width':1440,'height':1050});errors=[];root_reads=[]
        page.on('response',lambda response:root_reads.append(1) if response.url==f'http://127.0.0.1:{server.server_port}/' else None)
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.add_init_script('const originalTimeout=window.setTimeout;window.setTimeout=(f,t,...args)=>originalTimeout(f,t===60000?300:t,...args);')
        page.goto(f'http://127.0.0.1:{server.server_port}/',wait_until='load')
        page.locator('[data-page=brief]').click()
        selected=page.locator('#researchCompany').input_value()
        expect(page.locator('#financialRefreshStatus')).to_contain_text('7% 미만·미변경 2')
        monitor.revision='new-financials'
        page.wait_for_function("typeof INVESTMENT_LIVE!=='undefined'&&INVESTMENT_LIVE.financial_revision==='new-financials'")
        expect(page.locator('body')).to_have_attribute('data-current-page','brief')
        expect(page.locator('#researchCompany')).to_have_value(selected)
        expect(page.locator('#financialRefreshStatus')).to_contain_text('반영 1')
        expect(page.locator('#financialRefreshStatus')).to_contain_text('미확보 1')
        assert len(root_reads)==2,root_reads
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors
        browser.close()
finally:server.shutdown();server.server_close();thread.join(2)
print('PASS financial monitor status, automatic revision reload once, menu/company preservation, failure/partial counts, 390px')
