"""Real value-tab async seam: reference bands, basis isolation and mobile layout."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
actual=os.environ.get('BAND_ACTUAL')
if actual:
    reference=json.loads(Path(actual).read_text(encoding='utf-8'))
    detail=json.loads((ROOT/'validation/current/valuation-000660-preview.json').read_text(encoding='utf-8'))
    row=dict(code=detail['code'],name=detail['name'],market=detail['market'],industry='반도체',metrics={})
    model=detail['model']
else:
    row=dict(code='900000',name='가상 기업',market='KOSPI',industry='합성',metrics={})
    model=dict(groups=[],chart=dict(bars=[],reason='합성 자료'),notes=[])
    points=[dict(period_end=d,values=dict(close=100+i*10,band1=150,band2=120,band3=90,band4=60)) for i,d in enumerate(['2026-09-30','2026-10-16'])]
    reference=dict(code=row['code'],basis='CFS',status='ready',retrieved_at='2026-10-19T12:00:00+09:00',
        bands={k:dict(labels=['15배','12배','9배','6배'],rows=points) for k in ['per','pbr']},
        quote=dict(code=row['code'],name=row['name'],per=12,pbr=2,price_time='2026-10-16T15:30:00+09:00',retrieved_at='2026-10-19T12:00:00+09:00'))

payload=json.dumps(dict(row=row,model=model,reference=reference),ensure_ascii=False).replace('<','\\u003c')
scripts='\n'.join((ROOT/'src'/n).read_text(encoding='utf-8') for n in ['icons.js','discovery_engine.js','company_detail_engine.js','company_detail_ui.js'])
boot='''const d=INPUT;const shared={isWatched:()=>false,toggleWatch(){},tables:{},ebitda:{apply:()=>({groups:[]})}};
const testUI=CompanyDetailUI.create({element:document.querySelector('#companyDetail'),rows:[d.row],models:{[d.row.code]:d.model},research:{rows:{}},meta:{data_mode:'fixture',financial_basis:'CFS',financial_period:'2026-06-30',price_date:'2026-10-19'},getCode:()=>d.row.code,setCode(){},shared,initial:{tab:'value'},loadValuation:async(code,basis)=>basis==='CFS'?d.reference:{code,basis,status:'unavailable',bands:{}}});testUI.render();'''.replace('INPUT',payload)
html='<style>body{margin:8px;font-family:sans-serif}*{box-sizing:border-box}</style><style>'+(ROOT/'src/company_detail.css').read_text(encoding='utf-8')+'</style><div id="companyDetail"></div><script>'+scripts+'\n'+boot+'</script>'
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
    page=browser.new_page();errors=[];external=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:external.append(r.url))
    page.set_content(html)
    expect(page.locator('[data-naver-band=per] svg')).to_be_visible()
    if not actual:expect(page.locator('.sd-position').first).to_contain_text('네이버 참고')
    else:assert page.evaluate("['per','pbr','pcr'].every(k=>CompanyDetailEngine.num(CompanyDetailEngine.valuation(d.row,d.model).current[k]))")
    page.locator('[data-sd-field=band][data-value=pbr]').click()
    expect(page.locator('[data-naver-band=pbr] svg')).to_be_visible()
    for width in [1440,390,320]:
        page.set_viewport_size({'width':width,'height':1000})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
    page.set_viewport_size({'width':1440,'height':1000})
    (ROOT/'validation/current').mkdir(parents=True,exist_ok=True)
    page.locator('[data-naver-band=pbr]').screenshot(path=str(ROOT/'validation/current/naver-pbr-preview.png'))
    page.locator('[data-sd-field=basis][data-value=OFS]').first.click()
    expect(page.locator('[data-naver-band]')).to_have_count(0)
    expect(page.locator('#sdContent')).to_contain_text('네이버 밴드 연결 대기')
    page.locator('[data-sd-field=basis][data-value=CFS]').first.click()
    expect(page.locator('[data-naver-band=pbr] svg')).to_be_visible()
    page.locator('[data-sd-field=band][data-value=pcr]').click()
    expect(page.locator('[data-naver-band]')).to_have_count(0)
    assert not errors,errors
    assert not external,external
    browser.close()
print('PASS Naver bands: real async UI, PER/PBR, basis isolation/failure, PCR exclusion, 1440/390/320px, external requests 0')
