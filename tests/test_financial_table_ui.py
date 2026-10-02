"""Synthetic financial-table checks; optional actual stored HTML is read-only."""
import os,sys,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace
from playwright.sync_api import sync_playwright,expect

def open_tools(page):
    if page.locator('#moreNavigation').get_attribute('open') is None:
        page.locator('#moreNavigation summary').click()

actual=os.environ.get('FINANCIAL_ACTUAL_HTML')
html=Path(actual).read_text(encoding='utf-8') if actual else export_workspace(make_fixture())
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
    page=browser.new_page(viewport={'width':1440,'height':1200});errors=[];external=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:external.append(r.url) if r.url.startswith('https:') else None)
    page.route('http://127.0.0.1:8799/**',lambda r:r.fulfill(body=html,content_type='text/html'))
    page.goto(Path(actual).resolve().as_uri() if actual else 'http://127.0.0.1:8799/');page.locator('[data-page=brief]').click()
    if actual:page.locator('#researchCompany').select_option('005930')
    expect(page.locator('[data-brief-metric]')).to_have_count(11)
    expect(page.locator('#financialSummary')).to_have_count(0)
    expect(page.locator('.sd-table')).to_have_count(0)
    if actual:
        page.locator('.brief-financial').screenshot(path=str(ROOT/'validation/financial-table-actual.png'))
        code=page.evaluate("WORKSPACE_DATA.discovery.snapshot.companies.find(r=>!r.legacy_available).code")
        page.locator('#researchCompany').select_option(code)
        for k in ['revenue','op','net','borrowings']:
            expect(page.locator(f'[data-brief-metric={k}] b')).to_have_text('—')
        page.locator('#researchCompany').select_option('005930')
    open_tools(page);page.locator('[data-page=company]').click();page.locator('#sd-tab-financial').click()
    page.locator('[data-sd-field=cadence][data-value=annual]').first.click()
    page.locator('#financialPeriodSelect').select_option('CFS-annual')
    expect(page.locator('#sd-statement .sd-table')).to_be_visible()
    expect(page.locator('[data-sd-account=ebitda_margin]')).to_have_count(0)
    page.locator('#ebitdaEditor summary').click()
    # All entered amounts below are explicit test inputs, including in actual HTML.
    page.locator('#ebitdaPeriod').select_option(index=page.locator('#ebitdaPeriod option').count()-1)
    page.locator('#ebitdaValue').fill('1,000.25')
    page.locator('#ebitdaNote').fill('가상 UI 검증용 입력')
    page.locator('#ebitdaForm button[type=submit]').click()
    expect(page.locator('[data-sd-account=ebitda] td').last).to_contain_text('1,000')
    expect(page.locator('[data-sd-account=ebitda] td').last).to_have_attribute('title',re.compile('사용자 직접 입력'))
    page.locator('#ebitdaValue').fill('')
    page.locator('#ebitdaForm button[type=submit]').click()
    expect(page.locator('.ebitda-status')).to_contain_text('금액을 숫자로')
    expect(page.locator('[data-sd-account=ebitda] td').last).to_contain_text('1,000')
    page.locator('#ebitdaMethod').select_option('operating')
    page.locator('#ebitdaOperatingProfit').fill('500')
    page.locator('#ebitdaDepreciation').fill('40')
    page.locator('#ebitdaAmortization').fill('10')
    expect(page.locator('#ebitdaPreview')).to_have_text('550')
    page.locator('#ebitdaForm button[type=submit]').click()
    expect(page.locator('[data-sd-account=ebitda] td').last).to_contain_text('550')
    page.reload();open_tools(page);page.locator('[data-page=company]').click();page.locator('#sd-tab-financial').click()
    if actual:page.locator('#sdCompany').select_option('005930')
    page.locator('#financialPeriodSelect').select_option('CFS-annual')
    page.locator('#ebitdaEditor').evaluate("e=>e.open=true")
    expect(page.locator('[data-sd-account=ebitda] td').last).to_contain_text('550')
    page.locator('#ebitdaPeriod').select_option(index=0)
    page.locator('#ebitdaValue').fill('0')
    page.locator('#ebitdaForm button[type=submit]').click()
    expect(page.locator('[data-sd-account=ebitda] td').first).to_contain_text('0')
    expect(page.locator('[data-sd-account=ebitda] td').last).to_contain_text('550')
    with page.expect_download() as download_event:page.locator('#ebitdaExport').click()
    download=download_event.value
    saved=ROOT/'validation/ebitda-test-inputs.json';download.save_as(saved)
    payload=json.loads(saved.read_text(encoding='utf-8'))
    assert payload['unit']=='억원' and len(payload['entries'])==2
    page.locator('#ebitdaPeriod').select_option(index=page.locator('#ebitdaPeriod option').count()-1);page.locator('#ebitdaReset').click()
    expect(page.locator('[data-sd-account=ebitda] td').last).to_have_text('—')
    page.locator('#ebitdaImport').set_input_files(str(saved))
    expect(page.locator('.ebitda-status')).to_contain_text('입력 2개 불러옴')
    expect(page.locator('[data-sd-account=ebitda] td').last).to_contain_text('550')
    bad={**payload,'unit':'원'}
    page.locator('#ebitdaImport').set_input_files({'name':'wrong-unit.json','mimeType':'application/json','buffer':json.dumps(bad).encode()})
    expect(page.locator('.ebitda-status')).to_contain_text('억원 단위')
    expect(page.locator('[data-sd-account=ebitda] td').last).to_contain_text('550')
    # Printing must retain numbers rendered as editable buttons.
    page.emulate_media(media='print')
    expect(page.locator('[data-sd-account=ebitda] td').last).to_be_visible()
    page.emulate_media(media='screen')
    # A different company must not inherit the manual amount.
    original=page.locator('#sdCompany').input_value()
    another=page.evaluate("[...document.querySelector('#sdCompany').options].find(o=>o.value!==document.querySelector('#sdCompany').value).value")
    page.locator('#sdCompany').select_option(another)
    assert '550' not in page.locator('[data-sd-account=ebitda]').inner_text()
    page.locator('#sdCompany').select_option(original)
    page.locator('#financialPeriodSelect').select_option('CFS-annual')
    expect(page.locator('[data-sd-account=ebitda] td').last).to_contain_text('550')
    if not page.locator('#ebitdaEditor').evaluate('e=>e.open'):page.locator('#ebitdaEditor summary').click()
    # Remove test inputs before capturing the actual source dashboard.
    page.locator('#ebitdaPeriod').select_option(index=0);page.locator('#ebitdaReset').click()
    page.locator('#ebitdaPeriod').select_option(index=page.locator('#ebitdaPeriod option').count()-1);page.locator('#ebitdaReset').click()
    page.locator('#ebitdaMethod').select_option('operating')
    expect(page.locator('#ebitdaPreview')).to_have_text('—')
    if actual:
        page.add_style_tag(content='.mast,.workspace-bar{position:static!important}')
        page.locator('#sd-statement').screenshot(path=str(ROOT/'validation/ebitda-inputs-actual.png'))
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    assert page.locator('#sd-statement .sd-table-scroll').evaluate('e=>e.scrollWidth>e.clientWidth')
    page.locator('#sd-statement .sd-table-scroll').evaluate('e=>e.scrollLeft=e.scrollWidth')
    assert page.locator('#sd-statement .sd-table-scroll').evaluate('e=>e.scrollLeft>0')
    corner=page.locator('#sd-statement .sd-table thead th:first-child').bounding_box()
    row_label=page.locator('#sd-statement .sd-table tbody th').first.bounding_box()
    assert abs(corner['x']-row_label['x'])<2
    page.locator('#sd-statement').screenshot(path=str(ROOT/'validation/ebitda-inputs-mobile.png'))
    assert not errors,errors
    assert not external,external
    browser.close()
print('PASS financial table '+('actual' if actual else 'fixture')+': manual/calculated EBITDA, removed margin, restore, export/import, period/company isolation, printing, 390px')
