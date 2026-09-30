global.DiscoveryEngine=require('../src/discovery_engine.js');
const assert=require('assert'), A=require('../src/advanced_visuals.js');
const rows=Array.from({length:2455},(_,i)=>({metrics:{roe_pct:i%3?10:null,per:i%5?12:null}}));
const g=A.aggregate(rows);assert.equal(g.total,2455);assert.equal(g.bins.length,100);assert.equal(g.bins.reduce((a,b)=>a+b,0)+g.missing,2455);
assert.equal(A.aggregate([{metrics:{roe_pct:0,per:0}}]).known,1);
assert.equal(A.aggregate([{metrics:{roe_pct:NaN,per:10}}]).missing,1);
assert.equal(A.aggregate([{metrics:{roe_pct:-10000,per:10000}}]).bins[90],1);
assert.equal(A.aggregate([]).known,0);console.log('PASS Advanced aggregation: population conservation, unknown, zero, bounds, empty');
