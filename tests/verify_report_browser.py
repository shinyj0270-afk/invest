"""Browser and A4 checks for authored HTML; fixtures and saved actuals separate."""
import json
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright
from pypdf import PdfReader
import pymupdf
from investment.fixture import make_fixture
from investment.research import analyze
from investment.report import onepager
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'validation/current'; OUT.mkdir(exist_ok=True)
sources=[('fixture',make_fixture())]
actual=ROOT/'private_data/infomax/snapshot-review.json'
if actual.exists():
    s=json.loads(actual.read_text(encoding='utf-8'))
    for i,row in enumerate(s['companies']):
        reordered=dict(s,companies=[row]+[r for r in s['companies'] if r['code']!=row['code']])
        sources.append(('saved_actual' if i==0 else 'saved_actual_'+row['code'],reordered))
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
    page=browser.new_page(viewport={'width':1000,'height':1123})
    for label,s in sources:
        row=s['companies'][0]; info=next(r for r in analyze(s) if r['code']==row['code'])
        html=onepager(s,row,info); (OUT/(label+'_onepager.html')).write_text(html,encoding='utf-8')
        page.set_content(html); page.emulate_media(media='print')
        assert page.locator('body').evaluate('(el)=>el.scrollWidth<=innerWidth')
        pdf=OUT/(label+'_onepager.pdf'); page.pdf(path=str(pdf),prefer_css_page_size=True,print_background=True)
        doc=PdfReader(pdf); assert len(doc.pages)==1,(label,len(doc.pages))
        text=doc.pages[0].extract_text(); assert row['name'] in text and '관측' in text and '\ufffd' not in text
        assert abs(float(doc.pages[0].mediabox.width)-595.28)<1
        with pymupdf.open(pdf) as rendered:
            rendered[0].get_pixmap(matrix=pymupdf.Matrix(1.4,1.4)).save(OUT/(label+'_pdf_render.png'))
            blocks=rendered[0].get_text('blocks')
            assert all(b[0]>=30 and b[1]>=30 and b[2]<=565 and b[3]<=810 for b in blocks),'PDF text outside A4 content bounds'
        page.screenshot(path=str(OUT/(label+'_onepager.png')),full_page=True)
        print('PASS',label,'A4 1 page, Korean extraction, source name, width')
    browser.close()
