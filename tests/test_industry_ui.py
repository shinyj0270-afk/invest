"""Industry overview → detail → company / Research Library flow with synthetic payloads."""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from tools.browser_runtime import chromium_options
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace,script_json

html=export_workspace(make_fixture())
prefix,tail=html.split('const WORKSPACE_DATA=',1)
payload=json.JSONDecoder().raw_decode(tail)[0]
discovery={'snapshot':copy.deepcopy(payload['snapshot']),'research':copy.deepcopy(payload['research'])}
discovery['snapshot']['meta']['discovery']=True
companies=discovery['snapshot']['companies']
for i,row in enumerate(companies):
    row.update(industry='<img src=x onerror=alert(1)>반도체와반도체장비' if i<6 else '화학',discovery_allowed=True,legacy_available=False)
    t=discovery['research']['rows'][row['code']]['technical']
    close=None if i==5 else 100+i
    t.update(close=close,sma={'50':100,'150':100,'200':101},as_of=payload['snapshot']['meta']['price_date'],price_health={'status':'ready' if close else 'missing'},
             short_rs={k:dict(return_pct=(i-2)*1.5 if close else None,score=50+i if close else None) for k in ('1m','3m','6m')})
payload['discovery']=discovery
semis=companies[0]['industry']
payload['industry_sector_map']=dict(status='ready',decided_on='2026-10-19',decided_by='user',sectors={'반도체':[semis]})
payload['market_insights']={'definition':'합성 업종 정의','markets':[],'sectors':[
    {'market':'KOSPI','industry':semis,'count':5,'short_rs':{k:{'return_pct':4.2,'score':88.5,'count':5,'cap_eok':6000} for k in ('1m','3m','6m')}},
    {'market':'KOSPI','industry':'화학','count':2,'short_rs':{k:{'return_pct':1.0,'score':None,'count':2,'cap_eok':3200} for k in ('1m','3m','6m')}}]}
src=lambda sid,title,url,published:dict(id=sid,revision=1,kind='source',stage='raw',value=dict(title=title,url=url,published_on=published,accessed_on='2026-10-19',locator='p.1',origin='independent',access='public'))
library=dict(status='ready',profile='work',masters=[dict(id='oneil',name="William O'Neil")],sources=[src('s1','Official source','https://example.invalid/a','2026-10-01')],notes=[],stories=[],
    theses=[dict(id='THESIS-1',kind='thesis',revision=1,recorded_at='2026-10-19T01:00:00+00:00',stage='derived',metadata=dict(sector='반도체',topic='산업 주도력'),
        value=dict(title='Synthetic leadership question',claim='<svg onload=alert(2)>주도력 연구 질문',sector='반도체',status='active',as_of='2026-10-19',conditions=['확산 확인'],invalidation=['실적 미확산'],instruments=[]),
        evidence=[dict(id='e1',value=dict(stance='context',observed_on='2026-10-18',observation='배경 관측'))],provenance=[src('s1','Official source','https://example.invalid/a','2026-10-01'),src('s2','Bad link','javascript:alert(3)',None)])],
    cards=[dict(id='CARD-1',kind='master',revision=1,recorded_at='2026-10-19T00:00:00+00:00',stage='derived',metadata=dict(sector='전력기기',persons=['oneil'],instruments=[dict(code=companies[1]['code'],market='KOSPI',kind='stock')]),
        value=dict(principle='Synthetic card principle',conditions=['조건'],counterexamples=['반례'],instruments=[]),provenance=[])])
def document(data,live):
    return prefix.replace('const INVESTMENT_LIVE=null;','const INVESTMENT_LIVE='+script_json(live)+';')+'const WORKSPACE_DATA='+script_json(data)+tail[tail.index(';</script>'):]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,**chromium_options())
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];calls=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    current={'html':document(payload,{'token':'synthetic'})}
    def route(r):
        url=r.request.url
        if url.endswith('/research-library'):
            calls.append(r.request.method);assert r.request.headers.get('x-dashboard-token')=='synthetic'
            r.fulfill(content_type='application/json',body=json.dumps(library,ensure_ascii=False))
        elif url.endswith('/'):r.fulfill(content_type='text/html',body=current['html'])
        else:r.fulfill(content_type='application/json',body='{"records":[],"status":"idle"}')
    page.route('http://127.0.0.1:8767/**',route);page.goto('http://127.0.0.1:8767/')
    page.locator('#navigation [data-page="industry"]').click()
    view=page.locator('#industryView');expect(view).to_be_visible()
    expect(view).to_contain_text('산업 비교');expect(view).to_contain_text('주도산업 판정이 아닙니다')
    assert view.locator('img,svg').count()==0
    # Only the group with a stored RS percentile is ranked; the thin group is listed separately.
    assert view.locator('.ind-rank').count()==1
    expect(view.locator('details')).to_contain_text('화학')
    expect(view).to_contain_text('ROIC · WACC(자본비용) · 미확보')
    expect(view.locator('table').first).to_contain_text('1 가설 · 1 카드')
    view.locator('[data-industry]').first.click()
    expect(view).to_contain_text('추세의 지속 · 약화 확인')
    expect(view).to_contain_text('구성기업으로의 확산')
    expect(view.locator('.ind-facts').first).to_contain_text('200일선 위 기업60%3/5개')
    expect(view).to_contain_text('연구 중 · 검증 전')
    expect(view).to_contain_text('매출 증가 기업 비중')
    expect(view).to_contain_text('영업이익 증가 기업 비중미확보')
    expect(view).to_contain_text('사용자 확정 산업 대응표 연결')
    expect(view).to_contain_text('구성기업 직접 연결')
    expect(view).to_contain_text('원문 발행 2026-10-01')
    assert view.locator('a[href^="javascript:"]').count()==0
    assert view.locator('#industryResearch a[href="https://example.invalid/a"]').count()>=1
    assert set(calls)=={'GET'},calls
    expect(view).to_contain_text('사용자 확정 대응표(2026-10-19)')
    for width in (390,320):
        page.set_viewport_size({'width':width,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
        assert view.locator('button:visible,select:visible,input:visible').evaluate_all('(els)=>els.every(el=>el.getBoundingClientRect().height>=44)')
    out=ROOT/'validation/current/industry';out.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(out/'detail-320.png'),full_page=True)
    page.set_viewport_size({'width':1440,'height':1000})
    page.screenshot(path=str(out/'detail-1440.png'),full_page=True)
    # Research Library opens with the matched research sector as its filter.
    view.locator('[data-library-sector="반도체"]').first.click()
    expect(page.locator('#researchLibrary')).to_be_visible()
    expect(page.locator('#libraryStatus')).to_contain_text('ready')
    expect(page.locator('#libraryFilters [name=sector]')).to_have_value('반도체')
    expect(page.locator('#libraryResults')).to_contain_text('Synthetic leadership question')
    # Company link goes to the existing company brief.
    page.locator('#pageSelect').select_option('industry',force=True)
    view.locator('[data-company]').first.click()
    expect(page.locator('#research')).to_be_visible()
    page.locator('#pageSelect').select_option('industry',force=True);view.locator('#industryBack').click()
    for width in (390,320):
        page.set_viewport_size({'width':width,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
    page.screenshot(path=str(out/'overview-320.png'),full_page=True)
    page.set_viewport_size({'width':1440,'height':1000});page.screenshot(path=str(out/'overview-1440.png'),full_page=True)
    # Library failure keeps observed industry data and offers a retry.
    page.route('**/research-library',lambda r:r.fulfill(status=503,body='{}'))
    current['html']=document(payload,{'token':'synthetic'});page.reload()
    page.locator('#navigation [data-page="industry"]').click();view.locator('[data-industry]').first.click()
    expect(page.locator('#industryResearch')).to_contain_text('연결 대기')
    # Shared company-result view never requests or shows local research.
    calls.clear();result=copy.deepcopy(payload);result['result_view']=True
    current['html']=document(result,None);page.unroute('**/research-library');page.reload()
    page.locator('#navigation [data-page="industry"]').click();view.locator('[data-industry]').first.click()
    expect(page.locator('#industryResearch')).to_contain_text('연구자료가 포함되지 않습니다')
    assert calls==[],calls
    # Both exchanges have valid scores, but each table starts its own ranking at 1.
    both=copy.deepcopy(payload)
    for i, original in enumerate(companies[:5]):
        extra=copy.deepcopy(original);extra.update(code=f'98000{i}',market='KOSDAQ')
        both['discovery']['snapshot']['companies'].append(extra)
        both['discovery']['research']['rows'][extra['code']]=copy.deepcopy(discovery['research']['rows'][original['code']])
    both['market_insights']['sectors'].append(dict(market='KOSDAQ',industry=semis,count=5,
        short_rs={k:dict(return_pct=9,score=99,count=5,cap_eok=6000) for k in ('1m','3m','6m')}))
    current['html']=document(both,None);page.reload()
    page.locator('#navigation [data-page="industry"]').click()
    for market in ('KOSPI','KOSDAQ'):
        market_view=view.locator(f'[data-industry-market="{market}"]')
        expect(market_view).to_be_visible()
        assert market_view.locator('.ind-rank').all_text_contents()==['1']
        assert market_view.locator('[data-industry]').evaluate_all('(els)=>els.every(e=>e.dataset.industry.startsWith('+json.dumps(market+'|')+'))')
    for width in (1440,390,320):
        page.set_viewport_size({'width':width,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
    # A live token must not bypass result-view research exclusion.
    page.set_viewport_size({'width':1440,'height':1000})
    calls.clear();current['html']=document(result,{'token':'synthetic'});page.reload()
    page.locator('#navigation [data-page="industry"]').click();view.locator('[data-industry]').first.click()
    expect(page.locator('#industryResearch')).to_contain_text('연구자료가 포함되지 않습니다')
    assert calls==[],calls
    assert not errors,errors
    browser.close()
print('PASS industry overview/detail/company/library flow, unranked thin groups, XSS, failure, result view, 1440/390/320px')
