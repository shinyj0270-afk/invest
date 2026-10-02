"""Four tab navigation, data boundaries and shared input checks, with no retrieval."""
import os,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace
from playwright.sync_api import sync_playwright,expect

def open_tools(page):
    if page.locator('#moreNavigation').get_attribute('open') is None:
        page.locator('#moreNavigation summary').click()

actual=os.environ.get('DETAIL_ACTUAL_HTML')
if actual:html=Path(actual).read_text(encoding='utf-8')
else:
    snapshot=make_fixture()
    for r in snapshot['companies']:
        for p in r['prices']:p.update(final=True,open=p['close']*.995)
    html=export_workspace(snapshot)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
    page=browser.new_page(viewport={'width':1600,'height':1100});errors=[];external=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:external.append(r.url) if r.url.startswith('https:') else None)
    page.route('http://127.0.0.1:8799/**',lambda r:r.fulfill(body=html,content_type='text/html'))
    page.goto(Path(actual).resolve().as_uri() if actual else 'http://127.0.0.1:8799/')
    open_tools(page);page.locator('[data-page=company]').click()
    if actual:page.locator('#sdCompany').select_option('000660')
    original=page.locator('#sdCompany').input_value()
    expect(page.locator('#companyDetail')).to_be_visible()
    expect(page.locator('[role=tab]')).to_have_count(4)
    expect(page.locator('.sd-price-plot')).to_be_visible()
    expect(page.locator('.sd-chart-readout')).to_contain_text('OHLC')
    page.locator('[data-sd-field=chart][data-value=month]').click()
    expect(page.locator('[data-sd-field=chart][data-value=month]')).to_have_attribute('aria-pressed','true')
    page.locator('[data-sd-field=chart][data-value=week]').click()
    expect(page.locator('[data-sd-field=chart][data-value=week]')).to_have_attribute('aria-pressed','true')
    page.locator('[data-sd-toggle=bb]').click();page.locator('[data-sd-toggle=env]').click()
    expect(page.locator('[data-sd-toggle=bb]')).to_have_attribute('aria-pressed','true')
    expect(page.locator('[data-sd-toggle=env]')).to_have_attribute('aria-pressed','true')
    page.locator('#sdChartRange').select_option('all')
    page.locator('#sdSettings').click();page.locator('[data-sd-metric=roe]').uncheck()
    page.locator('#sdSettingsClose').click();assert 'ROE' not in page.locator('.sd-metrics').inner_text()
    page.locator('#sdWatch').click();expect(page.locator('#sdWatch')).to_have_attribute('aria-pressed','true')
    for tab in ['business','financial','value']:
        page.locator('#sd-tab-'+tab).click();expect(page.locator('#sdContent')).to_be_visible()
    page.locator('#sd-tab-financial').click()
    page.locator('[data-sd-field=cadence][data-value=quarter]').first.click()
    expect(page.locator('#sd-statement .sd-table')).to_be_visible()
    page.locator('[data-sd-trend=revenue]').click();expect(page.locator('#sdRowTrend svg')).to_be_visible()
    page.locator('[data-sd-field=statement][data-value=balance]').click()
    expect(page.locator('#sd-statement .sd-table')).to_contain_text('자本'.replace('本','본'))
    page.locator('[data-sd-field=statement][data-value=cash]').click()
    expect(page.locator('#sd-statement')).to_contain_text('영업활동 현금흐름')
    page.locator('[data-sd-field=statement][data-value=income]').click()
    page.locator('[data-sd-field=basis][data-value=OFS]').first.click()
    if actual:expect(page.locator('#sd-statement .sd-table')).to_be_visible()
    else:expect(page.locator('#sd-statement')).to_contain_text('선택한 회계기준')
    page.locator('[data-sd-field=basis][data-value=CFS]').first.click()
    page.locator('[data-sd-field=statement][data-value=income]').click()
    page.locator('#ebitdaEditor summary').click()
    page.locator('#ebitdaValue').fill('1234.25');page.locator('#ebitdaNote').fill('가상 UI 검사 입력')
    page.locator('#ebitdaForm button[type=submit]').click()
    expect(page.locator('#sd-statement .sd-table')).to_contain_text('1,234')
    page.locator('[data-page=brief]').click()
    expect(page.locator('[data-brief-metric]')).to_have_count(11)
    expect(page.locator('#financialSummary')).to_have_count(0)
    expect(page.locator(f'[data-watch="{original}"]')).to_have_attribute('aria-pressed','true')
    open_tools(page);page.locator('[data-page=company]').click();page.locator('#sd-tab-financial').click()
    expect(page.locator('[data-sd-account=ebitda] td').last).to_contain_text('1,234')
    page.locator('#ebitdaValue').fill('2222');page.locator('#ebitdaForm button[type=submit]').click()
    open_tools(page);page.locator('[data-page=company]').click();page.locator('#sd-tab-financial').click()
    expect(page.locator('#sd-statement .sd-table')).to_contain_text('2,222')
    another=page.evaluate("[...document.querySelector('#sdCompany').options].find(o=>o.value!==document.querySelector('#sdCompany').value).value")
    page.locator('#sdCompany').select_option(another)
    assert '2,222' not in page.locator('[data-sd-account=ebitda]').inner_text()
    page.locator('#sdCompany').select_option(original)
    page.reload();open_tools(page);page.locator('[data-page=company]').click()
    if actual:page.locator('#sdCompany').select_option(original)
    expect(page.locator('#sd-tab-financial')).to_have_attribute('aria-selected','true')
    expect(page.locator('[data-sd-account=ebitda] td').last).to_contain_text('2,222')
    # Restore all synthetic manual values and watch marks before captures.
    if not page.locator('#ebitdaEditor').evaluate('e=>e.open'):page.locator('#ebitdaEditor summary').click()
    page.locator('#ebitdaReset').click()
    page.locator('#sdWatch').click()
    page.locator('#sd-tab-summary').click();page.locator('[data-sd-field=chart][data-value=day]').click()
    expect(page.locator('[data-sd-toggle=bb]')).to_have_attribute('aria-pressed','true')
    expect(page.locator('[data-sd-toggle=env]')).to_have_attribute('aria-pressed','true')
    page.locator('#sdChartRange').select_option('126')
    page.locator('#sdSettings').click();page.locator('#sdSettingsReset').click();page.locator('#sdSettingsClose').click()
    page.locator('[data-sd-toggle=bb]').click();page.locator('[data-sd-toggle=env]').click()
    page.add_style_tag(content='.mast,.workspace-bar{position:static!important}')
    page.locator('#companyDetail').screenshot(path=str(ROOT/'validation/company-detail-actual.png' if actual else ROOT/'validation/company-detail-fixture.png'))
    if actual:
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(ROOT/'validation/company-detail-summary-view.png'))
    for tab in ['business','financial','value']:
        page.locator('#sd-tab-'+tab).click()
        if actual:page.locator('#companyDetail').screenshot(path=str(ROOT/('validation/company-detail-'+tab+'.png')))
    if actual:
        page.locator('#sd-tab-financial').click()
        for basis in ['CFS','OFS']:
            page.locator(f'[data-sd-field=basis][data-value={basis}]').first.click()
            for cadence in ['ttm','annual','quarter']:
                page.locator(f'[data-sd-field=cadence][data-value={cadence}]').first.click()
                for statement in ['income','balance','cash']:
                    page.locator(f'[data-sd-field=statement][data-value={statement}]').click()
                    expect(page.locator('#sd-statement .sd-table')).to_be_visible()
                    key={'income':'revenue','balance':'assets','cash':'ocf'}[statement]
                    assert page.locator(f'[data-sd-account={key}] td').last.inner_text()!='—'
        page.locator('#sd-tab-value').click()
        expect(page.locator('.sd-position')).to_have_count(3)
        assert page.locator('.sd-histogram').count()==1
        before=page.locator('#sdContent').inner_text()
        page.locator('#sdRequiredReturn').fill('12');page.locator('#sdRequiredReturn').press('Tab')
        assert page.locator('#sdRequiredReturn').input_value()=='12'
        assert page.locator('#sdContent').inner_text()!=before
        page.locator('[data-sd-field=band][data-value=pcr]').click()
        expect(page.locator('.sd-histogram')).to_be_visible()
        page.locator('#sdRequiredReturn').fill('10');page.locator('#sdRequiredReturn').press('Tab')
        page.locator('[data-sd-field=band][data-value=per]').click()
        page.locator('#sd-tab-financial').click()
        page.locator('[data-sd-field=basis][data-value=CFS]').first.click()
        page.locator('[data-sd-field=statement][data-value=income]').click()
        page.locator('[data-sd-field=cadence][data-value=quarter]').first.click()
        page.locator('#companyDetail').screenshot(path=str(ROOT/'validation/company-detail-financial.png'))
        page.locator('#sd-tab-value').click()
        page.locator('#companyDetail').screenshot(path=str(ROOT/'validation/company-detail-value.png'))
    # The old condition-search result now opens the same native detail.
    open_tools(page);page.locator('[data-page=screen]').click();frame=page.frame_locator('#detailFrame')
    frame.locator('[data-company]').first.click();expect(page.locator('#companyDetail')).to_be_visible()
    page.locator('#sd-tab-summary').click()
    page.locator('#sd-tab-summary').focus();page.locator('#sd-tab-summary').press('ArrowRight')
    expect(page.locator('#sd-tab-business')).to_have_attribute('aria-selected','true')
    page.set_viewport_size({'width':390,'height':844})
    for tab in ['summary','business','financial','value']:
        page.locator('#sd-tab-'+tab).click()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),tab
    page.locator('#sd-tab-summary').click()
    if actual:page.locator('#sdCompany').select_option(original)
    page.locator('#companyDetail').screenshot(path=str(ROOT/('validation/company-detail-mobile-actual.png' if actual else 'validation/company-detail-mobile-fixture.png')))
    assert not errors,errors;assert not external,external
    browser.close()
print('PASS detail: four tabs, OHLC/day/week/month controls, shared EBITDA/watch, period/basis/statement boundaries, setting/reload, legacy result links, keyboard/mobile, offline')
