const assert=require('node:assert/strict'),E=require('../src/company_detail_engine');
const q=['2025-09-30','2025-12-31','2026-03-31','2026-06-30'].map((d,i)=>({period_end:d,source:'test',values:{revenue:100+i,operating_profit:10+i,net_income:5+i,ebitda:null,assets:200+i,equity:100,liabilities:100+i,interest_expense:2}}));
const m={groups:[{id:'CFS-quarter',basis:'CFS',cadence:'quarter',columns:q}]};
assert.equal(E.periods(m,'CFS','ttm')[0].values.revenue,406);
assert.equal(E.periods(m,'CFS','ttm')[0].values.assets,203);
assert.equal(E.periods(m,'CFS','ttm')[0].values.ebitda,null);
assert.equal(E.periods(m,'OFS','ttm').length,0);assert.equal(E.periods(m,'CFS','annual').length,0);
const missing=structuredClone(m);missing.groups[0].columns[1].period_end='2025-11-30';assert.equal(E.periods(missing,'CFS','ttm').length,0);
const table={groups:[{id:'CFS-quarter',columns:q.map(c=>({period_end:c.period_end,values:{ebitda:20}}))}]};assert.equal(E.periods(m,'CFS','ttm',table)[0].values.ebitda,80);
const bars=['2026-09-21','2026-09-22','2026-09-28'].map((date,i)=>({date,open:10+i,high:14+i,low:8+i,close:12+i,volume:100+i}));
const weeks=E.aggregate(bars,'week');assert.equal(weeks.length,2);assert.equal(weeks[0].open,10);assert.equal(weeks[0].close,13);assert.equal(weeks[0].volume,201);assert.equal(E.aggregate(bars,'month').length,1);
bars[0].open=null;assert.equal(E.aggregate(bars,'week')[0].high,null);
const flat=Array.from({length:60},(_,i)=>({close:10,date:String(i)}));assert.equal(E.indicators(flat)[19].bbHigh,10);assert.equal(E.indicators(flat)[19].envHigh,10.5);assert.equal(E.indicators(flat)[59].ma60,10);assert.equal(E.indicators(flat)[18].ma20,null);
const rs=E.relative([{date:'1',close:10},{date:'2',close:20},{date:'3',close:20}],[{date:'1',close:100},{date:'2',close:100}]);assert.equal(rs[0].rs,100);assert.equal(rs[1].rs,200);assert.equal(rs[2].rs,null);
assert.equal(E.eventList([{published_on:'2026-02-01',kind:'news'},{published_on:'2026-03-01',kind:'disclosure'}],'news').length,1);
console.log('PASS company detail: exact four quarters, point balances, missing/basis/annual boundaries, shared EBITDA, OHLC aggregation, indicators, missing benchmark');

// Reading guide: matching years/basis, missing capex and zero/negative denominators.
const readingModel={groups:[{basis:'CFS',cadence:'quarter',columns:[
 {period_end:'2025-06-30',values:{revenue:100,operating_profit:10}},
 {period_end:'2026-06-30',values:{revenue:125,operating_profit:25,ocf:50,capex_ppe:-20,capex_intangibles:5,cash_end:60,total_borrowings:100,liabilities:150,equity:100}}
]}]};
const beforeReading=JSON.stringify(readingModel),rd=E.reading(readingModel,'CFS');
assert.equal(rd.revenueGrowth,25);assert.equal(rd.marginChange,10);
assert.equal(rd.cash.fcf,25);assert.equal(rd.cash.capex,25);assert.equal(rd.cash.debtRatio,150);
assert.equal(JSON.stringify(readingModel),beforeReading);
assert.equal(E.reading(readingModel,'OFS').latest,undefined);
readingModel.groups[0].columns[0].values.revenue=-100;
assert.equal(E.reading(readingModel,'CFS').revenueGrowth,null);
readingModel.groups[0].columns[1].values.capex_intangibles=null;
assert.equal(E.reading(readingModel,'CFS').cash.fcf,null);
assert.equal(E.reading(readingModel,'CFS').cash.capex,null);
assert.equal(E.reading(null,'CFS').cash.ocf,null);
console.log('PASS company reading: same-period arithmetic, missing/basis boundaries, no mutation');
