"""Offline fixture checks for simplified navigation and the personal home flow."""
import os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
(ROOT/'validation/current').mkdir(parents=True,exist_ok=True)
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace
from playwright.sync_api import sync_playwright,expect

snapshot=make_fixture()
for bars in snapshot['benchmarks'].values():
    for b in bars:b['final']=True
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];network=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:network.append(r.url) if r.url.startswith(('http:','https:')) else None)
    page.set_content(export_workspace(snapshot),wait_until='load')
    expect(page.locator('#home')).to_be_visible()
    assert page.locator('#moreNavigation').get_attribute('open') is None
    assert page.locator('#navigation>.nav-item').count()==7
    assert page.locator('#navigation svg.iconify').count()==10
    assert page.locator('#navigation svg:not([aria-hidden="true"])').count()==0
    expect(page.get_by_role('button',name='기업 찾기',exact=True)).to_have_accessible_name('기업 찾기')
    expect(page.locator('#moreNavigation summary')).to_have_count(0)
    expect(page.locator('#moreNavigation [data-page=overview]')).to_be_visible()
    page.get_by_role('button',name='자료 비교',exact=True).focus()
    page.keyboard.press('Enter')
    expect(page.locator('body')).to_have_attribute('data-current-page','overview')
    page.locator('[data-page=home]').focus();page.keyboard.press('Enter')
    # The menu uses solid foreground/plane colors; walk transparent ancestors.
    contrast=page.locator('#navigation .nav-item,#moreNavigation summary').evaluate_all('''els=>els.map(el=>{
      const rgb=s=>(s.match(/[\\d.]+/g)||[]).map(Number),lum=c=>c.slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0);
      let parent=el,bg;while(parent){bg=rgb(getComputedStyle(parent).backgroundColor);if(bg.length===3||bg[3]===1)break;parent=parent.parentElement;}
      const a=lum(rgb(getComputedStyle(el).color)),b=lum(bg);return (Math.max(a,b)+.05)/(Math.min(a,b)+.05);
    })''')
    assert min(contrast)>=4.5,contrast
    expect(page.locator('#viewFreshness')).to_be_hidden()
    page.locator('#workspaceStatus>summary').click()
    expect(page.locator('#viewFreshness')).to_be_visible()
    expect(page.locator('#viewFreshness')).to_contain_text('발굴 모집단')
    assert page.locator('#moreNavigation .nav-item').all_text_contents()==['자료 비교','고급 시각화','Research Library']
    options=page.locator('#pageSelect option').evaluate_all('(items)=>items.map(item=>item.value)')
    assert len(options)==len(set(options))==23
    assert page.locator('#sourceDetails').get_attribute('open') is None
    expect(page.locator('#homeMarketCharts')).to_contain_text('KOSPI')
    expect(page.locator('#homeVerdict')).to_contain_text('오늘의 결론')
    expect(page.locator('#homeKpis')).to_contain_text('탐색 범위')
    expect(page.locator('#moreNavigation [data-page=overview]')).to_be_visible()
    page.screenshot(path=str(ROOT/'validation/current/navigation-expanded-desktop.png'))
    page.locator('#moreNavigation .nav-item').first.click()
    assert page.locator('#moreNavigation').get_attribute('open') is None
    comparison=['overview','prices','bars','heatmap','scatter','data']
    assert page.locator('#contextNavigation button').count()==6
    page.screenshot(path=str(ROOT/'validation/current/navigation-comparison-desktop.png'))
    for view in comparison:
        if view!='overview' and page.locator('#contextNavigation details').get_attribute('open') is None:
            page.locator('#contextNavigation summary').click()
        page.locator(f'[data-context-page={view}]').click()
        expect(page.locator('body')).to_have_attribute('data-current-page',view)
        expect(page.locator('[data-page=overview]')).to_have_attribute('aria-current','page')
        expect(page.locator(f'[data-context-page={view}]')).to_have_attribute('aria-current','page')
        expect(page.locator('#pageSelect')).to_have_value(view)
        expect(page.locator('#workspacePath')).to_contain_text('자료 비교 /')
        expect(page.locator('#viewFreshness')).to_contain_text('전체의 원수치' if view=='data' else '선택 기업')
        assert 'current' in page.locator('#moreNavigation').get_attribute('class')
    page.locator('[data-page=home]').click()
    expect(page.locator('#homeWatch')).to_contain_text('별표')
    page.locator('#homeQuery').fill('900002');page.locator('#homeSearch button').click()
    expect(page.locator('#discoveryTable tbody tr')).to_have_count(1)
    page.locator('[data-watch="900002"]').click()
    expect(page.locator('[data-watch="900002"] svg')).to_have_attribute('data-icon','tabler:star-filled')
    page.locator('[data-page=home]').click()
    expect(page.locator('#homeWatch [data-home-code="900002"]')).to_be_visible()
    page.locator('#homeWatch [data-home-code="900002"]').click()
    expect(page.locator('#researchCompany')).to_have_value('900002')
    page.locator('[data-context-page=trend]').click()
    expect(page.locator('#research')).to_contain_text('900002')
    page.locator('[data-context-page=brief]').click()
    page.locator('[data-context-page=company]').click()
    expect(page.locator('#sdCompany')).to_have_value('900002')
    expect(page.locator('#viewFreshness')).to_contain_text('선택 기업 저장자료')
    expect(page.locator('#sdSettings svg')).to_have_attribute('data-icon','tabler:settings')
    expect(page.locator('#sdWatch svg')).to_have_attribute('data-icon','tabler:star-filled')
    page.locator('[data-page=holdings]').click()
    frame=page.frame_locator('#detailFrame')
    frame.locator('#pManagement summary').click();frame.locator('#pFixture').click()
    page.locator('[data-page=home]').click()
    expect(page.locator('#homeHoldings')).to_contain_text('가상 테스트')
    assert page.locator('#homeHoldings .home-company').count()>0
    expect(page.locator('#homeHoldings .brief-item').first).to_contain_text('첫 관측')
    expect(page.locator('#homeHoldings .brief-basis').first).to_contain_text('확인')
    assert page.locator('#homeHoldings .brief-item').count()==page.locator('#homeHoldings .home-company').count()
    page.locator('#homeSectors button').first.click()
    expect(page.locator('#discoveryFilters [name=industry]')).not_to_have_value('')
    page.locator('[data-page=home]').click()
    page.screenshot(path=str(ROOT/'validation/dashboard-home-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    for view in options:
        page.locator('#pageSelect').select_option(view)
        expect(page.locator('body')).to_have_attribute('data-current-page',view)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),view
        assert page.locator('#pageSelect').bounding_box()['height']>=44
        assert page.locator('#contextNavigation button:visible').evaluate_all('(els)=>els.every(el=>el.getBoundingClientRect().height>=44)')
    page.locator('#pageSelect').select_option('home')
    page.screenshot(path=str(ROOT/'validation/dashboard-home-mobile.png'),full_page=True)
    assert not errors,errors
    assert not network,network
    browser.close()
print(f'PASS menu minimum contrast={min(contrast):.2f}, keyboard/labels/44px targets; dashboard home, seven primary/three extra menus, comparison with secondary charts, search/watch/detail/trend/sector/holdings flows, 23 mobile views, no network/JS errors')
