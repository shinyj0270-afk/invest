const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');
const DATA=path.resolve(__dirname,'../private_data/infomax');
(async()=>{
 const expected=JSON.parse(fs.readFileSync(path.join(DATA,'snapshot-review.json'),'utf8'));
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(pathToFileURL(path.join(DATA,'INVESTMENT_실데이터_검토.html')).href);
  assert.equal(await page.locator('#importCount').innerText(),'3개 종목');
  assert.doesNotMatch(await page.locator('#dataBadge').innerText(),/가상/);
  for(const row of expected.companies){
   await page.locator('#companySelect').selectOption(row.code);
   assert.equal(await page.locator('#companyTitle').innerText(),row.name);
   assert.match(await page.locator('#profitMetrics').innerText(),new RegExp(row.metrics.operating_margin_pct.toFixed(1).replace('.','\\.')));
   assert.match(await page.locator('#companySources').innerText(),/공식 실적 발표/);
   const caps={'005930':1674958821192000,'000660':1360907275995000,'005380':72637537644000};
   assert.equal(row.metrics.market_cap_eok,caps[row.code]/1e8);
   assert.equal(row.market_cap_evidence.date,'2026-09-23');
   assert.equal(row.market_cap_evidence.revision_finality_confirmed,false);
   assert.ok(Number.isFinite(row.metrics.foreign_net_20d_eok));
   for(const prefix of ['foreign','institution']){
    assert.ok(Math.abs(row.metrics[prefix+'_net_turnover_20d_pct']-row.metrics[prefix+'_net_20d_eok']/(row.metrics.avg_trading_value_20d_eok*20)*100)<1e-10);
   }
   assert.equal(Object.values(row.metrics).filter(v=>v!==null).length,13);
   assert.equal(row.user_policy_evidence.venue_comparability_confirmed,false);
   assert.match(await page.locator('body').innerText(),/거래소 범위 동일성 미확인/);
   assert.match(await page.locator('#flowMetrics').innerText(),new RegExp(String(Number(row.metrics.foreign_net_turnover_20d_pct.toFixed(1))).replace('.','\\.')));
   assert.equal(row.user_policy_evidence.official_calendar_verified,false);
   assert.equal(row.user_policy_evidence.price_venue,null);
   assert.equal(row.user_policy_evidence.flows_final,false);
   assert.match(await page.locator('body').innerText(),/공식 거래일 미대조/);
   assert.match(await page.locator('body').innerText(),/추후 정정 가능/);
   const finance=row.additional_financial_evidence;
   assert.equal(finance.status,'user_policy_infomax_priority');
   assert.ok(Object.values(finance.differences_million_krw).every(v=>v===0));
   for(const key of ['roe_pct','interest_coverage_x','net_debt_equity_pct']){
    assert.equal(row.metrics[key],finance.metrics[key]);
    assert.equal(row.metric_missing_reasons[key],undefined);
   }
   assert.match(await page.locator('#profitMetrics').innerText(),new RegExp(String(Number(row.metrics.roe_pct.toFixed(1))).replace('.','\\.')));
   assert.match(await page.locator('#stabilityMetrics').innerText(),new RegExp(String(Number(row.metrics.interest_coverage_x.toFixed(1))).replace('.','\\.')));
   if(row.code==='005930'){
    assert.ok(Math.abs(row.metrics.debt_ratio_pct-180170840/579309676*100)<1e-10);
    assert.ok(Math.abs(row.metrics.current_ratio_pct-379711982/134189617*100)<1e-10);
    assert.ok(Math.abs(row.metrics.revenue_growth_pct-(171499470/74566317-1)*100)<1e-10);
    assert.match(await page.locator('#profitMetrics').innerText(),/130/);
   }else if(row.code==='005380'){
    assert.equal(finance.total_debt_million_krw,190751957);
    assert.equal(finance.supplier_bonds_minus_official_noncurrent_million_krw,333195);
    assert.ok(Math.abs(row.metrics.net_debt_equity_pct-(190751957-20256150)/135416445*100)<1e-10);
    assert.ok(Math.abs(row.metrics.debt_ratio_pct-259095722/135416445*100)<1e-10);
    assert.ok(Math.abs(row.metrics.current_ratio_pct-129045681/97136454*100)<1e-10);
    assert.ok(Math.abs(row.metrics.revenue_growth_pct-(49215328/48286677-1)*100)<1e-10);
   }else{
    assert.ok(Math.abs(row.metrics.debt_ratio_pct-86168986/262693228*100)<1e-10);
    assert.equal(row.metric_missing_reasons.debt_ratio_pct,undefined);
    assert.equal(row.statement_evidence.balance_match,'within_user_tolerance');
    assert.ok(Math.abs(row.metrics.current_ratio_pct-156155954/60257051*100)<1e-10);
    assert.ok(Math.abs(row.metrics.revenue_growth_pct-(79318746/22231952-1)*100)<1e-10);
   }
  }
  await page.locator('#companySelect').selectOption('005930');
  await page.screenshot({path:path.join(DATA,'dashboard-preview.png'),fullPage:true});
  await page.reload();
  assert.equal(await page.locator('#importCount').innerText(),'3개 종목');
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(DATA,'browser-validation.txt'),'PASS: 3 real companies, 39 metric values, Infomax priority with retained bond discrepancy, provisional flow ratios and warning labels, reload, mobile width, no JS errors\n');
  console.log('PASS actual-file dashboard integration');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
