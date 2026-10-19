"""Real value-tab async seam: reference bands, basis isolation and mobile layout."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
actual=os.environ.get('NICE_ACTUAL')
row=dict(code='900000',name='가상기업',market='KOSPI',industry='합성',metrics={})
model=dict(groups=[],chart=dict(bars=[],reason='합성 자료'),notes=[])
reference=dict(code=row['code'],name=row['name'],basis='CFS',currency='KRW',cadence='annual',status='ready',source='NICE 합성',source_url='https://www.nicerating.com',retrieved_at='2026-10-19',columns=[dict(period_end='2025-12-31',values=dict(total_borrowings=30,net_borrowings=-5,debt_ratio=50))])
if actual:
    reference=json.loads(Path(actual).read_text(encoding='utf-8'))
    detail=json.loads((ROOT/'validation/current/valuation-000660-preview.json').read_text(encoding='utf-8'))
    row=dict(code=detail['code'],name=detail['name'],market=detail['market'],industry='반도체',metrics={})
    model=detail['model']

payload=json.dumps(dict(row=row,model=model,reference=reference),ensure_ascii=False).replace('<','\\u003c')
scripts='\n'.join((ROOT/'src'/n).read_text(encoding='utf-8') for n in ['icons.js','ebitda_editor.js','discovery_engine.js','company_detail_engine.js','company_detail_ui.js'])
boot='''const d=INPUT;const shared={isWatched:()=>false,toggleWatch(){},tables:{},ebitda:{apply:()=>({groups:[]})}};
const testUI=CompanyDetailUI.create({element:document.querySelector('#companyDetail'),rows:[d.row],models:{[d.row.code]:d.model},research:{rows:{}},meta:{data_mode:'fixture',financial_basis:'CFS',financial_period:'2026-06-30',price_date:'2026-10-19'},getCode:()=>d.row.code,setCode(){},shared,initial:{tab:'financial'},loadFinancial:async(code,basis)=>{await new Promise(resolve=>setTimeout(resolve,100));return basis==='CFS'?d.reference:{code,basis,status:'unavailable',columns:[]};}});testUI.render();'''.replace('INPUT',payload)
html='<style>body{margin:8px;font-family:sans-serif}*{box-sizing:border-box}</style><style>'+(ROOT/'src/company_detail.css').read_text(encoding='utf-8')+'</style><div id="companyDetail"></div><script>'+scripts+'\n'+boot+'</script>'
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
    page=browser.new_page();errors=[];external=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:external.append(r.url))
    page.set_content(html)
    page.evaluate("const input=document.createElement('input');input.id='preserved-draft';input.value='unsaved draft';document.querySelector('#sd-statement').append(input);")
    expect(page.locator('#sd-financial-analysis')).to_contain_text('NICE 공개 재무 연결됨')
    expect(page.locator('[data-stability=net_borrowings]')).to_contain_text('-101,844' if actual else '-5')
    expect(page.locator('#preserved-draft')).to_have_value('unsaved draft')
    assert page.evaluate("document.querySelector('#sd-financial-analysis').compareDocumentPosition(document.querySelector('#sd-statement')) & Node.DOCUMENT_POSITION_FOLLOWING")
    for width in [1440,390,320]:
        page.set_viewport_size({'width':width,'height':1000})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
    page.set_viewport_size({'width':1440,'height':1100})
    (ROOT/'validation/current').mkdir(parents=True,exist_ok=True)
    page.locator('#sd-financial-analysis').screenshot(path=str(ROOT/'validation/current/nice-financial-preview.png'))
    page.locator('[data-sd-field=basis][data-value=OFS]').first.click()
    expect(page.locator('#sd-financial-analysis')).to_contain_text('NICE 공개 재무 연결 대기')
    expect(page.locator('#sd-financial-analysis sup')).to_have_count(0)
    page.locator('[data-sd-field=basis][data-value=CFS]').first.click()
    expect(page.locator('#sd-financial-analysis')).to_contain_text('NICE 공개 재무 연결됨')
    assert not errors,errors
    assert not external,external
    browser.close()
print('PASS financial analysis: async data, before statements, basis isolation, 1440/390/320px, no JS errors')
