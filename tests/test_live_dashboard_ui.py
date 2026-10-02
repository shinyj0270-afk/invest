"""Browser: live refresh updates data and restores per-tab holdings."""
import os
import sys
import threading
from http.server import HTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

def open_tools(page):
    if page.locator('#moreNavigation').get_attribute('open') is None:
        page.locator('#moreNavigation summary').click()


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from investment.fixture import make_fixture
from investment.live_dashboard import handler_for

first = make_fixture()
first['meta']['data_mode'] = 'user_input'
second = make_fixture()
second['meta']['data_mode'] = 'user_input'
second['companies'][0]['metrics']['roe_pct'] = 72
third = make_fixture()
third['meta']['data_mode'] = 'user_input'
third['companies'][0]['metrics']['roe_pct'] = 72
third['companies'][0]['name'] = '새 저장자료 기업'
calls = []


def refresh(root, *, force=False):
    calls.append(force)
    refreshes = calls.count(True)
    current = first if refreshes == 0 else second if refreshes == 1 else third
    return dict(snapshot=current, receipt=dict(status='complete' if force else 'cached',
        success=True, checked_at='2026-09-30T10:00:00+09:00',
        data_as_of=current['meta']['price_date'], target_date=current['meta']['price_date'],
        stale=False, updated_companies=int(force), price_records=0,
        failed_companies=0, fallback=False, error=None))


server = HTTPServer(('127.0.0.1', 0), handler_for(ROOT, refresh=refresh, token='browser-test-token'))
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=os.environ.get(
            'CHROMIUM_PATH', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
        page = browser.new_page(viewport={'width': 1440, 'height': 900})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(f'http://127.0.0.1:{server.server_port}/')
        expect(page.locator('#refreshData')).to_be_visible()
        expect(page.locator('#overviewTable')).to_contain_text('가상 연구기업 1')
        page.locator('[data-page=holdings]').click()
        frame = page.frame_locator('#detailFrame')
        frame.locator('#pCode').fill('900000')
        frame.locator('#pQty').fill('2')
        frame.locator('#pCost').fill('10000')
        frame.locator('#pSaveHolding').click()
        expect(frame.locator('#pHoldBody')).to_contain_text('가상 연구기업 1')
        open_tools(page);page.locator('[data-page=scatter]').click()
        with page.expect_navigation(wait_until='load', timeout=30000):
            page.locator('#refreshData').click()
        expect(page.locator('#sourceNotice')).to_contain_text('갱신 cached')
        page.wait_for_load_state('load')
        assert not errors, errors
        expect(page.locator('#focusMetrics')).to_contain_text('72 %', timeout=30000)
        assert '종목 식별이 바뀌어' not in page.locator('#sourceNotice').inner_text()
        page.locator('[data-page=holdings]').click()
        expect(frame.locator('#pHoldBody')).to_contain_text('2')
        with page.expect_navigation(wait_until='load', timeout=30000):
            page.locator('#refreshData').click()
        expect(page.locator('#sourceNotice')).to_contain_text('갱신 cached')
        open_tools(page);page.locator('[data-page=scatter]').click()
        expect(page.locator('#focusCompany')).to_contain_text('새 저장자료 기업')
        expect(page.locator('#sourceNotice')).to_contain_text('종목 식별이 바뀌어')
        assert page.evaluate("sessionStorage.getItem('investment-live-refresh-handoff')") is None
        page.locator('[data-page=holdings]').click()
        expect(frame.locator('#pHoldBody')).to_contain_text('가상 연구기업 1')
        expect(frame.locator('#pHoldBody')).to_contain_text('2')
        # Recommendation GETs also read saved data. Only explicit refreshes force it.
        assert calls[0] is False and calls.count(True)==2, calls
        forced=[i for i,value in enumerate(calls) if value]
        assert all(any(not value for value in calls[i+1:j]) for i,j in zip(forced,forced[1:]+[len(calls)])), calls
        assert not errors, errors
        browser.close()
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)
print('PASS live dashboard: startup check, force refresh, new data, holdings restored, no JS errors')
