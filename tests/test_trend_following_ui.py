"""Synthetic chart board and lazy views only; never starts the real service."""
import json,sys
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from tools.browser_runtime import chromium_options
from investment.workspace_export import export_workspace,script_json
from tests.test_trend_following import trend_fixture

snapshot=trend_fixture()
html=export_workspace(snapshot,live={'token':'synthetic','lazy_company_views':True})
prefix,tail=html.split('const WORKSPACE_DATA=',1);payload=json.JSONDecoder().raw_decode(tail)[0]
models=payload['company_details'];facts=payload['research']['rows'];tables=payload['financial_tables']
payload['market_insights']={'sectors':[dict(market='KOSPI',industry='가상 산업 1',count=10,short_rs={'1m':{'score':80}})]}
# Force the bounded lazy path so every visible card has to obtain verified prices.
payload['company_details']={};payload['trend_following']['previews']={}
for fact in payload['research']['rows'].values():fact['technical']['series']=[]
# Preserve complete synthetic reference series for responses.
original=json.JSONDecoder().raw_decode(tail)[0]
html=prefix+'const WORKSPACE_DATA='+script_json(payload)+tail[tail.index(';</script>'):]
loads=[];errors=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,**chromium_options())
    page=browser.new_page(viewport={'width':1600,'height':1100});page.set_default_timeout(10000)
    page.on('pageerror',lambda e:errors.append(str(e)))
    def route(request):
        url=request.request.url
        if '/company-view?' in url:
            code=parse_qs(urlsplit(url).query)['code'][0];loads.append(code);model=models[code]
            technical=original['research']['rows'][code]['technical']
            request.fulfill(status=200,content_type='application/json',body=json.dumps(dict(code=code,name=model['name'],market=model['market'],model=model,table=tables[code],series=technical['series'],trend_analysis=technical.get('trend_analysis'))))
        elif url.endswith('/recommendations'):
            request.fulfill(status=200,content_type='application/json',body='{"version":1,"records":[]}')
        elif url.endswith('/'):
            request.fulfill(status=200,content_type='text/html',body=html)
        else:request.fulfill(status=200,content_type='application/json',body='{"status":"idle"}')
    page.route('http://127.0.0.1:8767/**',route)
    page.goto('http://127.0.0.1:8767/',wait_until='load')
    page.locator('#navigation > [data-page=finder]').click()
    assert page.locator('#contextNavigation button').all_text_contents()==['추세추종','조건검색','산업별 후보']
    page.locator('[data-context-page="trend-following"]').click()
    expect(page.locator('#trendFollowing')).to_be_visible()
    expect(page.locator('#navigation > [data-page=finder]')).to_have_attribute('aria-current','page')
    expect(page.locator('#tfFilters [name=capMin]')).to_have_value('1000')
    expect(page.locator('#tfFilters [name=rsMin]')).to_have_value('70')
    expect(page.locator('.tf-stock .tf-chart')).to_have_count(6)
    expect(page.locator('#tfDetailChart .tc-price-svg')).to_be_visible()
    assert len(loads)==6,loads
    assert len(set(loads))==6
    assert page.locator('.tf-markets svg').count()==2
    assert page.locator('.tf-check').count()==8
    (ROOT/'validation/current').mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(ROOT/'validation/current/trend-following-desktop.png'),full_page=True)
    page.locator('#tfNext').click()
    expect(page.locator('#tfCount')).to_contain_text('2/2페이지')
    expect(page.locator('.tf-stock .tf-chart')).to_have_count(2)
    page.locator('#tfReset').click()
    page.locator('[data-tf-industry]').click()
    expect(page.locator('#tfCount')).to_contain_text('가상 산업 1')
    page.locator('#tfClearIndustry').click()
    page.locator('#tfFilters [name=query]').fill('없는기업')
    page.locator('#tfFilters button[type=submit], #tfFilters button:not([type])').first.click()
    expect(page.locator('.tf-empty')).to_contain_text('후보가 없습니다')
    page.locator('#tfReset').click()
    page.locator('#tfFilters [name=capMin]').fill('2000')
    page.locator('#tfFilters button:not([type])').click()
    page.reload()
    expect(page.locator('#trendFollowing')).to_be_visible()
    expect(page.locator('#tfFilters [name=capMin]')).to_have_value('2000')
    page.locator('#tfReset').click()
    for width in (390,320):
        page.set_viewport_size({'width':width,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
    page.screenshot(path=str(ROOT/'validation/current/trend-following-mobile.png'),full_page=True)
    page.locator('[data-context-page=finder]').click()
    expect(page.locator('#research')).to_be_visible()
    assert not errors,errors
    browser.close()
print('PASS trend tab order, 1000 threshold, six lazy charts/page, 8 checks, filter/reset, persistence, 390/320px, no JS errors')
