"""Interactive trend chart with explicit synthetic fixture prices only."""
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
    page.on('pageerror',lambda e:errors.append(str(e)))
    snapshot=make_fixture()
    for row in snapshot['companies']:
        for bar in row['prices']:bar.update(final=True,open=bar['close'])
    for bars in snapshot['benchmarks'].values():
        for bar in bars:bar.update(final=True,venue='KRX')
    page.set_content(export_workspace(snapshot),wait_until='load')
    page.locator('[data-page=brief]').click()
    page.locator('#research [data-research-go=trend]').first.click()
    expect(page.locator('.tc-price-svg')).to_be_visible()
    page.locator('[data-tc-mode]').select_option('candle')
    expect(page.locator('[data-tc-mode]')).to_have_value('candle')
    page.locator('[data-chart-hit]').scroll_into_view_if_needed()
    hit=page.locator('[data-chart-hit]').bounding_box()
    page.mouse.move(hit['x']+hit['width']*.6,hit['y']+50)
    expect(page.locator('.tc-tooltip')).to_be_visible()
    expect(page.locator('.tc-tooltip')).to_contain_text('시 ')
    page.locator('[data-tc-mode]').select_option('line')
    page.locator('[data-tc-series=ma200]').click()
    expect(page.locator('[data-tc-series=ma200]')).to_have_attribute('aria-pressed','false')
    page.locator('[data-trend-range="63"]').click()
    expect(page.locator('.tc-readout')).to_contain_text('63개 완료 거래일')
    start=page.locator('[data-tc-date=start]').input_value()
    page.locator('[data-tc-handle=start]').scroll_into_view_if_needed()
    handle=page.locator('[data-tc-handle=start]').bounding_box()
    page.mouse.move(handle['x']+5,handle['y']+15);page.mouse.down();page.mouse.move(handle['x']+80,handle['y']+15,steps=5);page.mouse.up()
    assert page.locator('[data-tc-date=start]').input_value()!=start
    saved=page.locator('[data-tc-date=start]').input_value()
    page.locator('#research [data-research-go=brief]').first.click()
    expect(page.locator('[data-tc-date=start]')).to_have_value(saved)
    expect(page.locator('[data-tc-series=ma200]')).to_have_attribute('aria-pressed','false')
    for width in [390,320]:
        page.set_viewport_size({'width':width,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
    # Missing OHLC must not be fabricated, and earlier MA values survive a trimmed series.
    page.goto('about:blank')
    page.set_content('<div id="chart" style="width:300px"></div>')
    page.add_script_tag(content=(ROOT/'src/trend_chart_ui.js').read_text(encoding='utf-8'))
    page.evaluate("""TrendChartUI.mount(document.querySelector('#chart'),{technical:{as_of:'2026-10-01',series:[{date:'2026-09-30',close:100,ma200:80,volume:null},{date:'2026-10-01',close:110,ma200:81,volume:null}]},state:{}})""")
    expect(page.locator('[data-tc-mode] option[value=candle]')).to_have_attribute('disabled','')
    paths=page.locator('.tc-price-svg path').evaluate_all('(els)=>els.map(e=>e.getAttribute("d"))')
    assert len([value for value in paths if value.strip()])==2,paths
    assert not errors,errors
    browser.close()
print('PASS fixture candles, hover, legend, periods, range drag, view state, 390/320px, JS errors0')
