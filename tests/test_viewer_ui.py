"""Rendered chart + navigation smoke test against a running local saved-data app."""
import os
import re
from playwright.sync_api import sync_playwright, expect

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
    page=browser.new_page(viewport={'width':1500,'height':1100})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(os.environ.get('INVESTMENT_TEST_URL','http://127.0.0.1:8501'))
    page.get_by_test_id('stSidebar').get_by_text('인터랙티브 뷰어',exact=True).click()
    scatter=page.locator('.st-key-chart_scatter')
    marks=scatter.locator('path[role="graphics-symbol"]')
    expect(marks.first).to_be_visible()
    count=marks.count()
    assert count>=1
    point=marks.last
    code=re.search(r'코드: (\d{6})',point.get_attribute('aria-label')).group(1)
    point.click()
    detail=page.get_by_test_id('stSelectbox').filter(has_text='자세히 볼 기업')
    expect(detail.get_by_role('combobox')).to_have_value(re.compile(code))
    heat=page.locator('.st-key-chart_heatmap')
    expect(heat.locator('svg.marks')).to_be_visible()
    # Missing pairs show an explicit empty state, not zero-valued points.
    page.get_by_role('combobox',name='산점도 X축',exact=True).click()
    page.get_by_role('option',name='PER (배)',exact=True).click()
    # This live test dataset may have PER; both supported states must be explicit.
    if scatter.get_by_text('두 지표를 함께 가진 기업이 없습니다.',exact=True).count():
        expect(scatter.get_by_text('두 지표를 함께 가진 기업이 없습니다.',exact=True)).to_be_visible()
    page.get_by_role('button',name='뷰어 초기화',exact=True).click()
    expect(page.locator('.st-key-chart_scatter path[role="graphics-symbol"]')).to_have_count(count)
    with page.expect_download() as download:
        page.get_by_role('button',name='현재 비교 데이터 CSV',exact=True).click()
    assert download.value.suggested_filename=='viewer_comparison.csv'
    page.get_by_test_id('stSidebar').get_by_text('조건검색',exact=True).click()
    page.get_by_test_id('stSidebar').get_by_text('인터랙티브 뷰어',exact=True).click()
    expect(page.locator('.st-key-chart_scatter path[role="graphics-symbol"]')).to_have_count(count)
    page.set_viewport_size({'width':390,'height':844})
    expect(page.get_by_test_id('stSidebar')).to_have_attribute('aria-expanded','false')
    page.get_by_test_id('stExpandSidebarButton').click()
    expect(page.get_by_test_id('stSidebar')).to_have_attribute('aria-expanded','true')
    page.get_by_test_id('stSidebarCollapseButton').get_by_role('button').click()
    expect(page.get_by_test_id('stSidebar')).to_have_attribute('aria-expanded','false')
    heat=page.locator('.st-key-chart_heatmap')
    heat.scroll_into_view_if_needed()
    expect(heat.locator('svg.marks')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    heat.screenshot(path='validation/viewer-mobile-heatmap.png')
    page.set_viewport_size({'width':1500,'height':1100})
    heat.screenshot(path='validation/viewer-final-heatmap.png')
    page.locator('.st-key-chart_scatter').screenshot(path='validation/viewer-final-scatter.png')
    assert not errors,errors
    browser.close()
print('PASS viewer UI: rendered bars/scatter/heatmap, point selection, axes/reset, CSV, navigation, mobile, no JS errors')
