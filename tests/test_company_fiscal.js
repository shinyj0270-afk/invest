'use strict';
const assert=require('node:assert/strict'),E=require('../src/company_detail_engine');
function quarter(fy,q,endMonth=2,currency='KRW',segment='feb-v1'){
  const start=new Date(Date.UTC(fy-(endMonth===12?0:1),endMonth%12+(q-1)*3,1)),end=new Date(Date.UTC(start.getUTCFullYear(),start.getUTCMonth()+3,0));
  return {code:'900001',basis:'CFS',currency,calendar_segment:segment,fiscal_year:fy,fiscal_quarter:q,year_end_month:endMonth,period_start:start.toISOString().slice(0,10),period_end:end.toISOString().slice(0,10),available_at:end.toISOString().slice(0,10),values:{revenue:10*q,operating_profit:q,net_income:q,parent_net:q,parent_equity:100,assets:200,liabilities:100,ocf:q}};
}
const q=[1,2,3,4].map(n=>quarter(2024,n)),m={groups:[{basis:'CFS',cadence:'quarter',columns:q}]};
assert.equal(q[3].period_end,'2024-02-29');assert.equal(E.consecutive(q),true);
assert.equal(E.periods(m,'CFS','ttm')[0].values.revenue,100);
assert.equal(E.periods(m,'CFS','ttm')[0].period_start,'2023-03-01');
assert.equal(E.periods(m,'CFS','annual')[0].period_end,'2024-02-29');
const leapPrior=quarter(2023,4);assert.equal(E.priorYear(q[3],[leapPrior]),leapPrior);
const wrongYear=quarter(2022,4);assert.equal(E.priorYear(q[3],[wrongYear]),undefined);
assert.equal(E.priorYear(q[3],[{...leapPrior,currency:'USD'}]),undefined);
assert.equal(E.priorYear(q[3],[{...leapPrior,calendar_segment:'changed-calendar'}]),undefined);
assert.equal(E.priorYear({period_end:'2024-02-29'},[{period_end:'2023-02-28'}]).period_end,'2023-02-28');
const row={code:'900001',metrics:{},latest_quote:{}},model={groups:[{basis:'CFS',cadence:'quarter',columns:[leapPrior,...q]}]};
assert.equal(E.summary(row,model,{rows:{}},{financial_basis:'CFS'}).find(x=>x[0]==='growth')[2],0);
for(const mutation of [c=>({...c,currency:'USD'}),c=>({...c,calendar_segment:'new'}),c=>({...c,basis:'OFS'}),c=>({...c,year_end_month:3}),c=>({...c,period_start:'2023-06-02'}),c=>({...c,fiscal_quarter:null}),c=>({period_end:c.period_end,values:c.values})]){
  const mixed=q.map((c,i)=>i===1?mutation(c):c);assert.equal(E.consecutive(mixed),false);assert.equal(E.periods({groups:[{basis:'CFS',cadence:'quarter',columns:mixed}]},'CFS','ttm').length,0);
}
const noProof=q.map(c=>({period_end:c.period_end,values:c.values}));assert.equal(E.consecutive(noProof),false);
const usd=q.map(c=>({...c,currency:'USD'}));assert.equal(E.consecutive(usd),true);assert.equal(E.periods({groups:[{basis:'CFS',currency:'USD',cadence:'quarter',columns:usd}]},'CFS','quarter').length,0);
const common={basis:'CFS',currency:'USD',period:'FY2024 Q4',amounts:{revenue:999},native_amounts:{revenue:20e6,operating_profit:2e6,net_income:1e6,balance_debt:5e6},metrics:{operating_margin_pct:10,per:20,pbr:2},metric_details:{}};
const summary=E.summary(row,{groups:[],common_financial:common},{rows:{}},{financial_basis:'CFS'});
assert.deepEqual(summary.find(x=>x[0]==='revenue').slice(2,4),[20,'백만 USD']);assert.equal(summary.find(x=>x[0]==='per')[2],null);
assert.equal(E.valuation(row,{groups:[],common_financial:common},'CFS').current.per,null);
console.log('PASS fiscal quarters: February leap year, explicit fiscal YoY/annual, identity/gap/unknown rejection, native USD units and valuation exclusion');
// A filing date establishes only the official cells; it cannot date provider cells.
const mixedProof=q.map(c=>({...c,available_at:null,filing_available_at:'2024-04-01',cell_provenance:{parent_net:{source:'provider',available_at:null},parent_equity:{source:'provider',available_at:null},ocf:{source:'DART',available_at:'2024-04-01'}}}));
const historical=E.valuation({metrics:{market_cap_eok:10}},{groups:[{basis:'CFS',cadence:'quarter',columns:mixedProof}],chart:{bars:[{date:'2024-03-29',close:1000},{date:'2024-04-01',close:1000}],as_of:'2024-04-01'}}).history;
assert.equal(historical[0].pcr,null);assert.equal(historical[1].pcr,1);
for(const p of historical){assert.equal(p.per,null);assert.equal(p.pbr,null);assert.equal(p.eps,null);assert.equal(p.bps,null);}
const missingProof=mixedProof.map((c,i)=>i===1?{...c,cell_provenance:{...c.cell_provenance,ocf:{available_at:null}}}:c);
assert.equal(E.valuation({metrics:{market_cap_eok:10}},{groups:[{basis:'CFS',cadence:'quarter',columns:missingProof}],chart:{bars:[{date:'2024-04-01',close:1000}]}}).history[0].pcr,null);
console.log('PASS historical ratios require per-cell publication across all four quarters; filing dates never date provider profit/book');
const detail=E.valuation({metrics:{market_cap_eok:10}},{groups:[{basis:'CFS',cadence:'quarter',columns:mixedProof}],chart:{bars:[{date:'2024-02-29',close:1000},{date:'2024-04-01',close:1000}],as_of:'2024-04-01'}}).detail;
assert.equal(detail[0].values.per,null);assert.equal(detail[0].values.pbr,null);
