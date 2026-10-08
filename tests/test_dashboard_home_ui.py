"""Offline fixture checks for simplified navigation and the personal home flow."""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace
from playwright.sync_api import sync_playwright,expect

snapshot=make_fixture()
for bars in snapshot['benchmarks'].values():
    for b in bars:b['final']=True
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];network=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:network.append(r.url) if r.url.startswith(('http:','https:')) else None)
    page.set_content(export_workspace(snapshot),wait_until='load')
    expect(page.locator('#home')).to_be_visible()
    assert page.locator('#moreNavigation').get_attribute('open') is None
    assert page.locator('#navigation>.nav-item').count()==6
    assert page.locator('#sourceDetails').get_attribute('open') is None
    expect(page.locator('#homeMarketCharts')).to_contain_text('KOSPI')
    expect(page.locator('#homeVerdict')).to_contain_text('오늘의 결론')
    expect(page.locator('#homeKpis')).to_contain_text('탐색 범위')
    page.locator('#moreNavigation summary').click()
    expect(page.locator('#moreNavigation .more-menu')).to_be_visible()
    page.locator('#moreNavigation .nav-item').first.click()
    assert page.locator('#moreNavigation').get_attribute('open') is None
    page.locator('[data-page=home]').click()
    expect(page.locator('#homeWatch')).to_contain_text('별표')
    page.locator('#homeQuery').fill('900002');page.locator('#homeSearch button').click()
    expect(page.locator('#discoveryTable tbody tr')).to_have_count(1)
    page.locator('[data-watch="900002"]').click()
    page.locator('[data-page=home]').click()
    expect(page.locator('#homeWatch [data-home-code="900002"]')).to_be_visible()
    page.locator('#homeWatch [data-home-code="900002"]').click()
    expect(page.locator('#researchCompany')).to_have_value('900002')
    page.locator('[data-context-page=trend]').click()
    expect(page.locator('#research')).to_contain_text('900002')
    page.locator('[data-context-page=brief]').click()
    page.locator('[data-context-page=company]').click()
    expect(page.locator('#sdCompany')).to_have_value('900002')
    page.locator('[data-page=holdings]').click()
    frame=page.frame_locator('#detailFrame')
    frame.locator('#pManagement summary').click();frame.locator('#pFixture').click()
    page.locator('[data-page=home]').click()
    expect(page.locator('#homeHoldings')).to_contain_text('가상 테스트')
    assert page.locator('#homeHoldings .home-company').count()>0
    expect(page.locator('#homeHoldings .brief-item').first).to_contain_text('첫 관측')
    expect(page.locator('#homeHoldings .brief-basis').first).to_contain_text('확인')
    assert page.locator('#homeHoldings .brief-item').count()==page.locator('#homeHoldings .home-company').count()
    page.locator('#homeSectors button').first.click()
    expect(page.locator('#discoveryFilters [name=industry]')).not_to_have_value('')
    page.locator('[data-page=home]').click()
    page.screenshot(path=str(ROOT/'validation/dashboard-home-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    for view in ['home','finder','watch','brief','trend','holdings','portfolio']:
        page.locator('#pageSelect').select_option(view)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),view
    page.locator('#pageSelect').select_option('home')
    page.screenshot(path=str(ROOT/'validation/dashboard-home-mobile.png'),full_page=True)
    assert not errors,errors
    assert not network,network
    browser.close()
print('PASS dashboard home, six primary menus, search/watch/detail/trend/sector/holdings flows, seven mobile views, no network/JS errors')
