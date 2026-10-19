"""Synthetic static and result-view navigation; no real server or DB."""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace,script_json
from investment.industry_phase import load_config as phase_config
from investment.leader_strategy import load_config as leader_config
from tools.browser_runtime import chromium_options
from playwright.sync_api import sync_playwright,expect

html=export_workspace(make_fixture());prefix,tail=html.split('const WORKSPACE_DATA=',1);data=json.JSONDecoder().raw_decode(tail)[0]
snap=copy.deepcopy(data['snapshot']);research=copy.deepcopy(data['research'])
for r in snap['companies']:r.update(industry='검증산업',market='KOSPI',discovery_allowed=True)
snap['meta']['discovery']=True;data['discovery']={'snapshot':snap,'research':research}
data['market_insights']={'sectors':[dict(market='KOSPI',industry='검증산업',short_rs={'1m':{'score':80,'return_pct':10,'count':8}})]}
data['industry_phase']={'status':'ready','config':phase_config(),'rows':{r['code']:{'phase':'왕'} for r in snap['companies']},
 'sectors':[dict(market='KOSPI',industry='검증산업',eligible=8,missing=0,rankable=True,cap_eligible=8,recent_weak=2,
     growth={'pct':75,'count':6,'cap_pct':80,'cap_total_eok':10000},decline={'pct':25,'count':2,'cap_pct':20})]}
leader_rows=[]
for i,r in enumerate(snap['companies'][:3]):
    leader_rows.append(dict(code=r['code'],name='<img src=x onerror=alert(1)>' if i==0 else r['name'],market='KOSPI' if i<2 else 'KOSDAQ',industry='검증산업',
      momentum_pct=10,turnover_change_pct=20,momentum_z=2,turnover_z=2,momentum_band='상',turnover_band='상',
      turnover_method='adjusted_close_volume_proxy',value_band='중립' if i!=1 else '미확인',value_metrics=['per','pbr'],value_period='2026-06-30',value_basis='CFS',reason='' if i!=1 else '가치지표 미확보',candidate=i!=1))
data['leader_strategy']={'status':'ready','config':leader_config(),'rows':leader_rows,'as_of':snap['meta']['price_date']}
def document(payload):return prefix+'const WORKSPACE_DATA='+script_json(payload)+tail[tail.index(';</script>'):]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,**chromium_options());errors=[];requests=[]
    for result in (False,True):
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.on('pageerror',lambda e:errors.append(str(e)));page.route('**/*',lambda r:(requests.append(r.request.url),r.abort()))
        payload=copy.deepcopy(data);payload['result_view']=result
        page.set_content(document(payload),wait_until='load')
        page.locator('#pageSelect').select_option('industry',force=True)
        expect(page.locator('#industryView')).to_contain_text('국면 확산')
        page.locator('#industryView [data-industry]').first.click()
        expect(page.locator('[data-phase-facts]')).to_contain_text('생+왕 기업 비중75%')
        expect(page.locator('[data-phase-facts]')).to_contain_text('최근 20거래일 쇠 진입2개')
        page.locator('#pageSelect').select_option('leader-strategy',force=True);v=page.locator('#leaderStrategy')
        expect(v).to_be_visible();expect(v.locator('[data-leader-cell]')).to_have_count(9)
        expect(v.locator('[data-leader-company]')).to_have_count(1)
        assert v.locator('img,script,svg').count()==0
        v.locator('[data-leader-cell="상|상"]').click();expect(v.locator('[data-leader-company]')).to_have_count(2)
        expect(v).to_contain_text('가치지표 미확보')
        v.locator('#leaderFilters [name=value]').select_option('중립');v.locator('#leaderFilters button[type=submit],#leaderFilters button:not([type])').first.click()
        expect(v.locator('[data-leader-company]')).to_have_count(1)
        for width in (1440,390,320):
            page.set_viewport_size({'width':width,'height':900});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
        v.locator('[data-leader-industry]').first.click();expect(page.locator('#industryView')).to_be_visible()
        page.locator('#pageSelect').select_option('leader-strategy',force=True)
        v.locator('[data-leader-company]').first.click();expect(page.locator('#research')).to_be_visible()
        page.close()
    assert not errors,errors;assert not requests,requests
    browser.close()
print('PASS phase detail, leader 9 cells/filter/company/industry links, XSS, result/static no requests, 1440/390/320px')
