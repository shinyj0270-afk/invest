const assert=require('node:assert/strict'),E=require('../src/company_detail_engine');
const qs=['2023-03-31','2023-06-30','2023-09-30','2023-12-31','2024-03-31'].map((d,i)=>({period_end:d,available_at:['2023-05-15','2023-08-14','2023-11-14','2024-03-15','2024-05-15'][i],source:'DART',values:{revenue:100,operating_profit:10,net_income:8,parent_net:6,parent_equity:120,equity:150,assets:200,liabilities:50,ocf:20,capex_ppe:-5,capex_intangibles:-2,cash_start:40+i,cash_end:41+i,eps:3}}));
const model={groups:[{basis:'CFS',cadence:'quarter',columns:qs}],chart:{as_of:'2024-06-01',bars:[{date:'2024-03-14',close:100},{date:'2024-03-15',close:100},{date:'2024-05-15',close:120},{date:'2024-06-01',close:120}]}};
const row={code:'x',metrics:{market_cap_eok:120},latest_quote:{market_cap_eok:120,price:120,retrieved_at:'2024-06-01T10:00:00+09:00'}},v=E.valuation(row,model);
assert.equal(v.history[0].per,null);assert.equal(v.history[1].period,'2023-12-31');assert.equal(v.history[2].period,'2024-03-31');assert.equal(v.current.per,5);assert.equal(v.current.pbr,1);
const ttm=E.periods(model,'CFS','ttm')[0].values;assert.equal(ttm.ocf,80);assert.equal(ttm.fcf,52);assert.equal(ttm.cash_start,40);assert.equal(ttm.cash_end,44);assert.equal(ttm.eps,null);
const missing=structuredClone(model);missing.groups[0].columns[1].values.ocf=null;assert.equal(E.periods(missing,'CFS','ttm')[0].values.ocf,null);assert.equal(E.valuation(row,missing).history[1].pcr,null);
const loss=structuredClone(model);loss.groups[0].columns.forEach(c=>c.values.parent_net=-2);assert.equal(E.valuation(row,loss).current.per,null);
const dist=E.distribution(Array.from({length:30},(_,i)=>({per:i+1})),'per',15);assert.equal(dist.percentile,50);assert.equal(dist.histogram.reduce((s,b)=>s+b.count,0),30);
const flat=E.distribution(Array.from({length:30},()=>({per:2})),'per',2);assert.equal(flat.histogram.reduce((s,b)=>s+b.count,0),30);assert.equal(E.distribution([{per:-1}],'per',1),null);
assert.equal(E.rim(100,10,.1).scenarios[0].value,100);assert.equal(E.rim(100,10,0),null);assert.equal(E.rim(null,10,.1),null);
const factors=E.decomposition(100,130,10,15);assert.equal(factors.start+factors.profit+factors.multiple,factors.end);assert.equal(factors.profit,50);assert.equal(factors.multiple,-20);assert.equal(E.decomposition(100,130,-10,15),null);
const summary=E.summary(row,model,{rows:{}},{financial_basis:'CFS',price_date:'2024-06-01'});assert.equal(summary.length,11);assert.equal(summary.find(x=>x[0]==='growth')[2],0);assert.equal(summary.find(x=>x[0]==='roe')[2],20);
console.log('PASS valuation: submission dates, missing/loss exclusions, cash/TTM accounting, 11 common metrics, histogram/RIM/factor reconciliation');

// The quote price, not a differently dated completed close, establishes estimated shares.
const splitQuote={metrics:{market_cap_eok:10000},latest_quote:{price:200,market_cap_eok:10000,retrieved_at:'2026-10-08T09:00:00+09:00'}};
const columns=['2025-06-30','2025-09-30','2025-12-31','2026-03-31','2026-06-30'].map(period_end=>({period_end,available_at:period_end,source:'synthetic',values:{parent_net:100,parent_equity:1000,net_income:100,equity:1000,ocf:100}}));
const quotedModel={groups:[{basis:'CFS',cadence:'quarter',columns}],chart:{as_of:'2026-10-07',bars:Array.from({length:25},(_,i)=>({date:'2026-09-'+String(i+1).padStart(2,'0'),close:100})).concat({date:'2026-10-07',close:100})},common_financial:{basis:'CFS',currency:'KRW',period:'2026-06-30',metrics:{per:12.5,pbr:5}}};
const aligned=E.valuation(splitQuote,quotedModel);
assert.equal(aligned.current.shares,5e9);assert.equal(aligned.current.date,'2026-10-07');assert.equal(aligned.current.shares_date,'2026-10-08');
for(const key of ['per','pbr','pcr','eps','bps','cps'])assert.equal(aligned.current[key],aligned.history.at(-1)[key]);
assert.equal(aligned.current.pcr,12.5);assert.equal(aligned.current.eps,8);assert.equal(aligned.current.bps,20);assert.equal(aligned.current.cps,8);
assert.equal(E.distribution(aligned.history,'per',aligned.current.per).percentile,100);
for(const retrieved_at of ['2026-10-07T09:00:00+09:00','2026-10-10T09:00:00+09:00'])assert.equal(E.valuation({...splitQuote,latest_quote:{...splitQuote.latest_quote,retrieved_at}},quotedModel).current.shares,5e9);
const late=structuredClone(quotedModel);late.groups[0].columns.at(-1).available_at='2026-10-08';late.groups[0].columns.at(-1).values.parent_net=200;late.common_financial.metrics.per=10;
const observed=E.valuation(splitQuote,late);assert.equal(observed.current.period,'2026-06-30');assert.equal(observed.current.eps,10);assert.equal(observed.current.per,10);assert.equal(observed.history.at(-1).eps,8);assert.equal(observed.history.at(-1).per,12.5);
const unknown=structuredClone(quotedModel);unknown.groups[0].columns.forEach(c=>c.available_at=null);
const currentOnly=E.valuation(splitQuote,unknown);assert.equal(currentOnly.current.eps,8);assert.equal(currentOnly.current.bps,20);assert.equal(currentOnly.current.cps,8);assert.equal(currentOnly.history.at(-1).per,null);
const reviewed=structuredClone(quotedModel);reviewed.common_financial.metrics={per:10,pbr:4};reviewed.common_financial.metric_details={per:{status:'reviewed'},pbr:{status:'reviewed'}};
const preserved=E.valuation(splitQuote,reviewed);assert.equal(preserved.current.per,10);assert.equal(preserved.current.pbr,4);assert.equal(preserved.current.eps,8);assert.equal(preserved.current.bps,20);
for(const quote of [{}, {...splitQuote.latest_quote,retrieved_at:'2026-10-02T09:00:00+09:00'}, {...splitQuote.latest_quote,retrieved_at:'2026-10-11T09:00:00+09:00'}, {...splitQuote.latest_quote,price:0}, {...splitQuote.latest_quote,retrieved_at:'invalid'}]){
  const withheld=E.valuation({...splitQuote,latest_quote:quote},quotedModel);
  for(const key of ['shares','eps','bps','cps','per','pbr','pcr'])assert.equal(withheld.current[key],null);
  assert.equal(withheld.history.at(-1).pcr,null);assert.equal(withheld.detail.at(-1).values.eps,null);
}
console.log('PASS valuation quote contract: one estimated share count, publication dates, reviewed priority without inverse EPS, invalid/stale quote withholding');
// Render the actual value tab with a stale global snapshot date and a fresh detail date.
const vm=require('node:vm'),fs=require('node:fs');
const ui=vm.runInNewContext(fs.readFileSync(require.resolve('../src/company_detail_ui.js'),'utf8')+'\nCompanyDetailUI;', {CompanyDetailEngine:E,DiscoveryEngine:require('../src/discovery_engine'),sessionStorage:{setItem(){}}});
const displayRow={...splitQuote,code:'900000',name:'합성 기업',market:'KOSPI'},displayModel={...quotedModel,notes:[]};
const element={innerHTML:'',querySelector:id=>['#sdCompany','#sdWatch'].includes(id)?{}:null,querySelectorAll:()=>[]};
ui.create({element,rows:[displayRow],models:{'900000':displayModel},research:{rows:{}},meta:{financial_basis:'CFS',price_date:'2026-09-23'},getCode:()=>displayRow.code,setCode(){},shared:{isWatched:()=>false,tables:{}},initial:{tab:'value'}}).render();
assert.match(element.innerHTML,/id="sdValueFrom"[^>]+max="2026-10-07"/);assert.match(element.innerHTML,/완료 종가 기준 2026-10-07/);assert.match(element.innerHTML,/시총·제공가격 조회일 2026-10-08/);
console.log('PASS valuation UI renders separate quote and completed-price dates and current detail date control');
