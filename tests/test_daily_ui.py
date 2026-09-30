"""Local Streamlit UI checks. Uploads explicitly synthetic holdings into one session."""
import json
import os
from pathlib import Path
import sys

from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from investment.holdings_bridge import holdings_input
from tests import test_infomax_daily

helper=test_infomax_daily.DailyImportTests();helper.setUp()
holdings=holdings_input(helper.convert())
row=holdings['research'][0]
row['name']='합성 UI 검증종목'
row['price_date']=holdings['as_of']
holdings['cash_krw']=1000
holdings['holdings']=[dict(code=row['code'],quantity=2,avg_cost_krw=50)]

with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
    page=browser.new_page(viewport={'width':1440,'height':1100})
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(os.environ.get('INVESTMENT_TEST_URL','http://127.0.0.1:8501'))
    expect(page.get_by_role('radio',name='오늘',exact=True)).to_be_checked()
    expect(page.get_by_test_id('stMetric').filter(has_text='보유 검토 대기')).to_contain_text('미입력')
    page.get_by_text('보유·연구 입력과 구성 설정',exact=True).click()
    uploader=page.get_by_test_id('stFileUploader').filter(has_text='일일 요약용 보유·연구 JSON').locator('input[type=file]')
    uploader.set_input_files(dict(name='synthetic_holdings.json',mimeType='application/json',buffer=json.dumps(holdings).encode()))
    expect(page.get_by_text('선택 파일: synthetic_holdings.json',exact=True)).to_be_visible()
    page.get_by_role('button',name='일일 요약에 입력 적용',exact=True).click()
    expect(page.get_by_test_id('stMetric').filter(has_text='보유 검토 대기')).to_contain_text('1 / 1')
    expect(page.get_by_test_id('stMetric').filter(has_text='입력 보유 평가액 + 현금')).to_contain_text('1,200원')
    waterfall=page.get_by_test_id('stExpander').filter(has_text='보유 평가액을 만든 손익 · 워터폴')
    expect(waterfall.locator('svg.marks')).to_be_visible()
    expect(waterfall.locator('path[role="graphics-symbol"]')).to_have_count(3)
    # Invalid upload must not discard the previous valid holdings.
    uploader.set_input_files(dict(name='invalid.json',mimeType='application/json',buffer=b'null'))
    expect(page.get_by_text('선택 파일: invalid.json',exact=True)).to_be_visible()
    page.get_by_role('button',name='일일 요약에 입력 적용',exact=True).click()
    expect(page.get_by_text('입력 검증 실패 · 기존 입력 유지',exact=False)).to_be_visible()
    expect(page.get_by_test_id('stMetric').filter(has_text='보유 검토 대기')).to_contain_text('1 / 1')
    page.get_by_role('spinbutton',name='최대 기업 수',exact=True).fill('3')
    page.get_by_role('spinbutton',name='가정 시나리오 손실 기준 (%)',exact=True).fill('20')
    page.get_by_text('이 설정과 가정의 한계를 확인했습니다',exact=True).click()
    page.get_by_role('button',name='구성 설정 적용',exact=True).click()
    expect(page.get_by_text('자료 보완 필요',exact=True)).to_be_visible()
    page.get_by_test_id('stSidebar').get_by_text('보유·포트폴리오',exact=True).click()
    frame=page.frame_locator('iframe').last
    expect(frame.locator('#pHoldBody')).to_contain_text('합성 UI 검증종목')
    expect(frame.locator('#pValue')).to_contain_text('1,200')
    expect(frame.locator('#pMax')).to_have_value('3')
    expect(frame.locator('#pConfirm')).to_be_checked()
    page.get_by_test_id('stSidebar').get_by_text('오늘',exact=True).click()
    page.get_by_text('보유·연구 입력과 구성 설정',exact=True).click()
    expect(page.get_by_test_id('stMetric').filter(has_text='보유 검토 대기')).to_contain_text('1 / 1')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    # Fresh mobile page starts with the sidebar collapsed; controls remain reachable.
    mobile=browser.new_page(viewport={'width':390,'height':844})
    mobile.goto(os.environ.get('INVESTMENT_TEST_URL','http://127.0.0.1:8501'))
    expect(mobile.get_by_role('heading',name='오늘의 투자 점검')).to_be_visible()
    expect(mobile.get_by_test_id('stMetric').filter(has_text='보유 검토 대기')).to_contain_text('미입력')
    assert mobile.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    assert not errors,errors
    browser.close()
print('PASS daily UI: empty/valid/invalid input, session isolation, policy + detail consistency, mobile width, no JS errors')
