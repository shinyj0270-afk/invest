"""Fictional manual holdings arithmetic and regressions in the integrated viewer."""
import json
import os
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace

results=[]
def check(name,condition):
    assert condition,name
    results.append(name)

with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
    page=browser.new_page(viewport={'width':1600,'height':1100})
    errors=[];external=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:external.append(r.url) if r.url.startswith(('http:','https:')) else None)
    page.on('dialog',lambda d:d.accept())
    artifact=os.environ.get('HOLDINGS_TEST_HTML')
    if artifact:page.goto(Path(artifact).resolve().as_uri(),timeout=60000)
    else:page.set_content(export_workspace(make_fixture()),wait_until='load')
    page.locator('[data-page=holdings]').click();f=page.frame_locator('#detailFrame')
    f.locator('#pManagement summary').click();f.locator('#pClear').click()
    asof=page.locator('#detailFrame').evaluate('e=>e.contentWindow.INVESTMENT_GET_HOLDINGS().as_of')
    f.locator('#pCode').fill('000001');f.locator('#pHoldingName').fill('가상 기업');f.locator('#pQty').fill('10');f.locator('#pCost').fill('10000')
    f.locator('#pCash').fill('200000');f.locator('#pQuote').fill('12000');f.locator('#pQuoteDate').fill(asof);f.locator('#pQuoteSource').fill('가상 입력')
    f.locator('#pSaveHolding').click()
    expect(f.locator('#pValue')).to_have_text('320,000 원')
    row=f.locator('#pHoldBody tr').first
    check('cost value profit return and weight visible',all(t in row.inner_text() for t in ['100,000','120,000','20,000','20 %','37.5 %']))
    check('unknown review does not suppress known arithmetic','판단 보류' in row.inner_text())
    expect(f.locator('#pScope')).to_be_visible()
    check('manual source and date visible','가상 입력' in row.inner_text() and asof in row.inner_text())
    page.locator('[data-page=waterfall]').click();expect(page.locator('#waterfallChart svg')).to_be_visible()
    check('stock cost plus profit reconciles','100,000 + 20,000 = 120,000' in page.locator('#waterfallChart').inner_text())
    page.locator('[data-page=holdings]').click();f.locator('[data-holding-edit="000001"]').click()
    expect(f.locator('#pQty')).to_have_value('10');expect(f.locator('#pQuote')).to_have_value('12000')
    f.locator('#pQty').fill('20');f.locator('#pCash').fill('0');f.locator('#pSaveHolding').click()
    expect(f.locator('#pValue')).to_have_text('240,000 원')
    check('same company edits instead of duplicate',f.locator('#pHoldBody tr').count()==1)
    check('zero cash produces full known stock weight','100 %' in row.inner_text())
    with page.expect_download() as dl:f.locator('#pExport').click()
    saved=json.loads(Path(dl.value.path()).read_text(encoding='utf-8'))
    check('explicit export preserves manual provenance',next(r for r in saved['research'] if r['code']=='000001')['price_source']['kind']=='manual_input' and saved['cash_krw']==0)
    f.locator('#pQuote').fill('0');f.locator('#pSaveHolding').click()
    expect(f.locator('#pValue')).to_have_text('240,000 원')
    check('invalid input keeps prior saved values','실패' in f.locator('#toast').inner_text())
    f.locator('#pCode').fill('000002')
    expect(f.locator('#pQuote')).to_have_value('');expect(f.locator('#pQuoteSource')).to_have_value('')
    check('switching code clears other company quote',f.locator('#pHoldingName').input_value()=='')
    f.locator('#pQty').fill('1');f.locator('#pCost').fill('1000');f.locator('#pSaveHolding').click()
    expect(f.locator('#pValue')).to_have_text('—')
    check('missing price explains next step','현재가 입력 필요' in f.locator('#pHoldBody').inner_text() and '000002' in f.locator('#pBookNote').inner_text())
    f.locator('#pDeleteHolding').click();f.locator('#pCash').fill('');f.locator('#pSaveCash').click()
    check('missing cash explains explicit zero','현금 미입력' in f.locator('#pBookNote').inner_text())
    f.locator('#pClear').click();f.locator('#pFile').set_input_files({'name':'roundtrip.json','mimeType':'application/json','buffer':json.dumps(saved).encode()})
    expect(f.locator('#pValue')).to_have_text('240,000 원')
    check('file roundtrip preserves manual arithmetic','가상 입력' in f.locator('#pHoldBody').inner_text())
    # Aged fictional prices must use the same configurable limit in both menus.
    f.locator('#pFixture').click()
    fixture=page.locator('#detailFrame').evaluate('e=>e.contentWindow.INVESTMENT_GET_HOLDINGS()')
    fixture['as_of']='2026-10-01'
    for r in fixture['research']:r['price_date']='2026-09-23'
    f.locator('#pFile').set_input_files({'name':'aged-fixture.json','mimeType':'application/json','buffer':json.dumps(fixture).encode()})
    expect(f.locator('#pValue')).to_have_text('—')
    check('stale quote prompts price update','가격 갱신 필요' in f.locator('#pHoldBody').inner_text())
    page.locator('[data-page=portfolio]').click();f.locator('#pPriceAge').fill('10')
    page.locator('[data-page=holdings]').click();expect(f.locator('#pValue')).to_have_text('1,150,000 원')
    page.locator('[data-page=waterfall]').click();expect(page.locator('#waterfallChart svg')).to_be_visible()
    check('waterfall honors configured age','890,000 + 60,000 = 950,000' in page.locator('#waterfallChart').inner_text())
    page.locator('[data-page=holdings]').click();f.locator('[data-review-detail="990001"]').click()
    page.locator('[data-page=portfolio]').click();f.locator('#pMax').fill('')
    page.locator('[data-page=holdings]').click()
    expect(f.locator('#pReviewCount')).to_have_text('—');expect(f.locator('#pWaitCount')).to_have_text('—')
    check('invalid policy clears old detail','설정 확인 필요' in f.locator('#pDetail').inner_text())
    page.locator('[data-page=waterfall]').click();expect(page.locator('#waterfallChart')).to_contain_text('설정')
    page.locator('[data-page=portfolio]').click();f.locator('#pMax').fill('5')
    page.locator('[data-page=holdings]').click();page.set_viewport_size({'width':390,'height':844})
    check('mobile no document overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
    check('no script errors',not errors);check('no external automatic requests',not external)
    browser.close()
print('PASS '+str(len(results))+' manual holdings UI checks'+(' (actual HTML)' if artifact else ''))
