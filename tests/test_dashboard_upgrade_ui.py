"""Monthly recommendation viewer using synthetic responses, never real records."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from tools.browser_runtime import chromium_options
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace
from investment.recommendations import propose
from tests.test_dashboard_upgrade import recommendation_context
first=propose(recommendation_context(),created_on='2026-10-02')
first['performance']={'status':'pending','reason':'작성 후 첫 완료 거래일 대기'}
second=propose(recommendation_context(),created_on='2026-10-03',kind='exception',reason='가상 검증 공시',previous=first)
second['performance']=first['performance']
records=[first];requests=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,**chromium_options())
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    html=export_workspace(make_fixture(),live={'token':'synthetic','daily_prices':True})
    def routes(route):
        path=route.request.url
        if path.endswith('/recommendations'):
            requests.append(route.request.method)
            if route.request.method=='POST':
                assert route.request.post_data_json['reason']=='가상 검증 공시'
                records.append(second)
            route.fulfill(status=200,content_type='application/json',body=json.dumps({'version':1,'records':records},ensure_ascii=False))
        elif path.endswith('/'):
            route.fulfill(status=200,content_type='text/html',body=html)
        else:route.fulfill(status=200,content_type='application/json',body='{"status":"idle"}')
    page.route('http://127.0.0.1:8767/**',routes)
    page.goto('http://127.0.0.1:8767/',wait_until='load')
    expect(page.locator('#recommendationHome')).to_contain_text('가상0')
    expect(page.locator('#recommendationHome')).to_contain_text('16%')
    page.locator('#navigation > [data-page=recommendations]').click()
    expect(page.locator('body')).to_have_attribute('data-current-page','recommendations')
    assert '条件' not in page.locator('#contextNavigation').inner_text()
    expect(page.locator('#recommendationView')).to_contain_text('자료 기준 추천 초안')
    expect(page.locator('#recommendationView')).to_contain_text('측정 대기')
    page.locator('#recommendationView textarea').fill('가상 검증 공시')
    page.locator('[data-rec-exception] button').click()
    expect(page.locator('[data-rec-version] option')).to_have_count(2)
    expect(page.locator('#recommendationView')).to_contain_text('가상 검증 공시')
    page.locator('[data-rec-version]').select_option('0')
    expect(page.locator('#recommendationView h3').first).to_contain_text('월간 기준안')
    for width in [390,320]:
        page.set_viewport_size({'width':width,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert requests==['GET','POST'],requests
    assert not errors,errors
    browser.close()
print('PASS synthetic monthly/exception versions, reasons, pending performance, mobile390/320, no JS errors')
