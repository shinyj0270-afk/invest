"""Synthetic-only UI integration for rolling charts and immutable cohort status."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from tools.browser_runtime import chromium_options
from investment.portfolio_risk import rolling_relationship,path_metrics

dates=[f'2025-{i:03d}' for i in range(253)]  # Label-only synthetic chart dates.
y=[((i%7)-3)/100 for i in range(252)];x=[2*r for r in y]
r=dict(status='ready',definition='Synthetic',**path_metrics(dates,x,y),rolling=rolling_relationship(dates,x,y))
data=dict(status='ready',profile='work',masters=[],sources=[],cards=[],notes=[],stories=[],theses=[
    dict(id='TEST',revision=1,recorded_at='2026-10-26',metadata={},value=dict(title='Synthetic thesis',claim='Unverified',conditions=[],invalidation=[],instruments=[]),
         followup=dict(status='waiting',frozen_on='2026-10-26',candidates=5,selection_rule='<img src=x onerror=alert(1)>',reason='관측기간 미도래',horizons=[
             dict(days=n,label=label,status='waiting',remaining_sessions=n) for n,label in [(63,'3개월'),(126,'6개월'),(252,'12개월')]]))])
html='<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:8px}svg{max-width:100%}.tscroll{max-width:100%;overflow:auto}td,th{white-space:nowrap}input,select{max-width:95%}</style></head><body><div id="risk"></div><div id="library"></div>'
for name in ['dashboard_upgrade_ui.js','research_library_ui.js']:
    html+='<script>'+(ROOT/'src'/name).read_text(encoding='utf-8')+'</script>'
html+='<script>document.querySelector("#risk").innerHTML=DashboardUpgradeUI.financialSeries('+json.dumps(r)+');ResearchLibraryUI.create(document.querySelector("#library"),{token:"synthetic"}).render();</script></body></html>'
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,**chromium_options());page=browser.new_page();errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.route('http://127.0.0.1:8767/**',lambda route:route.fulfill(content_type='application/json',body=json.dumps(data)) if route.request.url.endswith('/research-library') else route.fulfill(content_type='text/html',body=html))
    page.goto('http://127.0.0.1:8767/')
    rolling=page.locator('[data-rolling-risk]');expect(rolling).to_contain_text('시장 베타')
    rolling.locator('summary').click();expect(rolling.locator('svg')).to_have_count(2)
    expect(rolling).to_contain_text('2')
    follow=page.locator('[data-research-followup]');expect(follow).to_contain_text('63거래일')
    expect(follow).to_contain_text('기간 대기');expect(follow).to_contain_text('미도래')
    follow.locator('summary').click();expect(follow).to_contain_text('<img src=x onerror=alert(1)>')
    assert page.locator('#library img').count()==0
    for width in (1440,390,320):
        page.set_viewport_size(dict(width=width,height=1000))
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
    assert not errors,errors
    browser.close()
print('PASS rolling beta/correlation charts, forward waiting state, escaping and 1440/390/320px')
