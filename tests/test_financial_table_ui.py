"""Synthetic financial-table checks; optional actual stored HTML is read-only."""
import os,sys,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace
from playwright.sync_api import sync_playwright,expect
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
    expect(page.locator('#financialSummary')).to_be_visible()
    expect(page.locator('.financial-cards .financial-card')).to_have_count(4)
    expect(page.locator('.financial-table tbody tr')).to_have_count(11)
    if actual:
        expect(page.locator('.financial-table thead')).to_contain_text('연결 재무(CFS) · 분기 실적')
        expect(page.locator('.financial-table thead')).to_contain_text('2025.09')
        expect(page.locator('.financial-table thead')).to_contain_text('2026.06')
        expected={'revenue':'1,714,995','operating_profit':'894,924','net_income':'716,245','total_borrowings':'224,087'}
        for key,value in expected.items():
            expect(page.locator('[data-financial-key='+key+'] td').last).to_contain_text(value)
        expect(page.locator('[data-financial-key=ebitda] td').last).to_have_text('—')
        expect(page.locator('.financial-notes')).to_contain_text('혼합 출처 추정치')
        expect(page.locator('.financial-card').last).to_contain_text('산출 범위 확인')
        assert page.locator('.financial-bars').count()==2
        page.add_style_tag(content='.mast,.workspace-bar{position:static!important}')
        page.locator('#financialSummary').screenshot(path=str(ROOT/'validation/financial-table-actual.png'))
        # A public candidate must not inherit the selected reviewed company's history.
        code=page.evaluate("WORKSPACE_DATA.discovery.snapshot.companies.find(r=>!r.legacy_available).code")
        page.locator('#researchCompany').select_option(code)
        expect(page.locator('#financialSummary')).to_contain_text('기간별 재무 이력이 연결되지 않았습니다')
        expect(page.locator('.financial-bars')).to_have_count(0)
        page.locator('#researchCompany').select_option('005930')
    else:
        expect(page.locator('#financialPeriodSelect')).to_be_visible()
        page.locator('#financialPeriodSelect').select_option('CFS-annual')
        expect(page.locator('.financial-table thead')).to_contain_text('연간 실적')
        expect(page.locator('.financial-table thead')).to_contain_text('2025.12')
    expect(page.locator('[data-financial-key=ebitda_margin]')).to_have_count(0)
    if not actual:page.locator('#financialPeriodSelect').select_option('CFS-annual')
    # All entered amounts below are explicit test inputs, including in actual HTML.
    page.locator('[data-ebitda-period]').last.click()
    page.locator('#ebitdaValue').fill('1,000.25')
    page.locator('#ebitdaNote').fill('가상 UI 검증용 입력')
    page.locator('#ebitdaForm button[type=submit]').click()
    expect(page.locator('[data-financial-key=ebitda] td').last).to_contain_text('1,000')
    expect(page.locator('[data-financial-key=ebitda] td').last).to_have_attribute('title',re.compile('사용자 직접 입력'))
    page.locator('#ebitdaValue').fill('')
    page.locator('#ebitdaForm button[type=submit]').click()
    expect(page.locator('.ebitda-status')).to_contain_text('금액을 숫자로')
    expect(page.locator('[data-financial-key=ebitda] td').last).to_contain_text('1,000')
    page.locator('#ebitdaMethod').select_option('operating')
    page.locator('#ebitdaOperatingProfit').fill('500')
    page.locator('#ebitdaDepreciation').fill('40')
    page.locator('#ebitdaAmortization').fill('10')
    expect(page.locator('#ebitdaPreview')).to_have_text('550')
    page.locator('#ebitdaForm button[type=submit]').click()
    expect(page.locator('[data-financial-key=ebitda] td').last).to_contain_text('550')
    page.reload();page.locator('[data-page=brief]').click()
    if actual:page.locator('#researchCompany').select_option('005930')
    else:page.locator('#financialPeriodSelect').select_option('CFS-annual')
    expect(page.locator('[data-financial-key=ebitda] td').last).to_contain_text('550')
    page.locator('[data-ebitda-period]').first.click()
    page.locator('#ebitdaValue').fill('0')
    page.locator('#ebitdaForm button[type=submit]').click()
    expect(page.locator('[data-financial-key=ebitda] td').first).to_contain_text('0')
    expect(page.locator('[data-financial-key=ebitda] td').last).to_contain_text('550')
    with page.expect_download() as download_event:page.locator('#ebitdaExport').click()
    download=download_event.value
    saved=ROOT/'validation/ebitda-test-inputs.json';download.save_as(saved)
    payload=json.loads(saved.read_text(encoding='utf-8'))
    assert payload['unit']=='억원' and len(payload['entries'])==2
    page.locator('[data-ebitda-period]').last.click();page.locator('#ebitdaReset').click()
    expect(page.locator('[data-financial-key=ebitda] td').last).to_have_text('—')
    page.locator('#ebitdaImport').set_input_files(str(saved))
    expect(page.locator('.ebitda-status')).to_contain_text('입력 2개 불러옴')
    expect(page.locator('[data-financial-key=ebitda] td').last).to_contain_text('550')
    bad={**payload,'unit':'원'}
    page.locator('#ebitdaImport').set_input_files({'name':'wrong-unit.json','mimeType':'application/json','buffer':json.dumps(bad).encode()})
    expect(page.locator('.ebitda-status')).to_contain_text('억원 단위')
    expect(page.locator('[data-financial-key=ebitda] td').last).to_contain_text('550')
    # Printing must retain numbers rendered as editable buttons.
    page.emulate_media(media='print')
    expect(page.locator('[data-ebitda-period]').last).to_be_visible()
    page.emulate_media(media='screen')
    # A different company must not inherit the manual amount.
    original=page.locator('#researchCompany').input_value()
    another=page.evaluate("[...document.querySelector('#researchCompany').options].find(o=>o.value!==document.querySelector('#researchCompany').value).value")
    page.locator('#researchCompany').select_option(another)
    assert '550' not in page.locator('[data-financial-key=ebitda]').inner_text()
    page.locator('#researchCompany').select_option(original)
    if not actual:page.locator('#financialPeriodSelect').select_option('CFS-annual')
    expect(page.locator('[data-financial-key=ebitda] td').last).to_contain_text('550')
    # Remove test inputs before capturing the actual source dashboard.
    page.locator('[data-ebitda-period]').first.click();page.locator('#ebitdaReset').click()
    page.locator('[data-ebitda-period]').last.click();page.locator('#ebitdaReset').click()
    page.locator('#ebitdaMethod').select_option('operating')
    expect(page.locator('#ebitdaPreview')).to_have_text('—')
    if actual:
        page.add_style_tag(content='.mast,.workspace-bar{position:static!important}')
        page.locator('#financialSummary').screenshot(path=str(ROOT/'validation/ebitda-inputs-actual.png'))
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    assert page.locator('.financial-scroll').evaluate('e=>e.scrollWidth>e.clientWidth')
    page.locator('.financial-scroll').evaluate('e=>e.scrollLeft=e.scrollWidth')
    assert page.locator('.financial-scroll').evaluate('e=>e.scrollLeft>0')
    corner=page.locator('.financial-table thead th[rowspan]').bounding_box()
    row_label=page.locator('.financial-table tbody th').first.bounding_box()
    assert abs(corner['x']-row_label['x'])<2
    page.locator('#financialSummary').screenshot(path=str(ROOT/'validation/ebitda-inputs-mobile.png'))
    assert not errors,errors
    assert not external,external
    browser.close()
print('PASS financial table '+('actual' if actual else 'fixture')+': manual/calculated EBITDA, removed margin, restore, export/import, period/company isolation, printing, 390px')
