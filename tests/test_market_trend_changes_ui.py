"""Focused synthetic browser harness for shared explanations and manual watch checkpoints."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from tools.browser_runtime import chromium_options
from investment.trend_following import build_trend_following
from investment.workspace_research import build_research
from tests.test_trend_following import trend_fixture

s=trend_fixture();data=build_trend_following(s,build_research(s))
styles='body{font-family:Arial;margin:12px}*{box-sizing:border-box}.panel{border:1px solid #ddd;border-radius:10px}.panel-heading{display:flex;justify-content:space-between}.psub{font-size:12px}button,input,select{font:inherit;padding:8px;max-width:100%}'
styles+=''.join((ROOT/'src'/f).read_text(encoding='utf-8') for f in ('trend_following.css','market_explanation.css'))
scripts=''.join((ROOT/'src'/f).read_text(encoding='utf-8') for f in ('market_explanation_ui.js','trend_changes_ui.js','trend_following_ui.js'))
html='<html lang="ko"><meta charset="utf-8"><style>'+styles+'</style><main id="board"></main><script>'+scripts+'</script><script>const TrendChartUI={mount:()=>({destroy(){}})};const boardData='+json.dumps(data,ensure_ascii=False)+';const app=TrendFollowingUI.create({element:document.getElementById("board"),data:boardData});app.render();</script></html>'
errors=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,**chromium_options())
    page=browser.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
    page.route('http://127.0.0.1:9876/**',lambda route:route.fulfill(status=200,content_type='text/html',body=html))
    page.goto('http://127.0.0.1:9876/',wait_until='load')
    expect(page.locator('.market-explanation')).to_be_visible()
    expect(page.locator('.me-card')).to_have_count(2)
    expect(page.locator('.tf-changes')).to_contain_text('이전 체크포인트 없음')
    expect(page.locator('.tf-changes')).to_contain_text('신규/이탈 판정 대기')
    expect(page.locator('.tf-stock')).to_have_count(6)
    page.locator('[data-tf-watch]').first.click()
    expect(page.locator('.tf-watch h3')).to_contain_text('1개')
    page.locator('#tfWatchCheckpoint').click()
    expect(page.locator('.tf-watch')).to_contain_text('수정본 1')
    page.locator('#tfWatchCheckpoint').click()
    expect(page.locator('.tf-watch summary')).to_contain_text('1회')
    before=page.locator('.tf-changes').inner_text()
    page.locator('#tfFilters [name=capMin]').fill('9000')
    page.locator('#tfFilters button:not([type])').click()
    expect(page.locator('.tf-watch h3')).to_contain_text('1개')
    assert page.locator('.tf-changes').inner_text()==before
    page.reload()
    expect(page.locator('.tf-watch')).to_contain_text('수정본 1')
    expect(page.locator('#tfFilters [name=capMin]')).to_have_value('9000')
    page.locator('#tfReset').click()
    for width in (390,320):
        page.set_viewport_size({'width':width,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
    page.locator('[data-tfw-remove]').click()
    expect(page.locator('.tf-watch h3')).to_contain_text('0개')
    expect(page.locator('.tf-watch summary')).to_contain_text('1회')
    assert not errors,errors
    browser.close()
print('PASS synthetic UI shared 3 axes, no fabricated prior, six charts, explicit watch checkpoint/reload, filter-independent history, 390/320px, zero JS errors')
