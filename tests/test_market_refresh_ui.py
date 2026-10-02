"""Single refresh button, progress, failure and preservation of unsaved holdings."""
import os
from pathlib import Path
import sys
import tempfile
import threading
from http.server import HTTPServer
from playwright.sync_api import sync_playwright, expect

def open_tools(page):
    if page.locator('#moreNavigation').get_attribute('open') is None:
        page.locator('#moreNavigation summary').click()


ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from investment.fixture import make_fixture
from investment.live_dashboard import handler_for

snapshot=make_fixture();snapshot['meta']['data_mode']='user_input'
class Daily:
    def __init__(self):self.calls=0;self.reads=0;self.status='idle';self.fail=False
    def start(self):self.calls+=1;self.reads=0;self.status='running';return self.poll()
    def poll(self):
        if self.status=='running':
            self.reads+=1
            if self.reads>=3:
                self.status='failed' if self.fail else 'complete'
                if not self.fail:snapshot['companies'][0]['metrics']['roe_pct']=72
        return dict(status=self.status,completed=min(self.reads,2),total=2,failed=int(self.fail),
            target_date=snapshot['meta']['price_date'],retrieved_at='2026-10-02T10:00:00+09:00',updated_companies=2,message='갱신 실패 · 기존 자료 유지')
latest=Daily()
class Auto(Daily):
    def ensure_due(self):
        if self.status=='idle':self.start()
        return self.poll()
auto=Auto()
def refresh(root,force=False):
    return dict(snapshot=snapshot,receipt=dict(status='cached',success=True,data_as_of=snapshot['meta']['price_date']))
with tempfile.TemporaryDirectory() as temp:
    server=HTTPServer(('127.0.0.1',0),handler_for(temp,refresh=refresh,token='test',daily=auto,latest=latest))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
            page=browser.new_page(viewport={'width':1440,'height':900});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            expect(page.locator('#refreshData')).to_have_text('새로고침')
            assert page.locator('#refreshPrices').count()==0
            expect(page.locator('#priceRefreshStatus')).to_contain_text('일별',timeout=15000)
            expect(page.locator('#refreshData')).to_be_enabled()
            page.wait_for_timeout(6000)
            assert auto.calls==1
            assert latest.calls==0
            page.locator('[data-page=holdings]').click()
            frame=page.frame_locator('#detailFrame')
            frame.locator('#pCode').fill('900000');frame.locator('#pQty').fill('7');frame.locator('#pCost').fill('12345')
            page.locator('#refreshData').click()
            expect(page.locator('#refreshData')).to_be_disabled()
            expect(page.locator('#priceRefreshStatus')).to_contain_text('최신 제공 가격 조회 중')
            expect(page.locator('#refreshData')).to_be_enabled(timeout=15000)
            expect(frame.locator('#pQty')).to_have_value('7')
            expect(frame.locator('#pCost')).to_have_value('12345')
            assert page.locator('body').get_attribute('data-current-page')=='holdings'
            open_tools(page);page.locator('[data-page=scatter]').click()
            expect(page.locator('#focusMetrics')).to_contain_text('72 %')
            assert latest.calls==1
            latest.fail=True
            page.locator('#refreshData').click()
            expect(page.locator('#priceRefreshStatus')).to_contain_text('갱신 실패',timeout=15000)
            expect(page.locator('#focusMetrics')).to_contain_text('72 %')
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'), 'mobile overflow'
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown();server.server_close();thread.join(3)
print('PASS automatic daily refresh once, no latest quote request on open, single manual latest refresh, progress, unsaved input/menu preserved, failure, mobile')
