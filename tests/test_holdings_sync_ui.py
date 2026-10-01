"""Two isolated browser PCs with synthetic quotes and an in-memory private transport."""
import json,os,sys,tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace
from investment.holdings_sync import HoldingsService
from tests.test_holdings_sync import MemoryBackend

snapshot=make_fixture();snapshot['meta']['data_mode']='user_input'
html=export_workspace(snapshot,live={'token':'synthetic-session','receipt':{},'snapshot_id':'synthetic','holdings_sync':True})
base='http://127.0.0.1:18767';checks=[]
def check(name,condition):assert condition,name;checks.append(name)
with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
    backend=MemoryBackend();browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
    errors=[];external=[]
    def pc(name):
        service=HoldingsService(ROOT,backend,Path(tmp)/(name+'.json'));context=browser.new_context(viewport={'width':1600,'height':1100});offline={'value':False}
        def route(r):
            if r.request.url==base+'/holdings':
                if offline['value']:r.abort();return
                check('loopback requests carry session authorization',r.request.headers.get('x-dashboard-token')=='synthetic-session')
                if r.request.method=='POST':
                    data=r.request.post_data_json;result=service.submit(data['state'],data.get('base'))
                else:result=service.poll()
                r.fulfill(status=200,content_type='application/json',body=json.dumps(result,ensure_ascii=False))
            else:r.fulfill(status=200,content_type='text/html',body=html)
        context.route(base+'/**',route);page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:external.append(r.url) if r.url.startswith(('http:','https:')) and not r.url.startswith(base) else None)
        page.on('dialog',lambda d:d.accept());page.goto(base);page.locator('[data-page=holdings]').click()
        return context,page,page.frame_locator('#detailFrame'),offline
    ca,a,fa,offline=pc('work')
    expect(fa.locator('#pSaveStatus')).to_contain_text('연결됨')
    def add(f,code,quantity,price,cash=None):
        f.locator('#pEntry').click()
        f.locator('#pCode').fill(code);f.locator('#pQty').fill(str(quantity));f.locator('#pCost').fill('10000');f.locator('#pQuote').fill(str(price));f.locator('#pQuoteSource').fill('가상 입력')
        if cash is not None:f.locator('#pCash').fill(str(cash))
        f.locator('#pSaveHolding').click();expect(f.locator('#pSaveStatus')).to_contain_text('동기화 완료')
    add(fa,'000001',10,12000,200000)
    check('direct entry first and advanced JSON collapsed',fa.locator('#pEntry').is_visible() and not fa.locator('#pJsonEditor').is_visible())
    cb,b,fb,_=pc('home');expect(fb.locator('#pHoldBody')).to_contain_text('000001')
    check('restored holdings table precedes collapsed entry',not fb.locator('#pEntryPanel').evaluate('e=>e.open') and fb.locator('#pHoldingsCard').evaluate("e=>e.getBoundingClientRect().top<document.getElementById('pEntryPanel').getBoundingClientRect().top"))
    check('restored rows visible near top',fb.locator('#pHoldBody tr').first.bounding_box()['y']<700)
    check('instructions and management collapsed',not fb.locator('#pHelp').evaluate('e=>e.open') and not fb.locator('#pManagement').evaluate('e=>e.open') and not b.locator('#sourceDetails').evaluate('e=>e.open'))
    b.screenshot(path=str(ROOT/'preview_holdings_focus.png'),full_page=True)
    check('other PC restores quantity cash and quote',fb.locator('#pValue').inner_text()=='320,000 원')
    add(fb,'000002',2,15000)
    fa.locator('#pSyncNow').click();expect(fa.locator('#pHoldBody')).to_contain_text('000002')
    check('automatic pull keeps both companies',fa.locator('#pHoldBody tr').count()==2)
    # A remote refresh must not discard an unfinished direct-entry form.
    fa.locator('#pCode').fill('000003');fa.locator('#pQty').fill('77');fa.locator('#pCode').blur();fa.locator('#pSyncNow').click()
    expect(fa.locator('#pSaveStatus')).to_contain_text('동기화 완료')
    check('unfinished input survives remote poll',fa.locator('#pQty').input_value()=='77' and fa.locator('#pCode').input_value()=='000003')
    a.reload();a.locator('[data-page=holdings]').click();expect(fa.locator('#pHoldBody')).to_contain_text('000002')
    check('reload restores committed holdings',fa.locator('#pHoldBody tr').count()==2)
    offline['value']=True;fa.locator('[data-holding-edit="000001"]').click();fa.locator('#pQty').fill('11');fa.locator('#pSaveHolding').click()
    expect(fa.locator('#pSaveStatus')).to_contain_text('이 PC에 저장')
    a.reload();a.locator('[data-page=holdings]').click();expect(fa.locator('#pHoldBody tr').first).to_contain_text('11')
    check('offline restart preserves pending edits',fa.locator('#pHoldBody tr').count()==2)
    fb.locator('[data-holding-edit="000001"]').click();fb.locator('#pQty').fill('12');fb.locator('#pSaveHolding').click();expect(fb.locator('#pSaveStatus')).to_contain_text('동기화 완료')
    offline['value']=False;fa.locator('#pSyncNow').click();expect(fa.locator('#pSyncConflict')).to_be_visible()
    check('same field conflict never overwrites cloud',backend.state['input']['holdings'][0]['quantity']==12)
    fa.locator('#pKeepLocal').click();expect(fa.locator('#pSaveStatus')).to_contain_text('동기화 완료')
    check('explicit conflict choice preserves other company',backend.state['input']['holdings'][0]['quantity']==11 and len(backend.state['input']['holdings'])==2)
    fb.locator('#pSyncNow').click();expect(fb.locator('#pHoldBody tr').first).to_contain_text('11')
    # Fictional fixture selection must not replace private saved holdings.
    fa.locator('#pManagement summary').click();fa.locator('#pFixture').click();check('fixture is isolated from saved holdings',backend.state['input']['holdings'][0]['code']=='000001')
    fa.locator('#pReturnSaved').click();expect(fa.locator('#pHoldBody')).to_contain_text('000001')
    check('return from fixture restores own holdings',fa.locator('#pHoldBody tr').count()==2)
    fa.locator('[data-holding-edit="000002"]').click();fa.locator('#pDeleteHolding').click();expect(fa.locator('#pSaveStatus')).to_contain_text('동기화 완료')
    fb.locator('#pSyncNow').click();expect(fb.locator('#pHoldBody tr')).to_have_count(1)
    check('explicit deletion syncs to second PC',backend.state['input']['holdings'][0]['code']=='000001')
    b.set_viewport_size({'width':390,'height':844});b.screenshot(path=str(ROOT/'preview_holdings_focus_mobile.png'),full_page=True)
    check('mobile restored row visible without instructions',fb.locator('#pHoldBody tr').first.bounding_box()['y']<700)
    a.set_viewport_size({'width':390,'height':844});check('mobile no document overflow',a.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
    check('no script errors',not errors);check('no external broker or cloud requests',not external)
    browser.close()
print('PASS '+str(len(checks))+' two-PC holdings sync UI checks')
