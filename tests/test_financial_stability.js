const assert=require('assert');
const E=require('../src/company_detail_engine.js');
const model={groups:[{basis:'CFS',cadence:'annual',columns:[{period_end:'2025-12-31',source:'DART',values:{liabilities:50,equity:100,assets:150,balance_debt:20,ebitda:10}}]}]};
const reference={status:'ready',basis:'CFS',currency:'KRW',cadence:'annual',columns:[{period_end:'2025-12-31',values:{total_borrowings:30,net_borrowings:-5,debt_ratio:99,borrowing_dependence:22,debt_ebitda:4,net_debt_ebitda:-.7}}]};
let c=E.financialStability(model,'CFS',null,reference)[0];
assert.equal(c.values.debt_ratio,50);assert.equal(c.values.total_borrowings,30);assert.equal(c.values.net_borrowings,-5);
assert.equal(c.values.debt_ebitda,4); // Do not mix NICE debt with DART EBITDA.
assert.equal(c.sources.net_borrowings,'NICE 원제공값');
c=E.financialStability(model,'CFS',null,{...reference,basis:'OFS'})[0];
assert.equal(c.values.total_borrowings,undefined); // Partial debt is not total debt.
assert.equal(c.values.net_borrowings,undefined);
model.groups[0].columns[0].values.total_borrowings=0;
c=E.financialStability(model,'CFS',null,reference)[0];assert.equal(c.values.total_borrowings,0);assert.equal(c.values.debt_ebitda,0);
assert.equal(E.financialStability(model,'OFS',null,reference).length,0);
console.log('PASS financial stability: source priority, zero/negative values, basis isolation, no mixed-source calculation');
