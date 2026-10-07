'use strict';
const DashboardStability=(()=>{
 const kstDay=now=>new Date(now??Date.now()).toLocaleDateString('sv-SE',{timeZone:'Asia/Seoul'});
 function quoteStatus(quote,now){
  const retrieved=quote?.retrieved_at,parsed=typeof retrieved==='string'&&/([zZ]|[+-]\d\d:\d\d)$/.test(retrieved)?Date.parse(retrieved):NaN;
  const today=kstDay(now),day=Number.isFinite(parsed)?kstDay(parsed):null;
  const invalid=!Number.isFinite(parsed)||parsed>(now??Date.now())+60000;
  const stale=invalid||day!==today;
  const observed=quote?.price_time||quote?.observed_at||'미확인';
  return {stale,retrieved_at:invalid?'미확인':retrieved,observed_at:observed,
   label:stale?'이전 조회 참고가격':'오늘 조회 참고가격',
   detail:`시세시각 ${observed} · 조회 ${invalid?'미확인':retrieved} · 조회시각은 체결시각이 아닙니다`,
   action:stale?'새로고침으로 가격 다시 조회':''};
 }
 function restoreWire(data){
  if(data.wire_format!=='live-v2')return;
  if(Array.isArray(data.wire_text)){
   const text=data.wire_text,marker='__investment_wire_text__';
   const restore=value=>{
    if(value&&typeof value==='object'){
     if(!Array.isArray(value)&&Object.keys(value).length===1&&Object.hasOwn(value,marker)){
      const index=value[marker];if(!Number.isInteger(index)||index<0||typeof text[index]!=='string')throw Error('화면 자료의 출처 설명을 복원하지 못했습니다. 다시 불러오세요.');
      return text[index];
     }
     for(const key of Object.keys(value))value[key]=restore(value[key]);
    }
    return value;
   };
   for(const key of Object.keys(data))if(key!=='wire_text')data[key]=restore(data[key]);
   delete data.wire_text;
  }
  data.snapshot=data.analysis_snapshot;
  const d=data.discovery;
  for(const row of d?.snapshot?.companies||[]){
   const f=d.research?.rows?.[row.code]?.fundamental;
   if(f?.metrics_from_row)f.metrics=row.metrics;
   if(f?.details_from_row)f.metric_details=row.metric_details;
   if(row.common_financial?.details_from_row)row.common_financial.metric_details=row.metric_details;
   if(row.common_financial?.completeness_from_row)row.common_financial.financial_completeness=row.financial_completeness;
   if(row.valuation_from_details)row.valuation_details=Object.fromEntries(['per','pbr'].filter(k=>row.metric_details?.[k]).map(k=>[k,row.metric_details[k]]));
  }
  for(const row of data.trend_following?.rows||[]){
   if(Array.isArray(row.technical_from_research))row.technical=Object.fromEntries(row.technical_from_research.map(key=>{
    const value=d?.research?.rows?.[row.code]?.technical?.[key]??null;
    return [key,value&&typeof value==='object'?JSON.parse(JSON.stringify(value)):value];
   }));
   if(row.analysis_shared)row.technical.trend_analysis=row.analysis;
  }
 }
 return {kstDay,quoteStatus,restoreWire};
})();
if(typeof module!=='undefined')module.exports=DashboardStability;
