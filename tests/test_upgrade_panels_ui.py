"""Integrated market, risk and native financial panels with synthetic view models."""
import copy,json,sys
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from tools.browser_runtime import chromium_options
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace,script_json
from investment.recommendations import propose
from tests.test_dashboard_upgrade import recommendation_context

html=export_workspace(make_fixture())
prefix,tail=html.split('const WORKSPACE_DATA=',1)
payload=json.JSONDecoder().raw_decode(tail)[0]
cutoff=payload['snapshot']['meta']['price_date']
explanation={'as_of':cutoff,'definition':'가상 검증 시장 계약','markets':[],'universe':'합성 관찰 대상'}
for market in ['KOSPI','KOSDAQ']:
    explanation['markets'].append(dict(market=market,as_of=cutoff,index={'label':'가상 상승 정렬','close':1234,'definition':'지수 기준'},
        breadth={'label':'가상 기업 참여','population':8,'valid':8,'above':{'200':{'count':6,'eligible':8,'pct':75},'50':{'count':5,'eligible':8,'pct':62.5}},'advancing':5,'declining':2,'unchanged':1,'change_eligible':8,'definition':'참여 분모'},
        volatility={'annual20_pct':12,'prior20_pct':13,'returns':20,'start_date':'2026-08-27','label':'가상 변동성','definition':'과거20수익률'},explanation='가상 신호 설명',source_note='합성 자료',verification='검증용'))
payload['trend_following']['market_explanation']=explanation
payload['analysis_snapshot']['companies']=payload['analysis_snapshot']['companies'][:1]
payload['discovery']={'snapshot':copy.deepcopy(payload['snapshot']),'research':copy.deepcopy(payload['research'])}
payload['discovery']['snapshot']['meta']['discovery']=True
for row in payload['discovery']['snapshot']['companies']:row['legacy_available']=row['code']=='900000'
native_row=payload['discovery']['snapshot']['companies'][1]
native_row['latest_quote']={'price':12500,'retrieved_at':'2026-10-02T11:00:00+09:00','price_time':None}
complete={'basis':'CFS','currency':'USD','latest_stored':{'status':'ready','period_start':'2026-05-01','period_end':'2026-07-31','available_at':'2026-08-31','receipt':'20260831000001'},'ttm':{'status':'pending','reason':'이전 회계분기 추가 확인'},'required_accounts':{'status':'partial','missing':['ocf']},'roe':{'status':'pending','reason':'전년 같은 회계분기 평균 자본 확인'},'next_action':'가상 다음 원문 확인','source_urls':['https://dart.fss.or.kr/report/viewer.do?rcpNo=20260831000001']}
native={'completeness':complete,'groups':[{'basis':'CFS','currency':'USD','cadence':'quarter','amount_unit':'백만 USD','amount_divisor':1e6,'columns':[{'period_start':'2026-05-01','period_end':'2026-07-31','fiscal_year':2027,'fiscal_quarter':1,'revenue':123e6,'operating_profit':12e6,'net_income':9e6}]}],'fx':{'reason':'환율 검증 대기'}}
native_row.pop('common_financial',None);native_row['financial_completeness']=complete
model=payload['company_details']['900001'];model.update(groups=[],native_financial=native,financial_completeness=complete)
table=payload['financial_tables']['900001'];table.update(groups=[],native_financial=native,financial_completeness=complete)
record=propose(recommendation_context(),created_on='2026-10-02');record['performance']={'status':'pending','reason':'가상 가격 대기'}
policy={'limits':{'max_positions':5,'max_position_pct':40,'min_cash_pct':5},'effective_on':'2026-10-07','provenance':'사용자 확인 가상 검증'}
review={'status':'ready','policy_status':'ready','policy':policy,'window':{'start_date':'2025-09-25','as_of':cutoff,'observations':252},'previous':{'status':'ready','annual_volatility_pct':25,'max_drawdown_pct':-10},'proposed':{'status':'ready','annual_volatility_pct':24,'max_drawdown_pct':-12},'deltas':{'annual_volatility_pct':-1,'max_drawdown_pct':-2},'flags':['drawdown_deeper']}
record['risk_review']=copy.deepcopy(review);record['current_risk_review']=copy.deepcopy(review)
record['alternatives']=[{'name':'가상 교체 대안','replaces':'가상 이전 기업','advisory':'작성 당시 참고 대안','review':{'status':'pending','policy_status':'ready','policy':policy,'reason':'공통 가격 자료 대기'}}]
def document(data,lazy=False):
    config={'token':'synthetic','lazy_company_views':lazy}
    return prefix.replace('const INVESTMENT_LIVE=null;','const INVESTMENT_LIVE='+script_json(config)+';')+'const WORKSPACE_DATA='+script_json(data)+tail[tail.index(';</script>'):]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,**chromium_options())
    errors=[];loads=[]
    page=browser.new_page(viewport={'width':1440,'height':1050})
    page.on('pageerror',lambda e:errors.append(str(e)))
    def routes(route):
        path=route.request.url
        if path.endswith('/recommendations'):route.fulfill(content_type='application/json',body=json.dumps({'records':[record]},ensure_ascii=False))
        elif path.endswith('/'):route.fulfill(content_type='text/html',body=document(payload))
        else:route.fulfill(content_type='application/json',body='{"status":"idle"}')
    page.route('http://127.0.0.1:8767/**',routes)
    page.goto('http://127.0.0.1:8767/')
    home_text=page.locator('#home .market-explanation').inner_text()
    assert page.locator('#home .me-card').count()==2
    expect(page.locator('#upgradeOverview')).to_contain_text('최근 자료 저장')
    expect(page.locator('#upgradeOverview')).to_contain_text('필수 계정')
    assert page.locator('#upgradeOverview').get_by_text('방어 검토',exact=True).count()==0
    page.locator('[data-page=finder]').click();page.locator('[data-context-page=trend-following]').click()
    expect(page.locator('#trendFollowing .market-explanation')).to_have_text(page.locator('#trendFollowing .market-explanation').text_content())
    assert page.locator('#trendFollowing .market-explanation').inner_text()==home_text
    expect(page.locator('#trendFollowing .tf-changes')).to_contain_text('관측 후보 변화')
    page.locator('[data-page=recommendations]').click()
    expect(page.locator('#recommendationView')).to_contain_text('최대 5종목 · 종목당 40% · 현금 최소 5%')
    expect(page.locator('#recommendationView')).to_contain_text('최신 자료로 구성 변경 재점검')
    expect(page.locator('#recommendationView')).to_contain_text('작성 당시 구성 변경 위험 검토')
    page.locator('#recommendationView summary').filter(has_text='작성 당시 구성 변경 위험 검토').click()
    expect(page.locator('#recommendationView')).to_contain_text('가상 교체 대안')
    page.locator('[data-page=brief]').click();page.locator('#researchCompany').select_option('900001')
    expect(page.locator('#research .financial-completeness')).to_contain_text('백만 USD')
    expect(page.locator('#research .financial-completeness')).to_contain_text('2026-07-31')
    expect(page.locator('#research')).to_contain_text('이전 조회 참고가격')
    page.locator('[data-context-page=company]').click()
    expect(page.locator('#sdCompany')).to_have_value('900001')
    expect(page.locator('#companyDetail .financial-completeness')).to_contain_text('FY2027 Q1')
    for width in [390,320]:
        page.set_viewport_size({'width':width,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    lazy_payload=copy.deepcopy(payload);lazy_payload['company_details']={};lazy_payload['financial_tables']={}
    for facts in lazy_payload['discovery']['research']['rows'].values():facts['technical']['series_pending']=True
    lazy=browser.new_page(viewport={'width':1440,'height':1050});lazy.on('pageerror',lambda e:errors.append(str(e)))
    def lazy_routes(route):
        path=route.request.url
        if '/company-view?' in path:
            code=parse_qs(urlsplit(path).query)['code'][0];loads.append(code)
            value=payload['company_details'][code]
            route.fulfill(content_type='application/json',body=json.dumps({'code':code,'name':value['name'],'market':value['market'],'model':value,'table':payload['financial_tables'][code],'series':[]},ensure_ascii=False))
        elif path.endswith('/recommendations'):route.fulfill(content_type='application/json',body=json.dumps({'records':[record]},ensure_ascii=False))
        elif path.endswith('/'):route.fulfill(content_type='text/html',body=document(lazy_payload,True))
        else:route.fulfill(content_type='application/json',body='{"status":"idle"}')
    lazy.route('http://127.0.0.1:8767/**',lazy_routes)
    lazy.goto('http://127.0.0.1:8767/')
    lazy.locator('[data-page=brief]').click();lazy.locator('#researchCompany').select_option('900001')
    expect(lazy.locator('#research .financial-completeness')).to_contain_text('백만 USD')
    lazy.locator('[data-context-page=company]').click()
    expect(lazy.locator('#companyDetail .financial-completeness')).to_contain_text('백만 USD')
    assert loads.count('900001')==1,loads
    assert not errors,errors
    browser.close()
print('PASS same market cards home/trend, trend changes, current/written risk+alternatives5/40/5, native-only USD FY2027Q1 brief/detail, stale reference labels, lazy metadata updates, mobile390/320, JS errors0')
