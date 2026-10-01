import os,sys,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace,script_json
from playwright.sync_api import sync_playwright,expect
actual=os.environ.get('ADVANCED_ACTUAL_HTML')
html=export_workspace(make_fixture())
population=8
if os.environ.get("ADVANCED_SCALE_FIXTURE"):
    payload=json.JSONDecoder().raw_decode(html.split('const WORKSPACE_DATA=',1)[1])[0]
    from copy import deepcopy
    base=payload['snapshot']['companies'][0]
    candidates=[]
    for i in range(2455):
        row=deepcopy(base);row.update(code=str(100000+i),name="가상후보"+str(i),prices=[],legacy_available=False)
        candidates.append(row)
    payload['discovery']={'snapshot':{'meta':dict(payload['snapshot']['meta'],discovery=True),'companies':candidates},'research':{'rows':{}}}
    tail=html.split('const WORKSPACE_DATA=',1)[1]
    html=html.split('const WORKSPACE_DATA=',1)[0]+'const WORKSPACE_DATA='+script_json(payload)+tail[tail.index(';</script>'):]
    population=2455
if actual:
    old=Path(actual).read_text(encoding='utf-8')
    payload=json.JSONDecoder().raw_decode(old.split('const WORKSPACE_DATA=',1)[1])[0]
    html=html.split('const WORKSPACE_DATA=',1)[0]+'const WORKSPACE_DATA='+script_json(payload)+html.split('const WORKSPACE_DATA=',1)[1][html.split('const WORKSPACE_DATA=',1)[1].index(';</script>'):]
    population=len(payload['discovery']['snapshot']['companies'])
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    # HTTP origin gives sessionStorage a real same-origin refresh contract. No data leaves loopback.
    page.route('http://127.0.0.1:8799/**',lambda route:route.fulfill(status=200,content_type='text/html',body=html))
    page.goto('http://127.0.0.1:8799/');page.locator('[data-page=advanced]').click()
    expect(page.locator('#avCount')).to_contain_text(f'원본 모집단 {population}개')
    initial=float(page.locator('#advanced').get_attribute('data-render-ms'));assert initial<2000
    assert page.locator('.av-density>div').count()==100
    assert page.locator('[data-av-code]').count()<=25
    first=page.locator('[data-av-code]').first;name=first.inner_text().split(' · ')[0];first.click()
    expect(page.locator('#avCompany')).to_contain_text(name)
    if page.locator('[data-av-code]').count()>1:
        second=page.locator('[data-av-code]').nth(1);second_name=second.inner_text().split(' · ')[0];second.click();expect(page.locator('#avCompany')).to_contain_text(second_name)
    page.locator('#avFilters [name=query]').fill(name);page.locator('#avFilters button').first.click()
    expect(page.locator('#avCount')).to_contain_text(f'결과 1 / 원본 모집단 {population}개')
    page.reload();expect(page.locator('#advanced')).to_be_visible();expect(page.locator('#avFilters [name=query]')).to_have_value(name)
    page.locator('#avReset').click();expect(page.locator('#avCount')).to_contain_text(f'결과 {population} /')
    elapsed=float(page.locator('#advanced').get_attribute('data-render-ms'));assert elapsed<2000,elapsed
    nodes=page.locator('#advanced *').count();assert nodes<1600,nodes
    page.locator('[data-av-node]').first.click();expect(page.locator('#avNode')).to_contain_text('unavailable')
    # Verify the live payload stays separate from the reviewed holdings/detail contract.
    if actual:
        expect(page.locator('.av-strip')).to_contain_text('실제 저장자료')
        assert page.evaluate('WORKSPACE_DATA.analysis_snapshot.companies.length') == len(payload['analysis_snapshot']['companies'])
        assert page.evaluate('WORKSPACE_DATA.discovery.coverage.rs_ready') == payload['discovery']['coverage']['rs_ready']
        expect(page.locator('#avHoldings')).to_contain_text('브라우저 보유 입력')
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(ROOT/'validation/advanced-actual-desktop.png'))
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.screenshot(path=str(ROOT/'validation/advanced-actual-mobile.png'))
        page.set_viewport_size({'width':1440,'height':1000})
    page.locator('#avReview').click();frame=page.frame_locator('#detailFrame')
    # The real payload already has reviewed research, so switching to a fixture needs confirmation.
    page.once('dialog', lambda dialog: dialog.accept())
    frame.locator('#pFixture').click()
    page.locator('[data-page=portfolio]').click()
    frame.locator('#pConfirm').check();frame.locator('#pGenerate').click()
    # This synthetic holdings input is browser-local and explicitly labelled as a fixture.
    expected=page.evaluate('''() => {
      const w=document.querySelector('#detailFrame').contentWindow;
      const data=w.INVESTMENT_GET_HOLDINGS(),policy=w.INVESTMENT_GET_POLICY();
      const review=PortfolioEngine.reviewHoldings(data,policy),proposal=PortfolioEngine.propose(data,policy);
      const formatted=v=>typeof v==='number'?v.toLocaleString('ko-KR',{maximumFractionDigits:2}):'unknown';
      return {rows:review.rows.map(r=>({name:r.name,label:r.label,weight:formatted(r.weight_pct),pnl:formatted(r.pnl_krw)})),
              status:proposal.status,items:proposal.items.map(i=>({...i,displayWeight:formatted(i.weight_pct)})),cash:formatted(proposal.cash_pct)};
    }''')
    assert expected['status']=='MODEL_PROPOSAL',expected['status']
    assert 0<len(expected['items'])<=5
    page.locator('[data-page=advanced]').click();expect(page.locator('#avHoldings')).to_contain_text('가상 테스트')
    assert page.locator('.av-holding').count()==len(expected['rows'])
    expect(page.locator('#avHoldings')).to_contain_text(expected['status'])
    for i,row in enumerate(expected['rows']):
        card=page.locator('.av-holding').nth(i)
        expect(card).to_contain_text(row['name']+' · '+row['label'])
        expect(card).to_contain_text('비중 '+row['weight']+'%')
        expect(card).to_contain_text('손익 '+row['pnl']+'원')
    for item in expected['items']:
        expect(page.locator('#avHoldings')).to_contain_text((item.get('name') or item['code'])+' · '+item['displayWeight']+'%')
    expect(page.locator('#avHoldings')).to_contain_text('현금 '+expected['cash']+'%')
    expect(page.locator('#avHoldings')).to_contain_text('리스크 기여도 unknown')
    page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    page.screenshot(path=str(ROOT/'validation/advanced-mobile.png'))
    assert not errors,errors
    browser.close()
print(f'PASS Advanced UI population={population}, initial={initial:.1f}ms, filter/reset={elapsed:.1f}ms, nodes={nodes}: selection, filters, refresh, engine reuse, 390px, JS errors=0')
