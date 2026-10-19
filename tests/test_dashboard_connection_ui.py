"""Lazy company failures must end loading and support explicit retry."""
import json
from copy import deepcopy
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from tools.browser_runtime import chromium_options
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace

snapshot=make_fixture()
for row in snapshot['companies']:
    for bar in row['prices']:bar.update(final=True,open=bar['close'])
for prices in snapshot['benchmarks'].values():
    for bar in prices:bar.update(final=True,venue='KRX',adjustment_basis='index_level')
full=export_workspace(snapshot)
payload=json.JSONDecoder().raw_decode(full.split('const WORKSPACE_DATA=',1)[1])[0]
html=export_workspace(snapshot,live={'token':'synthetic','lazy_company_views':True})
# Model the actual discovery overview: validated common amounts arrive before lazy details.
overview=json.JSONDecoder().raw_decode(html.split('const WORKSPACE_DATA=',1)[1])[0]
overview['analysis_snapshot']['companies'][0]['common_financial']={
    'basis':'CFS','period':'2026-06-30','currency':'KRW',
    'amounts':{'revenue':1234,'operating_profit':56,'net_income':34},
    'metrics':{},'metric_details':{}}
overview['discovery']={'snapshot':deepcopy(overview['analysis_snapshot']),'research':deepcopy(overview['research'])}
overview['discovery']['snapshot']['meta'].update(discovery=True,financial_basis=None)
overview['discovery']['research']['rows']['900000']['technical'].update(series=[],series_pending=True)
prefix,tail=html.split('const WORKSPACE_DATA=',1)
_,length=json.JSONDecoder().raw_decode(tail)
from investment.workspace_export import script_json
html=prefix+'const WORKSPACE_DATA='+script_json(overview)+tail[length:]
base='http://127.0.0.1:8767'
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,**chromium_options())
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];calls=[];fail=[True]
    page.set_default_timeout(4000)
    page.on('pageerror',lambda e:errors.append(str(e)))
    def route(request):
        url=request.request.url
        if '/company-view?' in url:
            code=parse_qs(urlsplit(url).query)['code'][0];calls.append(code)
            if fail[0]:
                request.fulfill(status=503,content_type='application/json',body='{"error":"서버 다시 실행 필요"}')
            else:
                model=payload['company_details'][code]
                request.fulfill(content_type='application/json',body=json.dumps(dict(code=code,name=model['name'],market=model['market'],
                    table=payload['financial_tables'][code],model=model,series=payload['research']['rows'][code]['technical']['series'],
                    trend_analysis=payload['research']['rows'][code]['technical'].get('trend_analysis'))))
        elif url==base+'/':request.fulfill(content_type='text/html',body=html)
        else:request.fulfill(content_type='application/json',body='{"status":"idle","records":[]}')
    page.route(base+'/**',route)
    page.goto(base+'/',wait_until='load')
    page.locator('[data-page=brief]').click()
    expect(page.locator('[data-company-view-error]')).to_be_visible()
    # A failed detail request must not hide validated amounts already in the overview.
    expect(page.locator('[data-brief-metric="revenue"] b')).not_to_have_text('—')
    page.locator('[data-research-go=trend]').first.click()
    expect(page.locator('#research [data-company-view-error]')).to_be_visible()
    expect(page.locator('#research')).not_to_contain_text('불러오는 중')
    expect(page.locator('#research')).not_to_contain_text('조회 중')
    expect(page.locator('#research a[href="/restart"]')).to_be_visible()
    assert len(calls)==1,calls
    page.locator('[data-research-go=company]').click()
    expect(page.locator('#companyDetail [data-company-retry]')).to_be_visible()
    expect(page.locator('#companyDetail')).not_to_contain_text('불러오는 중')
    page.locator('[data-context-page=trend]').click()
    expect(page.locator('#research [data-company-view-error]')).to_be_visible()
    assert len(calls)==1,calls
    fail[0]=False
    page.locator('#research [data-company-view-retry]').first.click()
    expect(page.locator('#research .interactiveTrendChart svg').first).to_be_visible()
    expect(page.locator('#research [data-company-view-error]')).to_have_count(0)
    assert len(calls)==2,calls
    page.locator('[data-research-go=company]').click()
    expect(page.locator('#sdCompany')).to_be_visible()
    assert not errors,errors
    # All ten primary destinations are directly visible and keyboard accessible.
    expect(page.locator('#moreNavigation summary')).to_have_count(0)
    expect(page.locator('#navigation .nav-item')).to_have_count(10)
    for width in (1920,1640,1440,1366,1214,1024,950,901):
        page.set_viewport_size({'width':width,'height':1000})
        boxes=page.locator('#navigation .nav-item').evaluate_all('(els)=>els.map(e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom}})')
        assert all(0<=b['x']<b['right']<=width for b in boxes),(width,boxes)
        assert not any(a['x']<b['right'] and b['x']<a['right'] and a['y']<b['bottom'] and b['y']<a['bottom'] for i,a in enumerate(boxes) for b in boxes[i+1:]),width
    for width in (390,320):
        page.set_viewport_size({'width':width,'height':844})
        expect(page.locator('#pageSelect')).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    # Comparing a second company must also recover from a failed lazy request.
    page.set_viewport_size({'width':1440,'height':1000})
    page.locator('[data-page=overview]').click()
    for code in ('900001','900002'):
        if code=='900002':fail[0]=True
        page.locator('#comparisonQuery').fill(code)
        page.locator(f'[data-add-comparison="{code}"]').click()
    expect(page.locator('[data-comparison-retry="900002"]')).to_be_visible()
    expect(page.locator('#comparisonPrices')).not_to_contain_text('이력 연결 중')
    fail[0]=False
    page.locator('[data-comparison-retry="900002"]').click()
    expect(page.locator('#comparisonPrices svg')).to_have_count(2)
    expect(page.locator('[data-comparison-retry]')).to_have_count(0)
    page.reload();page.locator('[data-page=overview]').click()
    expect(page.locator('#comparisonChips [data-remove-comparison]')).to_have_count(2)
    timed=browser.new_page();timed.set_default_timeout(4000)
    timed.add_init_script('''const original=window.setTimeout;window.setTimeout=(f,t,...a)=>original(f,t===20000?80:t,...a);
    const fetchOriginal=window.fetch;window.fetch=(url,options)=>String(url).startsWith('/company-view?')?
      new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('Timed out','AbortError')))):
      fetchOriginal(url,options);''')
    timed.route(base+'/**',lambda r:r.fulfill(content_type='text/html',body=html) if r.request.url==base+'/' else r.fulfill(content_type='application/json',body='{"status":"idle","records":[]}'))
    timed.goto(base+'/',wait_until='load');timed.locator('[data-page=brief]').click()
    expect(timed.locator('[data-company-view-error]')).to_contain_text('지연')
    expect(timed.locator('[data-company-view-retry]').first).to_be_visible()
    # A tab left open across restart has an expired token. Retrying it cannot work;
    # reconnect must use the existing input-preserving reload path instead.
    stale=browser.new_page();stale.set_default_timeout(4000);documents=[0]
    stale.add_init_script("window.capturedHandoff=JSON.parse(sessionStorage.getItem('investment-live-refresh-handoff'));")
    def stale_route(request):
        if request.request.url==base+'/':
            documents[0]+=1
            body=html if documents[0]==1 else html.replace('"token":"synthetic"','"token":"new-synthetic"')
            request.fulfill(content_type='text/html',body=body)
        elif '/company-view?' in request.request.url and request.request.headers.get('x-dashboard-token')!='new-synthetic':
            request.fulfill(status=403,content_type='application/json',body='{"error":"request denied"}')
        else:route(request)
    stale.route(base+'/**',stale_route)
    stale.goto(base+'/',wait_until='load');stale.locator('[data-page=brief]').click()
    expect(stale.locator('[data-company-view-error]')).to_contain_text('서버 연결 정보가 변경')
    expect(stale.locator('[data-brief-metric="revenue"] b')).to_have_text('1,234억')
    assert stale.evaluate("WORKSPACE_DATA.discovery.research.rows['900000'].technical.series.length")==0
    expect(stale.locator('[data-company-view-retry]').first).to_have_text('입력을 보존하고 화면 다시 연결')
    before_input=stale.evaluate("document.getElementById('detailFrame').contentWindow.INVESTMENT_GET_HOLDINGS()")
    stale.locator('[data-company-view-retry]').last.click()
    expect(stale.locator('.interactiveTrendChart svg').first).to_be_visible()
    expect(stale.locator('[data-company-view-error]')).to_have_count(0)
    saved=stale.evaluate('window.capturedHandoff')
    assert saved['page']=='brief' and saved['code']=='900000',(saved['page'],saved['code'])
    assert saved['input']==before_input
    browser.close()
print('PASS company503 stops loading, restart guidance, retry loads metrics/detail/trend, timeout, ten direct menus, responsive widths')
