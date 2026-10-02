"""Reviewed financials survive discovery metadata; identities never cross."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace,script_json
from playwright.sync_api import sync_playwright,expect

fixture=make_fixture()
for row in fixture['companies']:
    for q in row.get('quarters',[]):q['net_income']=q['op']*.8
html=export_workspace(fixture)
prefix,tail=html.split('const WORKSPACE_DATA=',1)
payload=json.JSONDecoder().raw_decode(tail)[0]
snap=payload['analysis_snapshot']
meta=dict(snap['meta'],discovery=True)
meta.pop('financial_basis');meta.pop('financial_period')
payload['discovery']={'snapshot':{'meta':meta,'companies':snap['companies']},'research':payload['research']}
code=snap['companies'][0]['code']
model=payload['company_details'][code]
latest=next(g for g in model['groups'] if g['basis']==snap['meta']['financial_basis'] and g['cadence']=='quarter')['columns'][-1]
assert latest['values']['revenue'] is not None
def render(data):return prefix+'const WORKSPACE_DATA='+script_json(data)+tail[tail.index(';</script>'):]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
    page=browser.new_page(viewport={'width':1440,'height':1100});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.set_content(render(payload),wait_until='load')
    page.locator('[data-page=brief]').click();page.locator('#researchCompany').select_option(code)
    for key in ['revenue','op','net']:
        expect(page.locator(f'[data-brief-metric={key}] b')).not_to_have_text('—')
        expect(page.locator(f'[data-brief-metric={key}] small')).to_have_text(latest['period_end'])
    expect(page.locator('#research .section-title')).to_contain_text(snap['meta']['financial_basis'])
    expect(page.locator('.brief-comparison svg')).to_have_count(3)
    # A renamed issuer must not inherit the old company's monetary amounts.
    payload['discovery']['snapshot']['companies'][0]['name']='다른 식별정보'
    page.goto('about:blank')
    page.set_content(render(payload),wait_until='load')
    page.locator('[data-page=brief]').click();page.locator('#researchCompany').select_option(code)
    for key in ['revenue','op','net','borrowings']:
        expect(page.locator(f'[data-brief-metric={key}] b')).to_have_text('—')
    expect(page.locator('.brief-comparison')).to_have_count(0)
    assert not errors,errors
    browser.close()
print('PASS discovery financials: missing global basis retains matched reviewed amounts/period, changed identity does not inherit amounts')
