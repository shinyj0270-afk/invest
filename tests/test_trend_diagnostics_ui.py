"""Research diagnostics and chart range controls with explicit fixture data."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace
from playwright.sync_api import sync_playwright,expect
from tools.browser_runtime import chromium_options

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,**chromium_options())
    page=browser.new_page(viewport={'width':1440,'height':1050});errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    snapshot=make_fixture()
    for row in snapshot['companies']:
        for bar in row['prices']:bar['final']=True
    for bars in snapshot['benchmarks'].values():
        for bar in bars:bar.update(final=True,venue='KRX')
    page.set_content(export_workspace(snapshot),wait_until='load')
    page.locator('[data-page=brief]').click()
    page.locator('#research [data-research-go=trend]').first.click()
    expect(page.locator('#trendDiagnostics')).to_be_visible()
    expect(page.locator('[data-trend-health]')).to_contain_text('/8')
    page.locator('button[data-trend-range="63"]').click()
    expect(page.locator('button[data-trend-range="63"]')).to_have_attribute('aria-pressed','true')
    expect(page.locator('#research')).to_contain_text('63개 완료 거래일')
    page.locator('button[data-trend-range="253"]').click()
    expect(page.locator('#research')).to_contain_text('253개 완료 거래일')
    expect(page.locator('[data-trend-health]')).to_contain_text('/8')
    page.locator('#trendDiagnostics summary').first.click()
    assert page.locator('[data-trend-check]').count()==8
    expect(page.locator('[data-trend-check=rs]')).to_be_visible()
    expect(page.locator('#trendDiagnostics')).to_contain_text('연구용 변형')
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not errors,errors
    browser.close()
print('PASS fixture trend diagnostics, 8 checks, 3/12 month controls, stable conditions, mobile, no JS errors')
