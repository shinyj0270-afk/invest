'use strict';
const assert=require('assert');
global.DiscoveryEngine=require('../src/discovery_engine.js');
const E=require('../src/industry_engine.js');

const detail={period:'2026-06-30',basis:'CFS'};
const row=(code,industry,cap,extra={})=>({code,name:'N'+code,market:'KOSPI',industry,discovery_allowed:true,
  metrics:{market_cap_eok:cap,roe_pct:10,operating_margin_pct:5,revenue_growth_pct:3,debt_ratio_pct:50},
  metric_details:{roe_pct:detail,operating_margin_pct:detail,revenue_growth_pct:detail,debt_ratio_pct:detail},...extra});
const tech=(close,sma200,r1,r3)=>({technical:{as_of:'2026-10-16',close,sma:{'200':sma200},price_health:{status:'ready'},
  short_rs:{'1m':{return_pct:r1},'3m':{return_pct:r3},'6m':{return_pct:null}}}});
const rows=[row('A','Semis',900),row('B','Semis',50),row('C','Semis',30),row('D','Semis',15),row('E','Semis',5),
  row('F','Tiny',100),row('G','Tiny',100,{discovery_allowed:false}),row('H','Semis',10,{market:'KOSDAQ'})];
const research={rows:{A:tech(110,100,20,30),B:tech(90,100,-5,-2),C:tech(120,100,2,4),D:tech(null,100,null,null),E:tech(101,100,-1,1),F:tech(10,9,1,1),
  H:tech(1,2,0,0)}};
const short=(score,count)=>({return_pct:12.5,score,count,cap_eok:1000});
const insights={definition:'def',sectors:[
  {market:'KOSPI',industry:'Semis',count:5,short_rs:{'1m':short(91.2,5),'3m':short(80,5),'6m':short(null,0)}},
  {market:'KOSPI',industry:'Tiny',count:1,short_rs:{'1m':short(null,1),'3m':short(null,1),'6m':short(null,1)}},
  {market:'KOSDAQ',industry:'Semis',count:1,short_rs:{'1m':short(null,1),'3m':short(null,1),'6m':short(null,1)}}]};

const groups=E.groups(rows,research,insights);
assert.deepEqual(groups.map(g=>g.key),['KOSDAQ|Semis','KOSPI|Semis','KOSPI|Tiny']);
const semis=groups.find(g=>g.key==='KOSPI|Semis');
// Membership mirrors discovery rows; excluded companies never join a group.
assert.equal(semis.count,5);assert.equal(groups.find(g=>g.key==='KOSPI|Tiny').count,1);
// Existing cap-weighted RS is reused, not recomputed.
assert.equal(semis.rs['1m'].score,91.2);assert.equal(semis.rs['1m'].return_pct,12.5);
// Breadth: only companies with close and 200-day average count; D has no close.
assert.deepEqual(semis.breadth.above200,{count:3,eligible:4,pct:75});
assert.deepEqual(semis.breadth.positive3m,{count:3,eligible:4,pct:75});
// Concentration uses positive market caps; top company share and top-3 share.
assert.equal(semis.concentration.top.code,'A');
assert.ok(Math.abs(semis.concentration.top_share_pct-900/1000*100)<1e-9);
assert.ok(Math.abs(semis.concentration.top3_share_pct-980/1000*100)<1e-9);
// Equal-weight median and cap-weighted return excluding the largest member.
assert.equal(semis.spread.median1m_pct,0.5);
const exTop=(50*-5+30*2+5*-1)/(50+30+5);
assert.ok(Math.abs(semis.spread.ex_top1m_pct-exTop)<1e-9);
// The largest member stays the exclusion target even when its return is missing.
const missingTop=E.groups([row('T0','MissingTop',1000),row('T1','MissingTop',100),row('T2','MissingTop',50)],
  {rows:{T0:tech(null,100,null,null),T1:tech(110,100,10,10),T2:tech(90,100,-10,-10)}},null)[0];
assert.equal(missingTop.concentration.top.code,'T0');
assert.equal(missingTop.spread.ex_top_count,2);
assert.ok(Math.abs(missingTop.spread.ex_top1m_pct-10/3)<1e-9);
// Financial medians come from DiscoveryEngine.sectors with comparability checks.
assert.equal(semis.financial.roe_pct.value,10);assert.equal(semis.financial.roe_pct.count,5);
// Revenue breadth: existing revenue growth, only within the most common period/basis cohort.
assert.deepEqual(semis.revenue,{count:5,eligible:5,pct:100,period:'2026-06-30',basis:'CFS',excluded:0,missing:0});
const mixed=[row('M1','Mix',10),row('M2','Mix',10),row('M3','Mix',10),row('M4','Mix',10),row('M5','Mix',10)];mixed[4].metrics.revenue_growth_pct=null;
mixed[1].metrics.revenue_growth_pct=-2;mixed[2].metrics.revenue_growth_pct=0;
mixed[3].metric_details={...mixed[3].metric_details,revenue_growth_pct:{period:'2025-12-31',basis:'OFS'}};
const mix=E.groups(mixed,{rows:{}},null)[0].revenue;
assert.deepEqual(mix,{count:1,eligible:3,pct:1/3*100,period:'2026-06-30',basis:'CFS',excluded:1,missing:1});
const unknown=[row('U1','Unk',10)];unknown[0].metric_details={revenue_growth_pct:{period:'미확인',basis:'CFS'}};
assert.deepEqual(E.groups(unknown,{rows:{}},null)[0].revenue,{count:0,eligible:0,pct:null,period:null,basis:null,excluded:1,missing:0});
// Profit breadth compares amounts (not percentage growth) in one dated cohort.
const profitRow=(code,current,previous,extra={})=>row(code,'Profit',10,{common_financial:{operating_profit_comparison:{
  status:'ready',comparison:'single_quarter_yoy_amount',period:'2026-06-30',previous_period:'2025-06-30',
  period_start:'2026-04-01',previous_period_start:'2025-04-01',basis:'CFS',currency:'KRW',current,previous,...extra}}});
const profitMembers=[profitRow('P1',20,10),profitRow('P2',5,-5),profitRow('P3',-5,-10),
  profitRow('P4',-10,-10),profitRow('P5',-20,-10),profitRow('P6',0,-10),profitRow('P7',5,0),
  profitRow('P8',100,1,{basis:'OFS'}),profitRow('P9',100,1,{currency:'USD'}),row('P10','Profit',10)];
const profit=E.groups(profitMembers,{},null)[0].profit;
assert.equal(profit.count,5);assert.equal(profit.eligible,7);assert.equal(profit.pct,5/7*100);
assert.deepEqual(profit.categories,{profit_growth:1,turnaround:1,loss_narrowing:1,breakeven:1,from_zero:1});
assert.equal(profit.excluded,2);assert.equal(profit.missing,1);
const profitMissing=E.groups([row('PM','Profit',10)],{},null)[0].profit;
assert.equal(profitMissing.pct,null);assert.equal(profitMissing.eligible,0);
const newer=profitRow('PN',10,5,{period:'2026-09-30',previous_period:'2025-09-30',period_start:'2026-07-01',previous_period_start:'2025-07-01'});
assert.equal(E.groups([profitMembers[0],newer],{},null)[0].profit.period,'2026-09-30');
// Ranking only where the existing RS percentile exists; thin groups are listed, never ranked.
const view=E.overview(groups,{sort:'rs1m'});
assert.deepEqual(view.ranked.map(g=>g.key),['KOSPI|Semis']);
assert.deepEqual(view.limited.map(g=>g.key),['KOSDAQ|Semis','KOSPI|Tiny']);
assert.deepEqual(E.overview(groups,{sort:'rs1m',market:'KOSDAQ'}).limited.map(g=>g.key),['KOSDAQ|Semis']);
assert.deepEqual(E.overview(groups,{sort:'rs1m',query:'tin'}).limited.map(g=>g.key),['KOSPI|Tiny']);
// Breadth sort needs at least five eligible members; otherwise the group is not ranked.
assert.deepEqual(E.overview(groups,{sort:'breadth'}).ranked.map(g=>g.key),[]);
// Missing insights: no RS, no ranking, but observed members remain visible.
const bare=E.groups(rows,research,null);
assert.equal(bare.find(g=>g.key==='KOSPI|Semis').rs,null);
assert.equal(E.overview(bare,{sort:'rs1m'}).ranked.length,0);
// Valid scores from different exchange distributions never form a shared ranking.
const twoMarkets=[{...semis,key:'KOSPI|A',industry:'A'},
  {...semis,key:'KOSDAQ|B',industry:'B',market:'KOSDAQ',rs:{'1m':short(99,5)}}];
const separated=E.overview(twoMarkets);
assert.deepEqual(separated.markets.map(m=>[m.market,m.ranked.map(g=>g.key)]),
  [['KOSPI',['KOSPI|A']],['KOSDAQ',['KOSDAQ|B']]]);
assert.deepEqual(E.overview(twoMarkets,{market:'KOSDAQ'}).markets.map(m=>m.market),['KOSDAQ']);

// Research links: explicit instrument links and transparent name-correspondence candidates only.
const library={theses:[
  {id:'t1',value:{sector:'반도체',claim:'c',instruments:[]},metadata:{sector:'반도체'}},
  {id:'t2',value:{sector:'전력기기',claim:'c',instruments:[{code:'A',market:'KOSPI',kind:'stock'}]},metadata:{}},
  {id:'t3',value:{sector:'산업공통',claim:'c'},metadata:{sector:'산업공통'}}],cards:[],notes:[],sources:[]};
const map={sectors:{'반도체':['반도체와반도체장비'],'전력기기':['전기장비']}};
const linked=E.related(library,{industry:'반도체와반도체장비',members:[{code:'A'}]},map);
assert.deepEqual(linked.map(l=>[l.record.id,l.link]),[['t2','company'],['t1','map']]);
// Only the user-confirmed table links sectors; substring similarity alone never does.
assert.deepEqual(E.related(library,{industry:'반도체와반도체장비',members:[]},{sectors:{}}),[]);
assert.deepEqual(E.related(library,{industry:'반도체장비',members:[]},map),[]);
assert.deepEqual(E.related(library,{industry:'전기장비',members:[]},map).map(l=>l.record.id),['t2']);
assert.deepEqual(E.related(library,{industry:'화학',members:[]},map),[]);
assert.deepEqual(E.librarySectors(library),['반도체','전력기기']);
// Thesis states are labelled as research, never as a current leading-industry call.
assert.equal(E.statusLabel('active'),'연구 중 · 검증 전');
assert.equal(E.statusLabel('invalidated'),'반증됨');
assert.equal(E.statusLabel(undefined),'상태 미기록');
console.log('PASS industry engine: membership, reused RS, breadth, concentration, medians, unranked thin groups, research links');
