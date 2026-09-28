"""Synthetic test records only; not real companies or market observations."""
import json
import os
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT = Path(__file__).resolve().parents[1]
meta = dict(price_date='2025-12-30', flow_start='2025-12-01', flow_end='2025-12-30',
            financial_period='FY2025', financial_basis='CFS', venue='KRX', universe_label='TEST ONLY')
rows = []
for code, name, op, debt, foreign in [('000001','가_테스트전용',10,50,5),('000002','나_테스트전용',5,150,-5),('000003','다_테스트전용',None,50,5)]:
    rows.append(dict(code=code,name=name,market='KOSPI',industry='테스트산업',security_type='ordinary',analysis_profile='nonfinancial',metrics=dict(operating_margin_pct=op,debt_ratio_pct=debt,foreign_net_20d_eok=foreign,avg_trading_value_20d_eok=30,current_ratio_pct=150,foreign_net_turnover_20d_pct=foreign),history=[dict(year=2023,revenue_eok=100,operating_profit_eok=8),dict(year=2025,revenue_eok=120,operating_profit_eok=12)],sources=[]))
rows.append(dict(rows[0],code='000004',name='금융_테스트전용',analysis_profile='financial'))
fixture=dict(schema_version='0.1',meta=meta,companies=rows)
results=[]
def check(name, ok):
    if not ok: raise AssertionError(name)
    results.append('PASS '+name)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium') or shutil.which('chromium-browser'),args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1000})
    page.set_default_timeout(5000)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.set_content((ROOT/'INVESTMENT_Dashboard.html').read_text(encoding='utf-8'),wait_until='load')
    check('빈 화면은 실제 회사 수를 주장하지 않음',page.locator('#universeStat').inner_text()=='—')
    page.locator('#dataInput').set_input_files({'name':'test-only.json','mimeType':'application/json','buffer':json.dumps(fixture).encode()})
    page.wait_for_timeout(150)
    page.get_by_role('button',name='입력 예시 적용').click()
    check('비금융 보통주 3개를 대상으로 계산',page.locator('#universeStat').inner_text()=='3')
    check('AND 조건 통과 1개',page.locator('#matchStat').inner_text()=='1')
    check('AND 조건 자료 부족 1개',page.locator('#unknownStat').inner_text()=='1')
    page.locator('[data-compare="000001"]').check()
    page.locator('[data-compare="000002"]').check()
    page.locator('#resultStatus').select_option('pass')
    check('조건 충족 필터는 결과 1개만 표시',page.locator('#resultBody tr').count()==1)
    page.get_by_role('tab',name='03 산업비교').click()
    check('비교 산업 모집단은 검색 필터와 독립', '동종업계 3개' in page.locator('#peerScope').inner_text())
    first=page.locator('#compareBody tr').first.inner_text()
    check('업종 중앙값과 유효 표본 계산','7.5' in first and '2 / 3' in first)
    page.get_by_role('tab',name='02 기업분석').click()
    check('규칙형 회사 요약 생성','10 %' in page.locator('#companySummary').inner_text())
    check('연도 공백은 차트에서 선 연결하지 않음',page.locator('#historyChart path').get_attribute('d').count('M')==2)
    page.get_by_role('tab',name='01 조건검색').click()
    with page.expect_download() as dl:
        page.locator('#exportConfig').click()
    check('조건 JSON 내보내기',dl.value.suggested_filename=='screen_conditions.json')
    with page.expect_download() as dl:
        page.locator('#exportResults').click()
    check('검색 결과 CSV 내보내기',dl.value.suggested_filename=='screen_results.csv')
    invalid=dict(fixture,companies=[rows[0],rows[0]])
    page.locator('#dataInput').set_input_files({'name':'invalid.json','mimeType':'application/json','buffer':json.dumps(invalid).encode()})
    page.wait_for_timeout(150)
    check('중복 데이터 파일 차단 및 기존 상태 보존','불러오기 실패' in page.locator('#toast').inner_text() and page.locator('#universeStat').inner_text()=='3')
    check('렌더링·클릭에서 JS 런타임 오류 없음',not errors)
    browser.close()
print('\n'.join(results))
print(f'{len(results)} UI checks passed.')
