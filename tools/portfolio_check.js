/* Local deterministic contract check. Does not invent research or fetch data. */
'use strict';
const assert=require('node:assert/strict');
const P=require('../src/portfolio_engine.js');
function checkPortfolio(input,policy={}){
  const before=JSON.stringify(input),p=P.cleanPolicy(policy);
  const candidates=P.candidateChecks(input,p),result=P.propose(input,p);
  assert.equal(JSON.stringify(input),before,'input changed');
  assert.ok(result.items.length<=Math.min(5,p.maxCompanies),'company count');
  assert.equal(new Set(result.items.map(r=>r.issuer_id)).size,result.items.length,'duplicate issuer');
  if(['MODEL_PROPOSAL','CASH_ONLY'].includes(result.status)){
    const weights=result.items.map(r=>r.weight_pct),sum=weights.reduce((a,b)=>a+b,0);
    assert.ok(weights.every(w=>Number.isFinite(w)&&w>0&&w<=p.companyCapPct+1e-8),'company cap');
    assert.ok(Math.abs(sum+result.cash_pct-100)<1e-8,'total allocation');
    assert.ok(result.cash_pct>=p.minCashPct-1e-8,'cash floor');
    for(const [key,cap] of [['sector',p.sectorCapPct],['risk_group',p.groupCapPct]]){
      const grouped=new Map();
      for(const r of result.items){assert.ok(r[key]);grouped.set(r[key],(grouped.get(r[key])||0)+r.weight_pct);}
      assert.ok([...grouped.values()].every(w=>w<=cap+1e-8),key+' cap');
    }
    assert.ok(result.items.every(r=>candidates.some(c=>c.code===r.code&&c.ready)),'unready selection');
    assert.ok(P.stress(result.items,p.stressShockPct)>=-p.stressLossLimitPct-1e-8,'stress assumption');
  }else{
    assert.ok(['DATA_REQUIRED','SETTINGS_REQUIRED'].includes(result.status));
    assert.equal(result.items.length,0);assert.equal(result.cash_pct,null);
  }
  const holdings=P.reviewHoldings(input,p);
  return {verification_status:'passed',portfolio_status:result.status,mode:input.mode,
    engine_version:P.VERSION,evaluation_date:input.as_of,market_data_as_of:input.market_data_as_of||null,
    snapshot_id:input.snapshot_id,policy:p,candidate_count:candidates.length,
    ready_count:candidates.filter(c=>c.ready).length,candidates,
    selected:result.items.map(({code,name,issuer_id,sector,risk_group,weight_pct})=>({code,name,issuer_id,sector,risk_group,weight_pct})),
    cash_pct:result.cash_pct,message:result.message,
    holdings_review:{book:{total_krw:holdings.book.total_krw,complete:holdings.book.complete},
      rows:holdings.rows.map(({code,name,opinion,quantity,value_krw,cost_krw,pnl_krw,reasons,portfolio_action,overweight})=>
        ({code,name,opinion,quantity,value_krw,cost_krw,pnl_krw,reasons,portfolio_action,overweight}))},
    scope:'입력과 배분 제약 검증; 투자성과·최적 수익률 검증 아님'};
}
module.exports={checkPortfolio};
if(require.main===module){
  try{
    const payload=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
    const input=payload.holdings?P.attachMarket(payload.holdings,payload.market):payload.market;
    process.stdout.write(JSON.stringify(checkPortfolio(input,payload.policy||{})));
  }catch(error){process.stderr.write('portfolio validation failed: '+error.name+'\n');process.exitCode=1;}
}
