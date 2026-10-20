"""Logo selection preserves drafts, probes only on demand, and rejects invalid targets."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace
from tools.browser_runtime import chromium_options
from playwright.sync_api import sync_playwright, expect

html=export_workspace(make_fixture())
state={'available':False}
calls=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,**chromium_options())
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    def route(request):
        url=request.request.url
        if url=='http://127.0.0.1:9876/':request.fulfill(content_type='text/html',body=html)
        elif url=='http://127.0.0.1:9876/credit-status':
            calls.append(url)
            assert request.request.headers.get('x-dashboard-token')=='synthetic'
            request.fulfill(content_type='application/json',body=json.dumps(state))
        elif url=='http://127.0.0.1:4580/index.html':
            calls.append(url)
            request.fulfill(content_type='text/html; charset=utf-8',body='<meta charset="utf-8"><h1>합성 CREDIT 화면</h1><input id="creditDraft">')
        else:raise AssertionError('Unexpected request: '+url)
    page.route('**/*',route)
    page.goto('http://127.0.0.1:9876/')
    page.locator('#dashboardSwitch').click()
    expect(page.locator('#creditChoice')).to_be_disabled()
    assert calls==[]
    page.keyboard.press('Escape')
    expect(page.locator('#dashboardSwitch')).to_be_focused()
    page.evaluate("InvestmentDashboardSwitcher.create({token:'synthetic'},false)")
    page.locator('#homeQuery').fill('작성 중 기업 검색')
    page.locator('#dashboardSwitch').click()
    page.locator('#creditChoice').click()
    expect(page.locator('#creditConnectionStatus')).to_contain_text('CREDIT 대시보드를 실행')
    assert page.locator('#creditDashboardFrame').get_attribute('src') is None
    # A response cannot turn the logo into an arbitrary external-site launcher.
    state.update(available=True,url='https://example.invalid')
    page.locator('#creditRetry').click()
    expect(page.locator('#creditRetry')).to_be_enabled()
    assert page.locator('#creditDashboardFrame').get_attribute('src') is None
    state['url']='http://127.0.0.1:4580/index.html'
    page.locator('#creditRetry').click()
    expect(page.frame_locator('#creditDashboardFrame').locator('h1')).to_have_text('합성 CREDIT 화면')
    page.frame_locator('#creditDashboardFrame').locator('#creditDraft').fill('채권 입력 유지')
    before=len(calls)
    page.locator('#creditBack').click()
    expect(page.locator('#homeQuery')).to_have_value('작성 중 기업 검색')
    page.locator('#dashboardSwitch').click();page.locator('#creditChoice').click()
    expect(page.frame_locator('#creditDashboardFrame').locator('#creditDraft')).to_have_value('채권 입력 유지')
    assert len(calls)==before
    for width in (1440,390,320):
        page.set_viewport_size({'width':width,'height':900})
        page.locator('#dashboardSwitch').click()
        expect(page.locator('#dashboardChoices')).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
        page.keyboard.press('Escape')
    out=ROOT/'validation/current';out.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(out/'dashboard-switcher-credit.png'))
    page.locator('#creditBack').click()
    page.evaluate("InvestmentDashboardSwitcher.create({token:'synthetic'},true)")
    page.locator('#dashboardSwitch').click()
    expect(page.locator('#creditChoice')).to_be_disabled()
    assert not errors,errors
    browser.close()
print('PASS logo switcher: keyboard, explicit connection, unavailable/invalid target, both drafts preserved, no reload, result isolation, 1440/390/320px')
