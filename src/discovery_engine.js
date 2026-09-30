'use strict';
const DiscoveryEngine = (() => {
  const numeric = v => typeof v === 'number' && Number.isFinite(v);
  const metric = (r,k) => numeric(r.metrics?.[k]) ? r.metrics[k] : null;
  const dimensions = ['roe_pct','operating_margin_pct','revenue_growth_pct','debt_ratio_pct','per','pbr'];
  const limits = {roeMin:['roe_pct',1],marginMin:['operating_margin_pct',1],growthMin:['revenue_growth_pct',1],debtMax:['debt_ratio_pct',-1],perMax:['per',-1],pbrMax:['pbr',-1],rsMin:['price_rs',1]};
  const med = a => {const vs=a.filter(numeric).sort((x,y)=>x-y), n=vs.length;return n?n%2?vs[(n-1)/2]:(vs[n/2-1]+vs[n/2])/2:null;};
  function prepare(snapshot,research){const discovery=snapshot.meta?.discovery===true;return snapshot.companies.filter(r=>['KOSPI','KOSDAQ'].includes(r.market)&&((r.security_type==='ordinary'&&r.analysis_profile==='nonfinancial')||(discovery&&r.security_type==='ordinary_candidate'&&r.eligibility==='candidate'))).map(r=>{const f=research.rows?.[r.code]?.fundamental,t=research.rows?.[r.code]?.technical;return {...r,discovery,legacy_available:r.legacy_available??!discovery,metric_details:{...r.metric_details,...f?.metric_details},metrics:{...r.metrics,...f?.metrics,price_rs:t?.price_strength?.score??null,excess126_pct:t?.rs126_pct??null,excess252_pct:t?.rs252_pct??null}};});}
  const known=v=>typeof v==='string'&&v.trim()&&!/unknown|unverified|미확인|미명시|대기/i.test(v);
  function detail(row,research,key){const f=research.rows?.[row.code]?.fundamental,d=row.metric_details?.[key]||f?.metric_details?.[key];return d||(!row.discovery?{source:row.valuation_details?.[key]?.source,period:row.valuation_details?.[key]?.period||f?.period,basis:row.valuation_details?.[key]?.basis||f?.basis,observed_on:row.valuation_details?.[key]?.price_date,reason:row.valuation_details?.[key]?.reason}:{});}
  function filter(rows, f={}, research={}, watch=[]){
    const q=String(f.query||'').trim().toLocaleLowerCase(), ids=new Set(watch.map(w=>w.code));
    return rows.filter(r=>{
      if(f.market&&r.market!==f.market||f.industry&&r.industry!==f.industry||f.watch&&!ids.has(r.code))return false;
      if(q&&!`${r.code} ${r.name}`.toLocaleLowerCase().includes(q))return false;
      for(const [key,[k,direction]] of Object.entries(limits)){
        if(f[key]===''||f[key]===null||f[key]===undefined)continue;
        const target=Number(f[key]),v=metric(r,k);
        if(!Number.isFinite(target)||v===null||(['per','pbr'].includes(k)&&v<=0)||direction*(v-target)<0)return false;
      }
      const t=research.rows?.[r.code]?.technical;
      if(f.trend&&(r.discovery?t?.price_trend_status:t?.status)!=='pass')return false;
      if(f.highMax!==''&&f.highMax!==undefined&&f.highMax!==null){const lim=Number(f.highMax),gap=t?.gap_to_52w_high_pct;if(!Number.isFinite(lim)||lim<0||!numeric(gap)||gap>0||-gap>lim)return false;}
      return true;
    });
  }
  function sort(rows,key='roe_pct',direction='desc'){
    return [...rows].sort((a,b)=>{const x=metric(a,key),y=metric(b,key);if(x===null||y===null)return x===y?a.code.localeCompare(b.code):x===null?1:-1;return (direction==='asc'?1:-1)*(x-y)||a.code.localeCompare(b.code);});
  }
  function peers(rows,row,research,key){
    const f=research.rows?.[row.code]?.fundamental;
    const own=row.valuation_details?.[key];
    const ownDetail=detail(row,research,key);
    const matches=rows.filter(r=>{
      const g=research.rows?.[r.code]?.fundamental,v=r.valuation_details?.[key];
      if(row.discovery||r.discovery){const other=detail(r,research,key);return r.code!==row.code&&r.industry===row.industry&&known(ownDetail.period)&&known(ownDetail.basis)&&ownDetail.period===other.period&&ownDetail.basis===other.basis&&numeric(metric(r,key))&&(!['per','pbr'].includes(key)||(metric(r,key)>0&&known(ownDetail.observed_on)&&ownDetail.observed_on===other.observed_on));}
      if(r.code===row.code||r.industry!==row.industry||!f?.period||!f?.basis||f.period!==g?.period||f.basis!==g?.basis)return false;
      if(['per','pbr'].includes(key)&&(!own||!v||!own.period||own.period!==v.period||own.basis!==v.basis||own.price_date!==v.price_date))return false;
      return numeric(metric(r,key))&&(!['per','pbr'].includes(key)||metric(r,key)>0);
    });
    return {count:matches.length,median:matches.length>=5?med(matches.map(r=>metric(r,key))):null};
  }
  function sectors(rows,research={}){
    const groups=new Map();for(const r of rows){const key=r.industry||'산업 미분류';if(!groups.has(key))groups.set(key,[]);groups.get(key).push(r);}
    return [...groups].map(([name,rs])=>({name,count:rs.length,cap:rs.reduce((s,r)=>s+(numeric(metric(r,'market_cap_eok'))&&metric(r,'market_cap_eok')>0?metric(r,'market_cap_eok'):0),0),capCount:rs.filter(r=>metric(r,'market_cap_eok')>0).length,metrics:Object.fromEntries(dimensions.map(k=>{const valid=rs.filter(r=>metric(r,k)!==null),first=valid[0]&&detail(valid[0],research,k),comparable=!rs.some(r=>r.discovery)||(valid.length>0&&known(first.period)&&known(first.basis)&&valid.every(r=>{const d=detail(r,research,k);return d.period===first.period&&d.basis===first.basis;}));return [k,{value:comparable?med(valid.map(r=>metric(r,k))):null,count:valid.length,reason:comparable?'':'기간·기준 확인 또는 일치 필요'}];}))})).sort((a,b)=>b.cap-a.cap||a.name.localeCompare(b.name));
  }
  function restoreWatch(value,rows,mode){
    if(!value||value.version!==1||value.data_mode!==mode||!Array.isArray(value.companies)||value.companies.length>10000)throw Error('관심목록 형식 또는 실제/가상 모드가 다릅니다.');
    const map=new Map(rows.map(r=>[r.code,r])),seen=new Set(),companies=[];let skipped=0;
    for(const item of value.companies){const r=map.get(item?.code);if(!r||item.name!==r.name||item.market!==r.market||seen.has(r.code)){skipped++;continue;}seen.add(r.code);companies.push({code:r.code,name:r.name,market:r.market});}
    return {companies,skipped};
  }
  function csv(rows,meta,research){
    const safe=v=>{let s=String(v??'');if(/^[\s\uFEFF]*[=+@\-]/.test(s)&&!/^[-+]?\d+(\.\d+)?$/.test(s.trim()))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};
    const keys=[...dimensions,'price_rs','excess126_pct','excess252_pct'];
    const fields=['source','period','basis','observed_on','reason'];
    const data=[['code','name','market','industry','price_date','financial_period','eligibility','legacy_available',...keys,...keys.flatMap(k=>fields.map(f=>k+'_'+f)),'rs_valid_universe','trend_status'],...rows.map(r=>[r.code,r.name,r.market,r.industry,meta.price_date,research.rows?.[r.code]?.fundamental?.period,r.eligibility||r.analysis_profile,r.legacy_available??!r.discovery,...keys.map(k=>metric(r,k)),...keys.flatMap(k=>fields.map(f=>detail(r,research,k)[f])),research.rows?.[r.code]?.technical?.price_strength?.eligible_count,research.rows?.[r.code]?.technical?.status])];
    return '\ufeff'+data.map(r=>r.map(safe).join(',')).join('\r\n');
  }
  return Object.freeze({numeric,metric,dimensions,limits,med,prepare,detail,known,filter,sort,peers,sectors,restoreWatch,csv});
})();
if(typeof module!=='undefined')module.exports=DiscoveryEngine;
