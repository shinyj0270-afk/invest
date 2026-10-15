"""Offline fixture checks: home verdict top alignment, CSV beside status, no frame sandbox warning."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace
from playwright.sync_api import sync_playwright,expect
from tools.browser_runtime import chromium_options

snapshot=make_fixture()
for bars in snapshot['benchmarks'].values():
    for b in bars:b['final']=True
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,**chromium_options())
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];warnings=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('console',lambda m:'sandbox' in m.text and warnings.append(m.text))
    page.set_content(export_workspace(snapshot),wait_until='load')
    expect(page.locator('#home')).to_be_visible()
    # The verdict starts at the top of its card instead of floating in the middle.
    verdict=page.locator('.home-verdict')
    gap=verdict.evaluate("el=>el.firstElementChild.getBoundingClientRect().top-el.getBoundingClientRect().top-parseFloat(getComputedStyle(el).paddingTop)")
    assert gap<=4,gap
    # On desktop the CSV action shares the status summary row instead of adding its own row.
    page.locator('[data-page=finder]').click()
    expect(page.locator('#exportCsv')).to_be_visible()
    for width in (1640,1440,1024,901):
        page.set_viewport_size({'width':width,'height':1000})
        csv=page.locator('#exportCsv').bounding_box();summary=page.locator('#workspaceStatus>summary').bounding_box()
        assert csv['y']<summary['y']+summary['height'] and summary['y']<csv['y']+csv['height'],(width,csv,summary)
        assert csv['x']>summary['x']+summary['width'],(width,csv,summary)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth'),width
    page.locator('#workspaceStatus>summary').click();expect(page.locator('#viewFreshness')).to_be_visible()
    status=page.locator('.workspace-status-content').bounding_box();csv=page.locator('#exportCsv').bounding_box()
    assert status['y']>=csv['y']+csv['height']-1,(status,csv)
    page.locator('#workspaceStatus>summary').click()
    # Mobile keeps the screen selector and CSV in the sticky bar.
    page.set_viewport_size({'width':390,'height':844})
    expect(page.locator('#pageSelect')).to_be_visible();expect(page.locator('#exportCsv')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.locator('#pageSelect').select_option('holdings');page.wait_for_timeout(500)
    assert page.locator('#detailFrame').get_attribute('sandbox') is None
    assert not warnings,warnings
    assert not errors,errors
    browser.close()
print('PASS home verdict top-aligned, CSV on status row at four desktop widths, mobile bar kept, no iframe sandbox warning')
