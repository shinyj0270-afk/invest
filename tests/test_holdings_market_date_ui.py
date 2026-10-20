"""Synthetic holdings frame: the market badge follows saved daily closes; the Infomax review date stays visible."""
import copy,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from investment.fixture import make_fixture
from investment.workspace_export import export_holdings_frame
from tools.browser_runtime import chromium_options

snapshot=make_fixture();snapshot['meta']['data_mode']='user_input'
snapshot['companies'][0]['sources']=[dict(label=f'합성 누적 출처 {i+1}',url=f'https://example.invalid/reports/{i+1}') for i in range(75)]
code=snapshot['companies'][0]['code']
bar=dict(date='2026-10-14',close=123,final=True,venue='KRX',adjustment_basis='naver_chart_adjusted')
market=dict(universe=dict(schema_version='naver-universe-0.1',companies=[]),
    history=dict(calendar=dict(sessions=['2026-10-13','2026-10-14']),histories={code:dict(symbol=code,kind='item',prices=[copy.deepcopy(bar)])}))
html=export_holdings_frame(snapshot,market_cache=market)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,**chromium_options())
    context=browser.new_context(viewport={'width':1440,'height':1000})
    context.clock.set_fixed_time('2026-10-15T10:00:00+09:00')
    page=context.new_page();errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.set_content(html,wait_until='load')
    assert page.evaluate("typeof window.INVESTMENT_ACTIVATE==='function'"),errors
    assert page.evaluate('window.INVESTMENT_INITIAL_SNAPSHOT.companies[0].sources.length')==75
    page.evaluate("window.INVESTMENT_ACTIVATE&&window.INVESTMENT_ACTIVATE('holdings')")
    expect(page.locator('#pScope')).to_contain_text('시장자료 2026-10-14')
    expect(page.locator('#pScope')).to_contain_text('인포맥스 검토 2026-09-23')
    expect(page.locator('#pScopeDetail')).to_contain_text('인포맥스 검토 스냅샷 2026-09-23')
    assert not errors,errors
    browser.close()
print('PASS holdings frame initializes with 75 preserved sources and keeps saved daily close / Infomax review dates separate')
