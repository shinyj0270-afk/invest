"""Recovery chooses exactly one target, polls completion and keeps drafts untouched."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
state={'failures':[dict(kind='price',code='005930',name='Example',status='failed',stage='calendar',reason='incomplete',can_retry=True)],'price_job':{'status':'idle'}}
calls=[]
html='<meta charset="utf-8"><input id="draft" value="unsaved"><div id="recovery"></div><script>'+ (ROOT/'src/data_recovery_ui.js').read_text(encoding='utf-8')+'</script><script>InvestmentDataRecovery.create(document.getElementById("recovery"),{token:"test"}).render()</script>'
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
    page=browser.new_page(viewport={'width':390,'height':844});errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    def route(request):
        if request.request.url.endswith('/data-recovery'):
            assert request.request.headers.get('x-dashboard-token')=='test'
            if request.request.method=='POST':
                calls.append(request.request.post_data_json)
                state['failures']=[];state['price_job']={'status':'complete'}
                request.fulfill(json={'status':'running'})
            else:request.fulfill(json=state)
        else:request.fulfill(body=html,content_type='text/html')
    page.route('http://127.0.0.1:9999/**',route)
    page.goto('http://127.0.0.1:9999/')
    expect(page.locator('#recovery summary').first).to_contain_text('1')
    page.locator('#recovery summary').first.click()
    page.locator('[data-recovery-code="005930"]').click()
    expect(page.locator('#recovery summary').first).to_contain_text('실패 0',timeout=7000)
    assert calls==[dict(kind='price',code='005930')]
    expect(page.locator('#draft')).to_have_value('unsaved')
    assert page.locator('#recovery details').first.evaluate('(e)=>e.open')
    state['failures']=[dict(kind='financial',code='005930',name='Example',status='partial',reason='unavailable',can_retry=False)]
    page.reload();page.locator('#recovery summary').first.click()
    page.locator('#recovery details details summary').click()
    expect(page.locator('[data-recovery-code]')).to_be_disabled()
    expect(page.locator('#recovery')).to_contain_text('입력을 보관한 뒤 화면 새로고침')
    page.evaluate('window.recoveryTest=InvestmentDataRecovery.create(document.getElementById("recovery"),{token:"test"}); recoveryTest.render()')
    expect(page.locator('#recovery details details')).to_have_attribute('open','')
    assert not errors,errors
    browser.close()
print('PASS targeted recovery, completion, readonly and unsaved draft preservation')
