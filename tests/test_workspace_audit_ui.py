"""Regression journeys for candidate navigation, tab storage, and filtered selection."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace,script_json
from playwright.sync_api import sync_playwright,expect

def open_tools(page):
    if page.locator('#moreNavigation').get_attribute('open') is None:
        page.locator('#moreNavigation summary').click()


html=export_workspace(make_fixture())
payload=json.JSONDecoder().raw_decode(html.split('const WORKSPACE_DATA=',1)[1])[0]
snapshot=payload['analysis_snapshot']
payload['discovery']={'snapshot':{'meta':dict(snapshot['meta'],discovery=True),
    'companies':[dict(r,legacy_available=False) for r in snapshot['companies']]},'research':payload['research']}
prefix,tail=html.split('const WORKSPACE_DATA=',1)
html=prefix+'const WORKSPACE_DATA='+script_json(payload)+tail[tail.index(';</script>'):]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.route('http://127.0.0.1:8799/**',lambda r:r.fulfill(body=html,content_type='text/html'))
    page.goto('http://127.0.0.1:8799/')
    page.locator('[data-page=finder]').click()
    star=page.locator('[data-watch]').first;code=star.get_attribute('data-watch');star.click()
    page.locator('#discoveryFilters [name=query]').fill(code)
    page.locator('#discoveryFilters button[type=submit]').click()
    page.reload()
    expect(page.locator(f'[data-watch="{code}"]')).to_have_attribute('aria-pressed','true')
    expect(page.locator('#discoveryFilters [name=query]')).to_have_value(code)
    # Saved files retain the same validated identities, independent of browser storage.
    with page.expect_download() as d:page.locator('#watchExport').click()
    saved=Path(d.value.path()).read_bytes()
    assert json.loads(saved)['companies'][0]['code']==code
    page.locator('[data-watch]').first.click()
    page.locator('#watchImport').set_input_files({'name':'watch.json','mimeType':'application/json','buffer':saved})
    expect(page.locator(f'[data-watch="{code}"]')).to_have_attribute('aria-pressed','true')
    page.locator('[data-research-code]').first.click()
    page.reload()
    expect(page.locator('body')).to_have_attribute('data-current-page','brief')
    expect(page.locator('#researchCompany')).to_have_value(code)
    expect(page.locator('[data-research-go=company]')).to_be_disabled()
    for target in ['holdings','portfolio']:
        open_tools(page);page.locator('[data-page='+target+']').click();expect(page.locator('#legacy')).to_be_visible()
        expect(page.locator('#legacyTitle')).to_contain_text('보유' if target=='holdings' else '포트폴리오')
    open_tools(page);page.locator('[data-page=advanced]').click()
    second=page.locator('[data-av-code]').nth(1);name=second.inner_text().split(' · ')[0]
    page.locator('#avFilters [name=query]').fill(name);page.locator('#avFilters button').first.click()
    expect(page.locator('#avCompany')).to_contain_text(name)
    page.reload();expect(page.locator('#avCompany')).to_contain_text(name)
    page.locator('#avFilters [name=query]').fill('no-such-company');page.locator('#avFilters button').first.click()
    expect(page.locator('#avCompany')).to_contain_text('선택 기업 없음')
    expect(page.locator('[data-av-code]')).to_have_count(0)
    page.locator('#avReset').click();expect(page.locator('[data-av-code]').first).to_be_visible()
    # Removed/renamed identities are excluded on restore, rather than silently remapped.
    page.locator('[data-page=finder]').click()
    page.evaluate("sessionStorage.setItem('investment-research-v1-fixture',JSON.stringify({watch:{version:1,data_mode:'fixture',companies:[{code:'900001',name:'old identity',market:'KOSPI'}]}}))")
    page.reload();expect(page.locator('#researchNotice')).to_contain_text('제외')
    expect(page.locator('[data-watch][aria-pressed=true]')).to_have_count(0)
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#pageSelect').select_option('advanced')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    assert not errors,errors
    browser.close()
print('PASS audit: watch/filter reload, export/import, identity change, candidate navigation, selection/empty/reset, mobile')
