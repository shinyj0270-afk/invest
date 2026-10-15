"""Offline synthetic browser checks of the reference-style exported workspace."""
import os
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace
from playwright.sync_api import sync_playwright,expect

def open_tools(page):
    if page.locator('#moreNavigation summary').count():
        page.locator('#moreNavigation summary').click()


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
    page.locator('[data-page=overview]').click()
    expect(page.locator('#comparisonTable')).to_contain_text('기업 찾기에서 비교 담기')
    expect(page.locator('#comparisonPicker')).to_be_visible()
    page.locator('#comparisonFind').click()
    # Add five different candidates across finder pages/filters without changing watch state.
    for code in ('900001','900002','900003','900004','900005'):
        page.locator(f'[data-comparison="{code}"]').click()
    page.locator('[data-comparison="900006"]').click()
    expect(page.locator('#researchNotice')).to_contain_text('최대 5개')
    expect(page.locator('[data-open-comparison]')).to_contain_text('5/5')
    page.locator('[data-open-comparison]').click()
    expect(page.locator('#comparisonTable tbody tr')).to_have_count(5)
    expect(page.locator('#comparisonPrices svg')).to_have_count(5)
    expect(page.locator('#comparisonTable')).to_contain_text('—')
    expect(page.locator('#comparisonTable')).to_contain_text('CFS')
    # Remove and add directly on the basic screen; no hidden filter controls.
    page.locator('[data-remove-comparison="900001"]').click()
    page.locator('#comparisonQuery').fill('900006')
    page.locator('[data-add-comparison="900006"]').click()
    expect(page.locator('#comparisonTable tbody tr')).to_have_count(5)
    with page.expect_download() as downloaded:page.locator('#exportCsv').click()
    content=Path(downloaded.value.path()).read_text(encoding='utf-8-sig')
    assert '900006' in content and '900001' not in content
    # All advanced charts share the explicit selection.
    page.locator('#contextNavigation summary').click()
    page.locator('[data-context-page=heatmap]').click()
    expect(page.locator('#mainChart tbody tr')).to_have_count(5)
    page.locator('[data-context-page=scatter]').click()
    assert page.locator('#mainChart circle').count()==5
    page.locator('[data-page=overview]').click()
    expect(page.locator('#comparisonTable tbody tr')).to_have_count(5)
    page.locator('[data-page=finder]').click()
    expect(page.locator('[data-comparison="900006"]')).to_have_attribute('aria-pressed','true')
    page.locator('[data-legacy-screen]').locator('..').locator('summary').click()
    page.locator('[data-legacy-screen]').click()
    expect(page.locator('#legacy')).to_be_visible()
    frame=page.frame_locator('#detailFrame')
    page.locator('[data-page=holdings]').click()
    frame.locator('#pManagement summary').click();frame.locator('#pFixture').click()
    open_tools(page);page.locator('[data-page=holdings]').click();page.locator('[data-context-page=waterfall]').click()
    expect(page.locator('#waterfallScope')).to_contain_text('가상 테스트')
    expect(page.locator('#waterfallChart svg')).to_be_visible()
    assert page.locator('#waterfallChart rect').count()==6
    page.locator('#pageSelect').select_option('portfolio',force=True)
    expect(frame.locator('#pGenerate')).to_be_visible()
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#pageSelect').select_option('heatmap')
    expect(page.locator('#mainChart .heat')).to_be_visible()
    page.locator('#pageSelect').select_option('overview')
    expect(page.locator('#comparisonPicker')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    for width in (390,320):
        page.set_viewport_size({'width':width,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    (ROOT/'validation/current/compare-flow').mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(ROOT/'validation/current/compare-flow/mobile.png'))
    assert not requests,requests
    assert not errors,errors
    browser.close()
print('PASS finder comparison basket, five-company limit, explicit add/remove, missing data, shared charts/CSV, advanced screening, holdings, mobile, no network/JS errors')
