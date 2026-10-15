"""Lazy company failures must end loading and support explicit retry."""
import json
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
    page.locator('#research [data-company-view-retry]').click()
    expect(page.locator('#research .interactiveTrendChart svg').first).to_be_visible()
    expect(page.locator('#research [data-company-view-error]')).to_have_count(0)
    assert len(calls)==2,calls
    page.locator('[data-research-go=company]').click()
    expect(page.locator('#sdCompany')).to_be_visible()
    assert not errors,errors
    # All nine primary destinations are directly visible and keyboard accessible.
    expect(page.locator('#moreNavigation summary')).to_have_count(0)
    expect(page.locator('#navigation .nav-item')).to_have_count(9)
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
    expect(timed.locator('[data-company-view-retry]')).to_be_visible()
    browser.close()
print('PASS company503 stops loading, restart guidance, retry loads metrics/detail/trend, timeout, nine direct menus, responsive widths')
