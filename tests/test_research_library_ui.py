"""Full dashboard navigation, escaping, empty/error state and mobile research view."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from tools.browser_runtime import chromium_options
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace

html=export_workspace(make_fixture(),live={'token':'fixture'})
data=dict(status='ready',profile='work',cards=[],theses=[dict(id='t',revision=1,value=dict(title='<img src=x onerror=alert(1)>',claim='Synthetic claim',as_of='2026-01-03',status='active',invalidation=['Demand falls'],instruments=[]))])
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,**chromium_options())
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    def route(r):
        if r.request.url.endswith('/research-library'):
            assert r.request.headers.get('x-dashboard-token')=='fixture'
            r.fulfill(content_type='application/json',body=json.dumps(data))
        elif r.request.url.endswith('/'):r.fulfill(content_type='text/html',body=html)
        else:r.fulfill(content_type='application/json',body='{"records":[],"status":"idle"}')
    page.route('http://127.0.0.1:8767/**',route);page.goto('http://127.0.0.1:8767/')
    page.locator('#pageSelect').select_option('research-library',force=True)
    expect(page.locator('#researchLibrary')).to_be_visible()
    expect(page.locator('#libraryStatus')).to_contain_text('ready')
    assert page.locator('#researchLibrary img').count()==0
    expect(page.locator('#researchLibrary')).to_contain_text('<img src=x')
    for width in (390,320):
        page.set_viewport_size({'width':width,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    data['theses']=[];data['status']='empty'
    page.locator('#libraryReload').click()
    expect(page.locator('#researchLibrary')).to_contain_text('저장된 산업 가설이 없습니다')
    page.locator('#pageSelect').select_option('home',force=True);expect(page.locator('#home')).to_be_visible()
    page.route('**/research-library',lambda r:r.fulfill(status=503,body='{}'))
    page.locator('#pageSelect').select_option('research-library',force=True);page.locator('#libraryReload').click()
    expect(page.locator('#libraryStatus')).to_contain_text('연결 대기')
    assert not errors,errors
    browser.close()
print('PASS Research Library full navigation / XSS / empty / error / mobile')
