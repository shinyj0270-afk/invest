"""Full dashboard navigation, escaping, empty/error state and mobile research view."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from tools.browser_runtime import chromium_options
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace

html=export_workspace(make_fixture(),live={'token':'fixture'})
data=dict(status='ready',profile='work',cards=[],theses=[dict(id='t',revision=1,value=dict(title='<img src=x onerror=alert(1)>',claim='Synthetic claim',as_of='2026-01-03',status='active',invalidation=['Demand falls'],instruments=[]))])
data['sources']=[dict(id='source',revision=1,kind='source',stage='raw',value=dict(title='Original source',url='javascript:alert(1)',origin='independent',access='public'))]
data['masters']=[dict(id='minervini',name='Minervini')]
data['theses'][0]['evidence']=[dict(id='e1',revision=1,recorded_at='2026-01-05',value=dict(thesis_revision=1,stance='refute',observed_on='2026-01-04',observation='Demand actually fell',reasoning='Refutation evidence'),provenance=[dict(id='s2',value=dict(title='Official demand series',url='https://example.invalid/demand'))])]
data['theses'][0].update(metadata=dict(persons=['minervini'],topic='Capacity',sector='Semiconductors',instruments=[dict(code='005930')]),stage='derived',history=[dict(revision=1,recorded_at='2026-01-03',value=dict(claim='Old claim',change_reason='Initial')),dict(revision=2,recorded_at='2026-01-04',value=dict(claim='New claim',change_reason='New evidence'))],catalog_history=[dict(revision=1,recorded_at='2026-01-04',value=dict(stage='derived',reason='Classified',source_note='Official filing'))])
data['notes']=[dict(id='note',revision=1,kind='agent_note',stage='derived',metadata={},value=dict(title='Reviewed session note',claim='Conditional reviewed hypothesis',as_of='2026-01-03',invalidation=['Countercondition'],conditions=['<svg onload=alert(2)> condition'],missing_evidence=['Independent comparison missing'],claims=[dict(statement='Attributed author opinion',stance='context',source_ids=['source'])],approval=dict(reviewer='Synthetic human',reviewed_on='2026-01-04'),review=dict(verdict='pass')),provenance=[dict(id='source',value=dict(title='Approved public source',url='https://example.invalid/report',access='public',origin='independent'))])]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,**chromium_options())
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    def route(r):
        if r.request.url.endswith('/research-library'):
            assert r.request.headers.get('x-dashboard-token')=='fixture'
            r.fulfill(content_type='application/json',body=json.dumps(data))
        elif r.request.url.endswith('/'):r.fulfill(content_type='text/html',body=html)
        else:r.fulfill(content_type='application/json',body='{"records":[],"status":"idle"}')
    page.route('http://127.0.0.1:8767/**',route);page.goto('http://127.0.0.1:8767/')
    page.locator('#pageSelect').select_option('research-library',force=True)
    expect(page.locator('#researchLibrary')).to_be_visible()
    expect(page.locator('#libraryStatus')).to_contain_text('ready')
    assert page.locator('#researchLibrary img').count()==0
    expect(page.locator('#researchLibrary')).to_contain_text('<img src=x')
    assert page.locator('#researchLibrary a[href^="javascript:"]').count()==0
    page.locator('#libraryFilters [name=person]').select_option('minervini')
    page.locator('#libraryFilters [name=topic]').select_option('Capacity')
    page.locator('#libraryFilters [name=sector]').select_option('Semiconductors')
    page.locator('#libraryFilters [name=company]').fill('005930')
    page.locator('#libraryFilters [name=stage]').select_option('derived')
    page.locator('#libraryFilters button').first.click()
    assert page.locator('.library-record').count()==1
    page.locator('.library-record summary').click()
    expect(page.locator('.library-record')).to_contain_text('New evidence')
    expect(page.locator('.library-record')).to_contain_text('Official filing')
    expect(page.locator('.library-record')).to_contain_text('반박 근거')
    expect(page.locator('.library-record')).to_contain_text('Demand actually fell')
    expect(page.locator('.library-record')).to_contain_text('Official demand series')
    page.locator('#libraryFilters [name=query]').fill('no matching text')
    page.locator('#libraryFilters button').first.click()
    assert page.locator('.library-record').count()==0
    page.locator('#libraryReset').click()
    assert page.locator('.library-record').count()==3
    expect(page.locator('#researchLibrary')).to_contain_text('사람 검토 연구노트')
    expect(page.locator('#researchLibrary')).to_contain_text('Synthetic human')
    assert page.locator('#researchLibrary svg').count()==0
    page.locator('#libraryFilters [name=query]').fill('Independent comparison missing')
    page.locator('#libraryFilters button').first.click()
    assert page.locator('.library-record').count()==1
    expect(page.locator('.library-record')).to_contain_text('Approved public source')
    page.locator('#libraryReset').click()
    for width in (390,320):
        page.set_viewport_size({'width':width,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert page.locator('#researchLibrary button,#researchLibrary input,#researchLibrary select').evaluate_all('(els)=>els.every(el=>el.getBoundingClientRect().height>=44)')
    data['theses']=[];data['notes']=[];data['status']='empty'
    page.locator('#libraryReload').click()
    expect(page.locator('#researchLibrary')).to_contain_text('저장된 산업 가설이 없습니다')
    page.locator('#pageSelect').select_option('home',force=True);expect(page.locator('#home')).to_be_visible()
    page.route('**/research-library',lambda r:r.fulfill(status=503,body='{}'))
    page.locator('#pageSelect').select_option('research-library',force=True);page.locator('#libraryReload').click()
    expect(page.locator('#libraryStatus')).to_contain_text('연결 대기')
    assert not errors,errors
    browser.close()
print('PASS Research Library full navigation / XSS / empty / error / mobile')
