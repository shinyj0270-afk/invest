// Synthetic import flow through the rebuilt HTML. Uses local installed Edge.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '..');
(async()=>{
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'investment-import-'));
 let browser;
 try {
  execFileSync(process.env.PYTHON||'python',['tools/infomax_demo.py','--output-dir',path.join(tmp,'demo')],{cwd:root});
  const snapshot=JSON.parse(fs.readFileSync(path.join(tmp,'demo','snapshot.json'),'utf8'));
  browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.setContent(fs.readFileSync(path.join(root,'INVESTMENT_Dashboard.html'),'utf8'));
  const upload=async data=>{await page.locator('#dataInput').setInputFiles({name:'fixture.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(data))});};
  await upload(snapshot);
  await page.waitForFunction(()=>document.getElementById('importCount').textContent==='3개 종목');
  assert.match(await page.locator('#dataBadge').innerText(),/가상 테스트/);
  await page.getByRole('tab',{name:'02 기업분석'}).click();
  assert.match(await page.locator('#profitMetrics').innerText(),/10 %/);
  assert.match(await page.locator('#flowMetrics').innerText(),/0.2 억원/);
  assert.match(await page.locator('#companySources').innerText(),/지배주주/);
  if(process.env.VALIDATION_SCREENSHOT)await page.screenshot({path:process.env.VALIDATION_SCREENSHOT,fullPage:true});
  assert.match(await page.locator('#profitMetrics span').filter({hasText:'ROE'}).getAttribute('title'),/TTM/);
  console.log('PASS CSV 변환 → JSON 가져오기 → 지표·결측 사유 표시');
  const invalid=structuredClone(snapshot);invalid.companies[0].metrics.roe_pct='bad';
  await upload(invalid);
  await page.waitForFunction(()=>document.getElementById('toast').textContent.includes('불러오기 실패'));
  assert.match(await page.locator('#profitMetrics').innerText(),/10 %/);
  console.log('PASS 잘못된 입력 후 마지막 정상 자료 유지');
  const hostile=structuredClone(snapshot);hostile.companies[0].data_quality=['<img src=x onerror="window.attacked=true">'];
  await upload(hostile);
  await page.getByRole('tab',{name:'02 기업분석'}).click();
  assert.equal(await page.locator('#companySources img').count(),0);
  assert.equal(await page.evaluate(()=>window.attacked),undefined);
  assert.match(await page.locator('#companySources').innerText(),/<img/);
  console.log('PASS 결측 설명의 HTML 주입 방어');
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.locator('#dataBadge').isVisible(),true);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),true);
  assert.deepEqual(errors,[]);
  console.log('PASS 모바일 폭 및 브라우저 오류 검사');
 } finally {
  if(browser)await browser.close();
  assert.equal(path.dirname(path.resolve(tmp)),path.resolve(os.tmpdir()));
  assert.match(path.basename(tmp),/^investment-import-/);
  fs.rmSync(tmp,{recursive:true,force:true});
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
