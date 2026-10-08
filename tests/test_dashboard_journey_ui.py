"""Synthetic linked journeys and browser persistence, with no actual personal writes."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from tools.browser_runtime import chromium_options
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace,script_json
from investment.financial_metrics import common_metrics
from investment.recommendations import propose
from tests.test_dashboard_upgrade import recommendation_context

html=export_workspace(make_fixture(),live={'token':'fixture'})
prefix,tail=html.split('const WORKSPACE_DATA=',1);data=json.JSONDecoder().raw_decode(tail)[0]
rows=data['analysis_snapshot']['companies'];facts=data['research']['rows'];first=rows[0]['code']
for r in rows:
    r['common_financial']=common_metrics(r,data['financial_tables'][r['code']],facts[r['code']]['technical'])
    r['collection_health']={'status':'partial','last_success':'2026-10-01','last_checked':'2026-10-02','failed_periods':1,'retry':'다음 일간 점검에 재시도'}
    r['industry']='가상 산업';r['common_financial']['metrics'].update(revenue_growth_pct=30,roe_pct=15,operating_margin_pct=10,debt_ratio_pct=50)
    r['metrics'].update(r['common_financial']['metrics']);facts[r['code']]['fundamental']['metrics'].update(r['common_financial']['metrics'])
    facts[r['code']]['technical'].update(status='pass',price_trend_status='pass',gap_to_52w_high_pct=-3,price_strength={'score':90},short_rs={'1m':{'score':80}})
data['market_insights']={'markets':[],'sectors':[{'market':rows[0]['market'],'industry':'가상 산업','count':5,'short_rs':{'1m':{'score':80,'return_pct':12,'count':5,'cap_eok':10000}}}]}
html=prefix+'const WORKSPACE_DATA='+script_json(data)+tail[tail.index(';</script>'):]
record=propose(recommendation_context(),created_on='2026-10-02')
record['performance']={'status':'ready','return_pct':2.4,'parts':[{'code':t['code'],'name':t['name'],'return_pct':i+1,'contribution_pct':(i+1)*.16} for i,t in enumerate(record['targets'])],'benchmark_returns':{'KOSPI':2},'entry_date':'2026-10-05','as_of':'2026-10-06'}
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,**chromium_options())
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    def route(r):
        if r.request.url.endswith('/recommendations'):r.fulfill(content_type='application/json',body=json.dumps({'records':[record]}))
        elif r.request.url.endswith('/'):r.fulfill(content_type='text/html',body=html)
        else:r.fulfill(content_type='application/json',body='{"status":"idle"}')
    page.route('http://127.0.0.1:8799/**',route);page.goto('http://127.0.0.1:8799/')
    page.locator('#homeSectors .home-tile').first.click()
    expect(page.locator('#homeCandidates h3')).to_contain_text('가상 산업')
    page.locator('#homeCandidates [data-sector-search]').click()
    expect(page.locator('[name=industry]')).to_have_value('가상 산업')
    page.locator('[data-preset=growth]').click()
    expect(page.locator('[name=growthMin]')).to_have_value('10')
    expect(page.locator('#discoveryTable')).to_contain_text('적용 조건 충족')
    page.locator('[data-preset-name]').fill('나의 성장 검색');page.locator('[data-save-preset]').click()
    page.reload();page.locator('[data-page=finder]').click()
    expect(page.locator('[data-saved-preset]')).to_contain_text('나의 성장 검색')
    page.locator('[data-saved-preset]').select_option('0');expect(page.locator('[name=growthMin]')).to_have_value('10')
    page.locator('[data-delete-preset]').click();expect(page.locator('[data-saved-preset] option')).to_have_count(1)
    page.locator('[data-watch]').first.click();page.locator('[data-page=watch]').click()
    expect(page.locator('.journey-changes')).to_contain_text('첫 관측 기준')
    page.locator('#discoveryTable [data-research-code]').first.click()
    expect(page.locator('.journey-company')).to_contain_text('같은 산업')
    expect(page.locator('.journey-history')).to_be_visible()
    page.locator('[data-journey-cadence]').select_option('annual')
    expect(page.locator('.journey-company')).not_to_contain_text('QoQ')
    page.locator('[data-journey-cadence]').select_option('quarter');expect(page.locator('.journey-company')).to_contain_text('QoQ')
    page.locator('.journey-health summary').click();expect(page.locator('.journey-health')).to_contain_text('2026-10-01')
    page.screenshot(path=str(ROOT/'validation/journey-company-fixture.png'))
    page.locator('#pageSelect').select_option('recommendations',force=True)
    expect(page.locator('#recommendationView')).to_contain_text('모델 기여도')
    expect(page.locator('#recommendationView')).to_contain_text('2.4%p')
    for width in (1440,390,320):
        page.set_viewport_size({'width':width,'height':1000})
        for view in ('home','finder','watch','brief','recommendations'):
            page.locator('#pageSelect').select_option(view,force=True)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(width,view)
    assert not errors,errors
    browser.close()
print('PASS synthetic sector drilldown, saved presets reload/delete, watch baseline, quarter/year/peers, health, contributions, desktop/mobile')
