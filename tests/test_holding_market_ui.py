"""Known public companies outside the legacy universe; synthetic prices only."""
import copy,json,os,subprocess,sys,tempfile
from urllib.parse import urlsplit,parse_qs
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace
from investment.holdings_bridge import holdings_catalog
from investment.holdings_sync import HoldingsService
from tests.test_holding_market import cache
from tests.test_holdings_sync import MemoryBackend

snapshot=make_fixture();snapshot['meta']['data_mode']='user_input';market=cache()
template=market['universe']['companies'][0]
market['universe']['companies'] += [dict(template,code=str(100000+i),name='가상 후보 '+str(i)) for i in range(200)]
catalog={r['code']:r for r in holdings_catalog(snapshot,market,'2026-10-01')}
html=export_workspace(snapshot,market_cache=market,live={'token':'synthetic','receipt':{},'holdings_sync':True,'holdings_market':True})
script="const P=require('./src/portfolio_engine.js'),H=require('./src/holdings_sync.js');let x=P.empty('2026-10-01');for(const code of ['005010','010950'])x=P.saveHolding(x,{code,quantity:10,avg_cost_krw:null},null,{price:110,date:'2026-09-29',label:'가상 입력'});console.log(JSON.stringify(H.pack(x,P.DEFAULT)));"
initial=json.loads(subprocess.check_output(['node','-e',script],cwd=ROOT,encoding='utf-8'));checks=[]
def check(name,condition):assert condition,name;checks.append(name)
with tempfile.TemporaryDirectory() as tmp,sync_playwright() as p:
 backend=MemoryBackend();backend.write(initial,None);service=HoldingsService(ROOT,backend,Path(tmp)/'cache.json')
 browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
 context=browser.new_context(viewport={'width':1600,'height':1100});errors=[];external=[];newprice={'value':120};quotes=[]
 base='http://127.0.0.1:18768'
 def route(r):
  if r.request.url.startswith(base+'/holding-market?code='):
   code=parse_qs(urlsplit(r.request.url).query)['code'][0];quotes.append(code);assert r.request.headers.get('x-dashboard-token')=='synthetic'
   row=copy.deepcopy(catalog.get(code));result=dict(code=code,row=row,status='unavailable',message='미연결')
   if row:
    row.update(price_krw=newprice['value'],price_date='2026-09-30');result.update(status='updated',message='최근 완료 종가 확인 · 2026-09-30')
   r.fulfill(status=200,content_type='application/json',body=json.dumps(result,ensure_ascii=False))
  elif r.request.url==base+'/holdings':
   data=r.request.post_data_json if r.request.method=='POST' else None
   result=service.submit(data['state'],data.get('base')) if data else service.poll()
   r.fulfill(status=200,content_type='application/json',body=json.dumps(result,ensure_ascii=False))
  else:r.fulfill(status=200,content_type='text/html',body=html)
 context.route(base+'/**',route);page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
 page.on('request',lambda r:external.append(r.url) if r.url.startswith(('http:','https:')) and not r.url.startswith(base) else None)
 page.goto(base);page.locator('[data-page=holdings]').click();f=page.frame_locator('#detailFrame')
 expect(f.locator('#pHoldBody')).to_contain_text('가상 휴스틸');expect(f.locator('#pHoldBody')).to_contain_text('가상 S-Oil')
 expect(f.locator('#pSaveStatus')).to_contain_text('동기화 완료');expect(f.locator('#pMarketStatus')).to_contain_text('최근 완료 종가')
 check('held company names resolved outside legacy universe',f.locator('#pHoldBody tr').count()==2)
 expect(f.locator('#pHoldBody')).to_contain_text('1,200')
 check('newer completed price updates evaluation','1,200' in f.locator('#pHoldBody').inner_text())
 check('missing cost and cash remain unknown',all(h['avg_cost_krw'] is None for h in page.locator('#detailFrame').evaluate('e=>e.contentWindow.INVESTMENT_GET_HOLDINGS().holdings')) and '현금 미입력' in f.locator('#pBookNote').inner_text())
 check('candidate identity never becomes completed investment review','판단 보류' in f.locator('#pHoldBody').inner_text())
 check('only selected catalog companies enter private state',len(backend.state['input']['research'])<15)
 f.locator('[data-holding-edit="005010"]').click();expect(f.locator('#pHoldingName')).to_have_value('가상 휴스틸')
 check('company name read only for connected code',f.locator('#pHoldingName').evaluate('e=>e.readOnly'))
 f.locator('#pQty').fill('77');f.locator('#pQuote').fill('8888');f.locator('#pQuoteSource').fill('가상 수기 초안');newprice['value']=130
 f.locator('#pQuoteRefresh').click();expect(f.locator('#pHoldBody')).to_contain_text('1,300')
 check('async price update preserves unfinished quantity and quote',f.locator('#pQty').input_value()=='77' and f.locator('#pQuote').input_value()=='8888')
 check('unfinished quantity not saved to cloud',backend.state['input']['holdings'][0]['quantity']==10)
 f.locator('#pCode').fill('010950');expect(f.locator('#pHoldingName')).to_have_value('가상 S-Oil')
 f.locator('#pCode').fill('999999');expect(f.locator('#pHoldingName')).to_have_value('');expect(f.locator('#pQuote')).to_have_value('')
 check('unknown code clears previous company and quote',not f.locator('#pHoldingName').evaluate('e=>e.readOnly'))
 f.locator('[data-holding-company="005010"]').click();expect(page.locator('#research')).to_contain_text('가상 휴스틸')
 check('company name opens existing brief analysis',page.locator('#research').is_visible())
 page.locator('[data-page=holdings]').click();page.set_viewport_size({'width':390,'height':844})
 check('mobile no document overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
 check('only loopback fetches and no script errors',not errors and not external)
 browser.close()
print('PASS '+str(len(checks))+' company lookup and automatic quote UI checks')
