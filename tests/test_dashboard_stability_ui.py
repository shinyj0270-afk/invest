"""Draft reload, deferred frame/detail, stale quotes and initialization recovery."""
import copy
import json
import sys
import threading
from pathlib import Path
from http.server import HTTPServer
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from tools.browser_runtime import chromium_options
from investment.fixture import make_fixture
from investment.live_dashboard import handler_for
from investment.workspace_export import export_workspace
from investment.recommendations import propose
from tests.test_dashboard_upgrade import recommendation_context

snapshot=make_fixture();snapshot['meta']['data_mode']='user_input'
snapshot['companies'][0]['latest_quote']={'price':12345,'retrieved_at':'2026-10-02T11:00:00+09:00','price_time':None}
first=propose(recommendation_context(),created_on='2026-10-02')
second=propose(recommendation_context(),created_on='2026-10-03',kind='exception',reason='저장된 가상 사유',previous=first)
for r in [first,second]:r['performance']={'status':'pending','reason':'가상 가격 대기'}
class Monitor:
    revision=None
    def poll(self):return dict(status='complete',revision=self.revision,updated=int(bool(self.revision)),deferred=0,failed=0,partial=0)
    def ensure_due(self):return self.poll()
monitor=Monitor();manual=[False];root_reads=[]
def refresh(root,force=False):
    if force:manual[0]=True
    value=copy.deepcopy(snapshot)
    if manual[0]:value['companies'][0]['metrics']['roe_pct']=72
    return dict(snapshot=value,receipt={'status':'cached','error':None})
server=HTTPServer(('127.0.0.1',0),handler_for(ROOT,refresh=refresh,financial_monitor=monitor,token='synthetic'))
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
base=f'http://127.0.0.1:{server.server_port}'
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,**chromium_options())
        page=browser.new_page(viewport={'width':1440,'height':1050});errors=[];requests=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda request:requests.append(request.url))
        page.on('response',lambda r:root_reads.append(r.status) if r.url==base+'/' else None)
        page.add_init_script("Date.now=()=>Date.parse('2026-10-07T12:00:00+09:00');const timeout=window.setTimeout;window.setTimeout=(f,t,...a)=>timeout(f,t===60000?350:t,...a);")
        page.route(base+'/recommendations',lambda route:route.fulfill(content_type='application/json',body=json.dumps({'records':[first,second]},ensure_ascii=False)))
        page.goto(base+'/',wait_until='load')
        expect(page.locator('#home')).to_be_visible();expect(page.locator('#initializationError')).to_be_hidden()
        page.wait_for_function("typeof document.getElementById('detailFrame').contentWindow?.INVESTMENT_GET_HOLDINGS==='function'")
        assert any(url.endswith('/holdings-frame') for url in requests)
        assert not any('/company-view?' in url for url in requests),requests
        page.locator('[data-page=recommendations]').click()
        expect(page.locator('[data-rec-version] option')).to_have_count(2)
        page.locator('[data-rec-version]').select_option('0')
        reason='자동·수동 새로고침 후에도 보존할 가상 미저장 사유 <검토>'
        page.locator('#recommendationView textarea').fill(reason)
        monitor.revision='synthetic-revision-1'
        page.wait_for_function("typeof INVESTMENT_LIVE!=='undefined'&&INVESTMENT_LIVE.financial_revision==='synthetic-revision-1'")
        expect(page.locator('#recommendationView textarea')).to_have_value(reason)
        expect(page.locator('[data-rec-version]')).to_have_value('0')
        assert len(root_reads)==2,root_reads
        with page.expect_navigation(wait_until='load'):page.locator('#refreshData').click()
        expect(page.locator('#recommendationView textarea')).to_have_value(reason)
        expect(page.locator('[data-rec-version]')).to_have_value('0')
        page.reload(wait_until='load')
        expect(page.locator('#recommendationView textarea')).to_have_value(reason)
        expect(page.locator('[data-rec-version]')).to_have_value('0')
        page.locator('[data-page=brief]').click()
        expect(page.locator('#researchCompany')).to_have_value('900000')
        page.locator('[data-context-page=company]').click()
        expect(page.locator('#sdCompany')).to_have_value('900000')
        assert len([url for url in requests if '/company-view?' in url])==1,requests
        page.locator('#sdCompany').select_option('900001')
        expect(page.locator('#sdCompany')).to_have_value('900001')
        assert len([url for url in requests if '/company-view?' in url])==2
        page.locator('[data-page=home]').click()
        page.locator('#homeQuery').fill('900000');page.locator('#homeSearch button').click()
        page.locator('[data-watch="900000"]').click();page.locator('[data-page=home]').click()
        expect(page.locator('#homeWatch')).to_contain_text('이전 조회 참고가격')
        expect(page.locator('#homeWatch')).to_contain_text('시세시각 미확인')
        expect(page.locator('#homeWatch')).to_contain_text('2026-10-02')
        assert not errors,errors
        for width in [390,320]:
            page.set_viewport_size({'width':width,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        unavailable=browser.new_page()
        unavailable.route(base+'/dashboard',lambda route:route.abort())
        unavailable.goto(base+'/',wait_until='load')
        expect(unavailable.locator('#loadingStatus')).to_contain_text('화면을 준비하지 못했습니다')
        expect(unavailable.locator('#loadingRetry')).to_be_visible()
        expect(unavailable.locator('#loadingHelp')).to_contain_text('open-investment.cmd')
        outdated=browser.new_page()
        from investment.dashboard_build import restart_page
        outdated.route(base+'/dashboard',lambda route:route.fulfill(status=503,content_type='text/html',body=restart_page()))
        outdated.goto(base+'/',wait_until='load')
        expect(outdated.locator('main')).to_contain_text('새 코드가 저장되었습니다')
        broken=browser.new_page()
        broken.set_content(export_workspace(make_fixture()).replace('const TrendFollowingUI=','const MissingTrendFollowingUI=',1),wait_until='load')
        expect(broken.locator('#initializationError')).to_be_visible()
        expect(broken.locator('#initializationError')).to_contain_text('open-investment.cmd')
        browser.close()
finally:server.shutdown();server.server_close();thread.join(2)
print('PASS auto/manual/native reload draft+selected ID, initial no detail calls, authenticated deferred holdings frame, lazy company switch, stale quote, missing module recovery, mobile390/320, JS errors0')
