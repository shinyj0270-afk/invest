"""Offline synthetic browser checks of the reference-style exported workspace."""
import os
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace
from playwright.sync_api import sync_playwright,expect

snapshot=make_fixture()
for row in snapshot['companies']:
    for bar in row['prices']:
        bar.update(final=True,venue='KRX',adjustment_basis='unadjusted')
snapshot['companies'][0]['metrics']['roe_pct']=None
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
    page=browser.new_page(viewport={'width':1600,'height':1100})
    errors=[];requests=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:requests.append(r.url) if r.url.startswith(('http:','https:')) else None)
    page.set_content(export_workspace(snapshot),wait_until='load')
    expect(page.locator('#sourceNotice')).to_contain_text('가상 테스트')
    expect(page.locator('#kpis .kpi')).to_have_count(4)
    page.locator('[data-page=heatmap]').click()
    expect(page.locator('#mainChart .missing')).to_have_count(1)
    page.locator('#mainChart [data-code="900002"][data-key="roe_pct"]').click()
    expect(page.locator('#focusCompany')).to_have_value('900002')
    page.locator('[data-page=scatter]').click()
    points=page.locator('#mainChart circle')
    assert points.count()==7
    points.last.focus();points.last.press('Enter')
    selected=page.locator('#focusCompany').input_value()
    page.locator('[data-page=company]').click()
    frame=page.frame_locator('#detailFrame')
    expect(frame.locator('#companySelect')).to_have_value(selected)
    page.locator('[data-page=bars]').click()
    page.locator('#viewSearch').fill('900002')
    expect(page.locator('#mainChart .bar-row')).to_have_count(1)
    with page.expect_download() as downloaded:page.locator('#exportCsv').click()
    content=Path(downloaded.value.path()).read_text(encoding='utf-8-sig')
    assert '900002' in content and '900001' not in content
    page.locator('[data-page=overview]').click()
    expect(page.locator('#overviewBars .bar-row')).to_have_count(1)
    page.locator('[data-page=prices]').click()
    expect(page.locator('#mainChart svg')).to_be_visible()
    page.locator('#viewSearch').fill('no-such-company')
    expect(page.locator('#mainChart')).to_contain_text('자료 대기')
    page.locator('#reset').click()
    page.locator('[data-page=holdings]').click()
    frame.locator('#pFixture').click()
    page.locator('[data-page=waterfall]').click()
    expect(page.locator('#waterfallScope')).to_contain_text('가상 테스트')
    expect(page.locator('#waterfallChart svg')).to_be_visible()
    assert page.locator('#waterfallChart rect').count()==6
    page.locator('[data-page=portfolio]').click()
    expect(frame.locator('#pGenerate')).to_be_visible()
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#pageSelect').select_option('heatmap')
    expect(page.locator('#mainChart .heat')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    page.screenshot(path=str(ROOT/'validation/workspace-mobile.png'))
    assert not requests,requests
    assert not errors,errors
    browser.close()
print('PASS standalone workspace: overview, missing, heatmap/scatter selection, legacy detail, filter CSV, price, waterfall, portfolio, mobile, no network/JS errors')
