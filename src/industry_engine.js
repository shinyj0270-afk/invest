'use strict';
// Industry overview aggregates. Reuses the stored cap-weighted short RS (market_insights)
// and DiscoveryEngine.sectors medians; adds only predefined breadth/concentration counts.
const IndustryEngine=(()=>{
  const num=v=>typeof v==='number'&&Number.isFinite(v);
  const MIN_MEMBERS=5;
  const GENERIC=new Set(['','산업공통','미확인','미분류','unknown']);
  const median=vs=>{const a=vs.filter(num).sort((x,y)=>x-y),n=a.length;return n?n%2?a[(n-1)/2]:(a[n/2-1]+a[n/2])/2:null;};
  const share=(count,eligible)=>({count,eligible,pct:eligible?count/eligible*100:null});
  const cap=r=>{const v=r.metrics?.market_cap_eok;return num(v)&&v>0?v:null;};
  const tech=(research,r)=>research?.rows?.[r.code]?.technical||{};
  const priced=t=>num(t.close)&&(t.price_health?.status??'ready')==='ready';

  function breadth(members,research){
    const ts=members.map(r=>tech(research,r));
    const above=ts.filter(t=>priced(t)&&num(t.sma?.['200']));
    const r3=ts.filter(t=>priced(t)&&num(t.short_rs?.['3m']?.return_pct));
    return {above200:share(above.filter(t=>t.close>t.sma['200']).length,above.length),
      positive3m:share(r3.filter(t=>t.short_rs['3m'].return_pct>0).length,r3.length)};
  }
  function concentration(members){
    const capped=members.filter(r=>cap(r)!==null).sort((a,b)=>cap(b)-cap(a)||a.code.localeCompare(b.code));
    const total=capped.reduce((s,r)=>s+cap(r),0),top=capped[0];
    return {cap_eok:total,cap_count:capped.length,top:top?{code:top.code,name:top.name}:null,
      top_share_pct:total?cap(top)/total*100:null,top3_share_pct:total?capped.slice(0,3).reduce((s,r)=>s+cap(r),0)/total*100:null};
  }
  function spread(members,research){
    const r1=r=>tech(research,r).short_rs?.['1m']?.return_pct;
    const valid=members.filter(r=>priced(tech(research,r))&&num(r1(r)));
    const capped=valid.filter(r=>cap(r)!==null).sort((a,b)=>cap(b)-cap(a)||a.code.localeCompare(b.code)).slice(1);
    const weight=capped.reduce((s,r)=>s+cap(r),0);
    return {median1m_pct:median(valid.map(r1)),count:valid.length,
      ex_top1m_pct:weight?capped.reduce((s,r)=>s+cap(r)*r1(r),0)/weight:null,ex_top_count:capped.length};
  }
  // Revenue breadth reuses the stored revenue growth; only the most common
  // known period/basis cohort is compared, other members are counted as excluded.
  function revenue(members,research){
    const valid=members.filter(r=>num(r.metrics?.revenue_growth_pct)),cohorts=new Map();
    for(const r of valid){const d=DiscoveryEngine.detail(r,research||{},'revenue_growth_pct');
      if(!DiscoveryEngine.known(d.period)||!DiscoveryEngine.known(d.basis))continue;
      const key=d.period+'|'+d.basis;if(!cohorts.has(key))cohorts.set(key,[]);cohorts.get(key).push(r);}
    const [key,cohort]=[...cohorts].sort((a,b)=>b[1].length-a[1].length||b[0].localeCompare(a[0]))[0]||[null,[]];
    const [period,basis]=key?key.split('|'):[null,null],count=cohort.filter(r=>r.metrics.revenue_growth_pct>0).length;
    return {count,eligible:cohort.length,pct:cohort.length?count/cohort.length*100:null,period,basis,excluded:valid.length-cohort.length,missing:members.length-valid.length};
  }
  function groups(rows,research,insights){
    const map=new Map();
    for(const r of rows){if(r.discovery_allowed===false)continue;const industry=r.industry||'산업 미분류',key=r.market+'|'+industry;
      if(!map.has(key))map.set(key,{key,market:r.market,industry,members:[]});map.get(key).members.push(r);}
    const stored=new Map((insights?.sectors||[]).map(s=>[s.market+'|'+s.industry,s]));
    return [...map.values()].sort((a,b)=>a.key.localeCompare(b.key)).map(g=>{
      const sector=stored.get(g.key),fin=DiscoveryEngine.sectors(g.members,research||{})[0];
      return {...g,count:g.members.length,rs:sector?sector.short_rs:null,rs_count:sector?.count??null,
        breadth:breadth(g.members,research),revenue:revenue(g.members,research),concentration:concentration(g.members),spread:spread(g.members,research),
        financial:fin?.metrics||{},priced_count:g.members.filter(r=>priced(tech(research,r))).length};
    });
  }
  function rankValue(g,sort){
    if(sort==='breadth')return g.breadth.above200.eligible>=MIN_MEMBERS?g.breadth.above200.pct:null;
    if(sort==='cap')return g.concentration.cap_count>=MIN_MEMBERS?g.concentration.cap_eok:null;
    const k={rs1m:'1m',rs3m:'3m',rs6m:'6m'}[sort]||'1m',v=g.rs?.[k]?.score;return num(v)?v:null;
  }
  function overview(all,{sort='rs1m',market='',query=''}={}){
    const q=String(query).trim().toLocaleLowerCase();
    const shown=all.filter(g=>(!market||g.market===market)&&(!q||g.industry.toLocaleLowerCase().includes(q)));
    const ranked=shown.filter(g=>rankValue(g,sort)!==null).sort((a,b)=>rankValue(b,sort)-rankValue(a,sort)||a.key.localeCompare(b.key));
    const limited=shown.filter(g=>rankValue(g,sort)===null).sort((a,b)=>a.key.localeCompare(b.key));
    return {ranked,limited,sort,min_members:MIN_MEMBERS};
  }
  const sectorsOf=r=>[...new Set([r.metadata?.sector,r.value?.sector].filter(s=>typeof s==='string'&&!GENERIC.has(s.trim())))];
  const instrumentsOf=r=>[...(r.metadata?.instruments||[]),...(r.value?.instruments||[])];
  const records=lib=>[['thesis',lib?.theses],['master',lib?.cards],['agent_note',lib?.notes],['source',lib?.sources]].flatMap(([kind,rs])=>(rs||[]).map(record=>({kind,record})));
  // Sector links use only the user-confirmed table (config/industry_sector_map.json);
  // text similarity alone never links research to an industry.
  function related(lib,{industry,members},map){
    const codes=new Set((members||[]).map(m=>m.code)),mapped=s=>(map?.sectors?.[s]||[]).includes(industry),out=[];
    for(const {kind,record} of records(lib)){
      if(instrumentsOf(record).some(i=>codes.has(i?.code)))out.push({kind,record,link:'company'});
      else if(sectorsOf(record).some(mapped))out.push({kind,record,link:'map'});
    }
    return out.sort((a,b)=>(a.link==='company'?0:1)-(b.link==='company'?0:1));
  }
  function librarySectors(lib){return [...new Set(records(lib).flatMap(({record})=>sectorsOf(record)))].sort();}
  function statusLabel(s){return ({active:'연구 중 · 검증 전',invalidated:'반증됨',retired:'연구 종료'})[s]||(s?String(s):'상태 미기록');}
  return Object.freeze({num,median,groups,overview,rankValue,related,librarySectors,statusLabel,MIN_MEMBERS});
})();
if(typeof module!=='undefined')module.exports=IndustryEngine;
