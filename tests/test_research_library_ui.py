"""Full dashboard navigation, escaping, empty/error state and mobile research view."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from tools.browser_runtime import chromium_options
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace
from investment.research_library_view import recent_stories

html=export_workspace(make_fixture(),live={'token':'fixture'})
data=dict(status='ready',profile='work',cards=[],theses=[dict(id='t',revision=1,value=dict(title='<img src=x onerror=alert(1)>',claim='Synthetic claim',as_of='2026-01-03',status='active',invalidation=['Demand falls'],instruments=[]))])
data['sources']=[dict(id='source',revision=1,kind='source',stage='raw',value=dict(title='Original source',url='javascript:alert(1)',origin='independent',access='public'))]
data['masters']=[dict(id='minervini',name='Minervini')]
data['theses'][0]['evidence']=[dict(id='e1',revision=1,recorded_at='2026-01-05',value=dict(thesis_revision=1,stance='refute',observed_on='2026-01-04',observation='Demand actually fell',reasoning='Refutation evidence'),provenance=[dict(id='s2',value=dict(title='Official demand series',url='https://example.invalid/demand'))])]
data['theses'][0].update(metadata=dict(persons=['minervini'],topic='Capacity',sector='Semiconductors',instruments=[dict(code='005930')]),stage='derived',history=[dict(revision=1,recorded_at='2026-01-03',value=dict(claim='Old claim',change_reason='Initial')),dict(revision=2,recorded_at='2026-01-04',value=dict(claim='New claim',change_reason='New evidence'))],catalog_history=[dict(revision=1,recorded_at='2026-01-04',value=dict(stage='derived',reason='Classified',source_note='Official filing'))])
data['notes']=[dict(id='note',revision=1,kind='agent_note',stage='derived',metadata={},value=dict(title='Reviewed session note',claim='Conditional reviewed hypothesis',as_of='2026-01-03',invalidation=['Countercondition'],conditions=['<svg onload=alert(2)> condition'],missing_evidence=['Independent comparison missing'],claims=[dict(statement='Attributed author opinion',stance='context',source_ids=['source'])],approval=dict(reviewer='Synthetic human',reviewed_on='2026-01-04'),review=dict(verdict='pass')),provenance=[dict(id='source',value=dict(title='Approved public source',url='https://example.invalid/report',access='public',origin='independent'))])]
data['notes'][0]['recorded_at']='2026-01-06T00:00:00+00:00'
data['theses'][0]['kind']='thesis'
data['theses'][0]['recorded_at']='2026-01-05T00:00:00+00:00'
data['theses'][0]['value']['conditions']=['First condition','Second condition']
data['theses'][0]['provenance']=[dict(id='s2',value=dict(title='Official demand series',url='https://example.invalid/demand',published_on='2025-12-01'))]
data['cards']=[dict(id='card',kind='master',recorded_at='2026-01-04T00:00:00+00:00',revision=1,
    value=dict(title='Synthetic research card',principle='Synthetic principle',conditions=['Condition one','Condition two'],counterexamples=['Counterexample']),
    provenance=[dict(id='s3',value=dict(title='Earlier publication',url='https://example.invalid/earlier',published_on='2000-01-01'))])]
data['stories']=recent_stories(data)
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
    expect(page.locator('#libraryStories .library-story')).to_have_count(3)
    assert page.locator('.library-story-heading h4').all_text_contents()==['Reviewed session note','<img src=x onerror=alert(1)>','Synthetic research card']
    assert page.locator('#libraryFilters').evaluate('(el)=>el.compareDocumentPosition(document.getElementById("libraryStories"))&Node.DOCUMENT_POSITION_FOLLOWING')
    assert page.locator('#libraryStories').evaluate('(el)=>el.compareDocumentPosition(document.getElementById("libraryResults"))&Node.DOCUMENT_POSITION_FOLLOWING')
    for story in page.locator('.library-story').all():
        assert 5<=story.locator('.library-story-lines p').count()<=10
        expect(story.locator('.library-story-sources a').first).to_be_visible()
    source_record=page.locator('.library-source-record').first
    assert source_record.locator('details').get_attribute('open') is None
    assert source_record.locator('h4').evaluate('e=>parseFloat(getComputedStyle(e).fontSize)')>source_record.locator('.library-source-summary').evaluate('e=>parseFloat(getComputedStyle(e).fontSize)')
    expect(source_record.locator('.library-source-summary')).not_to_contain_text('independent')
    page.locator('#libraryFilters [name=person]').select_option('minervini')
    page.locator('#libraryFilters [name=topic]').select_option('Capacity')
    page.locator('#libraryFilters [name=sector]').select_option('Semiconductors')
    page.locator('#libraryFilters [name=company]').fill('005930')
    page.locator('#libraryFilters [name=stage]').select_option('derived')
    page.locator('#libraryFilters button').first.click()
    assert page.locator('.library-record').count()==1
    expect(page.locator('#libraryStories .library-story')).to_have_count(1)
    page.locator('.library-record summary').click()
    expect(page.locator('.library-record')).to_contain_text('New evidence')
    expect(page.locator('.library-record')).to_contain_text('Official filing')
    expect(page.locator('.library-record')).to_contain_text('반박 근거')
    expect(page.locator('.library-record')).to_contain_text('Demand actually fell')
    expect(page.locator('.library-record')).to_contain_text('Official demand series')
    page.locator('#libraryFilters [name=query]').fill('no matching text')
    page.locator('#libraryFilters button').first.click()
    assert page.locator('.library-record').count()==0
    expect(page.locator('#libraryStories .library-story')).to_have_count(0)
    page.locator('#libraryReset').click()
    assert page.locator('.library-record').count()==4
    expect(page.locator('#researchLibrary')).to_contain_text('사람 검토 연구노트')
    expect(page.locator('#researchLibrary')).to_contain_text('Synthetic human')
    assert page.locator('#researchLibrary svg').count()==0
    page.locator('#libraryFilters [name=query]').fill('Independent comparison missing')
    page.locator('#libraryFilters button').first.click()
    assert page.locator('.library-record').count()==1
    expect(page.locator('.library-record')).to_contain_text('Approved public source')
    page.locator('#libraryReset').click()
    page.locator('[data-story-id="note"]').click()
    expect(page.locator('#library-record-agent_note-note')).to_be_in_viewport()
    for width in (390,320):
        page.set_viewport_size({'width':width,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert page.locator('#researchLibrary button,#researchLibrary input,#researchLibrary select').evaluate_all('(els)=>els.every(el=>el.getBoundingClientRect().height>=44)')
    (ROOT/'validation/current/library-stories').mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(ROOT/'validation/current/library-stories/mobile.png'),full_page=True)
    page.set_viewport_size({'width':1440,'height':1000})
    page.screenshot(path=str(ROOT/'validation/current/library-stories/desktop.png'),full_page=True)
    data['theses']=[];data['notes']=[];data['cards']=[];data['stories']=[];data['status']='empty'
    page.locator('#libraryReload').click()
    expect(page.locator('#researchLibrary')).to_contain_text('저장된 산업 가설이 없습니다')
    expect(page.locator('#libraryStories')).to_contain_text('요약할 연구가 부족')
    page.locator('#pageSelect').select_option('home',force=True);expect(page.locator('#home')).to_be_visible()
    page.route('**/research-library',lambda r:r.fulfill(status=503,body='{}'))
    page.locator('#pageSelect').select_option('research-library',force=True);page.locator('#libraryReload').click()
    expect(page.locator('#libraryStatus')).to_contain_text('연결 대기')
    assert not errors,errors
    browser.close()
print('PASS Research Library full navigation / XSS / empty / error / mobile')
