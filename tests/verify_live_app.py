"""UI-only checks against the locally running app. No external provider calls."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
    page=browser.new_page(viewport={'width':1500,'height':1000}); errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8501'); page.get_by_role('heading',name='INVESTMENT · 기업 탐색과 연구').wait_for()
    page.get_by_role('combobox',name='데이터 모드').click(); page.get_by_role('option',name='가상 테스트',exact=True).click()
    page.get_by_text('가상 테스트 · 실제 기업/시장 관측 아님',exact=False).wait_for()
    for title in ['기업분석','산업비교','A4 One-Pager','장기성장 연구','추세 연구','기존 보유·포트폴리오','데이터 상태','조건검색']:
        page.get_by_role('tab',name=title,exact=True).click()
    page.get_by_role('button',name='조건 저장',exact=True).click()
    page.get_by_text('조건 저장 완료 · 재실행 후 복원',exact=True).wait_for()
    with page.expect_download() as dl: page.get_by_role('button',name='조건 JSON 내보내기',exact=True).click()
    assert dl.value.suggested_filename=='screen_conditions.json'
    with page.expect_download() as dl: page.get_by_role('button',name='결과 CSV 내보내기',exact=True).click()
    assert dl.value.suggested_filename=='screen_results.csv'
    page.get_by_role('tab',name='A4 One-Pager',exact=True).click()
    with page.expect_download() as dl: page.get_by_role('button',name='인쇄용 HTML 다운로드',exact=True).click()
    assert dl.value.suggested_filename.endswith('_onepager.html')
    page.get_by_role('heading',name='INVESTMENT · 기업 탐색과 연구').scroll_into_view_if_needed()
    page.screenshot(path=str(ROOT/'validation/current/app-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    page.screenshot(path=str(ROOT/'validation/current/app-mobile.png'),full_page=True)
    assert not errors,errors
    browser.close()
print('PASS live Streamlit: 8 tabs, fixture selection, condition save, JSON/CSV/HTML exports, mobile width, no page errors')
