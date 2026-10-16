"""Offline result view: actual app rendering, synthetic data, no external requests."""
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace,script_json
from investment.shared_dashboard import payload_from_html
from playwright.sync_api import sync_playwright,expect
from tools.browser_runtime import chromium_options

snapshot=make_fixture()
for row in snapshot['companies']:
    for bar in row['prices']:bar.update(final=True,open=bar['close'])
for bars in snapshot['benchmarks'].values():
    for bar in bars:bar.update(final=True,venue='KRX',adjustment_basis='index_level')
content=export_workspace(snapshot,result_view=True)
payload=payload_from_html(content)
assert payload['detail_html'] is None
assert payload['company_details']
# A calculated company outside the original reviewed subset must retain details.
extra=payload['analysis_snapshot']['companies'][1]['code']
payload['discovery']={'snapshot':deepcopy(payload['analysis_snapshot']),'research':deepcopy(payload['research'])}
payload['discovery']['snapshot']['meta'].update(discovery=True,financial_basis=None)
for row in payload['discovery']['snapshot']['companies']:
    row['legacy_available']=row['code']!=extra
payload['analysis_snapshot']['companies']=payload['analysis_snapshot']['companies'][:1]
prefix,tail=content.split('const WORKSPACE_DATA=',1)
import json
_,length=json.JSONDecoder().raw_decode(tail)
content=prefix+'const WORKSPACE_DATA='+script_json(payload)+tail[length:]
with tempfile.TemporaryDirectory() as temp:
    path=Path(temp)/'dashboard.html';path.write_text(content,encoding='utf-8')
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,**chromium_options())
        page=browser.new_page(viewport={'width':1440,'height':1000})
        errors=[];requests=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.route('http://**/*',lambda route:(requests.append(route.request.url),route.abort()))
        page.route('https://**/*',lambda route:(requests.append(route.request.url),route.abort()))
        page.goto(path.as_uri(),wait_until='load')
        page.locator('[data-page=brief]').click()
        expect(page.locator('[data-brief-metric="revenue"] b')).not_to_have_text('—')
        page.locator('[data-context-page=company]').click()
        expect(page.locator('#sdCompany')).to_be_visible()
        page.locator('#sd-tab-financial').click()
        expect(page.locator('#sd-statement')).to_be_visible()
        page.locator('[data-page=brief]').click()
        page.locator('#researchCompany').select_option(extra)
        expect(page.locator('[data-research-go=company]').first).to_be_enabled()
        page.locator('[data-research-go=company]').first.click()
        expect(page.locator('#sdCompany')).to_have_value(extra)
        for width in (390,320):
            page.set_viewport_size({'width':width,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors,errors
        assert not requests,requests
        browser.close()
print('PASS shared results: offline company metrics/detail, 1440/390/320px, no network, no holdings frame')
