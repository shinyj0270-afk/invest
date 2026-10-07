"""Risk panels on synthetic portfolio, trend and advanced pages; no private data."""
import json,sys
from urllib.parse import urlsplit,parse_qs
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from tools.browser_runtime import chromium_options
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace
from investment.portfolio_risk import portfolio_risk
from investment.recommendations import propose
from tests.test_dashboard_upgrade import recommendation_context
from tests.test_portfolio_risk import risk_fixture

snapshot=make_fixture()
for row in snapshot['companies']:
    for p in row['prices']:p.update(final=True,open=p['close'])
for prices in snapshot['benchmarks'].values():
    for p in prices:p.update(final=True,venue='KRX',adjustment_basis='index_level')
targets,cache,cutoff=risk_fixture()
record=propose(recommendation_context(),created_on='2026-10-02')
record['portfolio_risk']=portfolio_risk(targets,20,cache,cutoff)
record['current_portfolio_risk']=record['portfolio_risk']
record['performance']={'status':'pending','reason':'가상 검증 가격; 실제 성과 아님'}
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,**chromium_options())
    page=browser.new_page(viewport={'width':1440,'height':1050});errors=[]
    page.set_default_timeout(10000)
    page.on('pageerror',lambda e:errors.append(str(e)))
    html=export_workspace(snapshot,live={'token':'synthetic','daily_prices':True})
    def route(request):
        url=request.request.url
        if url.endswith('/recommendations'):
            request.fulfill(status=200,content_type='application/json',body=json.dumps({'version':1,'records':[record]}))
        elif url.endswith('/'):
            request.fulfill(status=200,content_type='text/html',body=html)
        else:request.fulfill(status=200,content_type='application/json',body='{"status":"idle"}')
    page.route('http://127.0.0.1:8767/**',route)
    page.goto('http://127.0.0.1:8767/',wait_until='load')
    page.locator('#navigation > [data-page=recommendations]').click()
    panel=page.locator('#recommendationView [data-portfolio-risk]').first
    expect(panel).to_contain_text('주식 HHI 0.5')
    expect(panel.locator('svg')).to_have_count(3)
    panel.locator('[data-risk-correlation] summary').click()
    expect(panel).to_contain_text('변동성 기여')
    page.locator('[data-page=brief]').first.click()
    page.locator('#research [data-research-go=trend]').first.click()
    expect(page.locator('#research [data-financial-series] svg')).to_have_count(3)
    expect(page.locator('#research [data-financial-series]')).to_contain_text('지수 초과수익')
    # A price-chart zoom must not relabel the risk panel's independently stated window.
    period=page.locator('#research [data-financial-series]').inner_text()
    page.locator('[data-trend-range="63"]').click()
    assert period==page.locator('#research [data-financial-series]').inner_text()
    if page.locator('#moreNavigation').get_attribute('open') is None:
        page.locator('#moreNavigation summary').click()
    page.locator('[data-page=advanced]').first.click()
    expect(page.locator('#avCompany [data-financial-series] svg')).to_have_count(3)
    (ROOT/'validation/current').mkdir(parents=True,exist_ok=True)
    page.locator('#avCompany').screenshot(path=str(ROOT/'validation/current/risk-charts-synthetic.png'))
    for width in (390,320):
        page.set_viewport_size({'width':width,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not errors,errors
    # Missing models in the lazy live path load just the selected company once.
    payload=json.JSONDecoder().raw_decode(html.split('const WORKSPACE_DATA=',1)[1])[0]
    models=payload['company_details'];facts=payload['research']['rows'];loads=[]
    lazy_html=export_workspace(snapshot,live={'token':'synthetic','daily_prices':True,'lazy_company_views':True})
    lazy=browser.new_page(viewport={'width':1440,'height':1050});lazy.set_default_timeout(10000)
    lazy.on('pageerror',lambda e:errors.append(str(e)))
    def lazy_route(request):
        url=request.request.url
        if '/company-view?' in url:
            code=parse_qs(urlsplit(url).query)['code'][0];loads.append(code)
            model=models[code]
            request.fulfill(status=200,content_type='application/json',body=json.dumps(dict(
                code=code,name=model['name'],market=model['market'],model=model,table=payload['financial_tables'][code],
                series=facts[code]['technical']['series'],trend_analysis=facts[code]['technical'].get('trend_analysis'))))
        elif url.endswith('/'):
            request.fulfill(status=200,content_type='text/html',body=lazy_html)
        elif url.endswith('/recommendations'):
            request.fulfill(status=200,content_type='application/json',body=json.dumps({'version':1,'records':[record]}))
        else:request.fulfill(status=200,content_type='application/json',body='{"status":"idle"}')
    lazy.route('http://127.0.0.1:8767/**',lazy_route)
    lazy.goto('http://127.0.0.1:8767/',wait_until='load')
    lazy.evaluate('WORKSPACE_DATA.company_details = {}')
    lazy.locator('#moreNavigation summary').click()
    lazy.locator('[data-page=advanced]').click()
    expect(lazy.locator('#avCompany [data-financial-series] svg')).to_have_count(3)
    assert len(loads)==1,loads
    lazy.locator('#avReset').click()
    assert len(loads)==1,loads
    assert not errors,errors
    browser.close()
print('PASS synthetic risk correlation/contribution, trend/advanced charts, lazy selected company only, labelled period, mobile390/320, no JS errors')
