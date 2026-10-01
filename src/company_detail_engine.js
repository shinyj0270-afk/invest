'use strict';
const CompanyDetailEngine=(()=>{
  const num=v=>typeof v==='number'&&Number.isFinite(v);
  const ratio=(a,b,m=1)=>num(a)&&num(b)&&b>0&&num(a/b*m)?a/b*m:null;
  const flow=['revenue','operating_profit','net_income','ebitda','interest_expense','cost_of_sales','gross_profit','sga','finance_income','finance_cost','other_income','other_cost','pretax','tax','parent_net','nci_net','eps','ocf','cash_generated','noncash_adjustments','noncash_cost','noncash_income','working_capital','icf','financing_cf','cash_change','capex_ppe','capex_intangibles'];
  const enrich=c=>{const v=c.values;return {...c,values:{...v,operating_margin:ratio(v.operating_profit,v.revenue,100),gross_margin:ratio(v.gross_profit,v.revenue,100),net_margin:ratio(v.net_income,v.revenue,100),debt_ratio:ratio(v.liabilities,v.equity,100),fcf:num(v.ocf)&&num(v.capex_ppe)&&num(v.capex_intangibles)?v.ocf-Math.abs(v.capex_ppe)-Math.abs(v.capex_intangibles):null}};};
  function consecutive(cs){return cs.length===4&&cs.every((c,i)=>{
    const d=new Date(c.period_end+'T00:00:00Z'),m=d.getUTCMonth();
    const end=new Date(Date.UTC(d.getUTCFullYear(),m+1,0)).toISOString().slice(0,10);
    return [2,5,8,11].includes(m)&&end===c.period_end&&(!i||(d.getUTCFullYear()*12+m)-(Number(cs[i-1].period_end.slice(0,4))*12+Number(cs[i-1].period_end.slice(5,7))-1)===3);
  });}
  function sum(cs){const last=cs.at(-1),values={...last.values};for(const k of flow){const value=cs.every(c=>num(c.values[k]))?cs.reduce((s,c)=>s+c.values[k],0):null;values[k]=num(value)?value:null;}values.cash_start=cs[0].values.cash_start;const dates=cs.map(c=>c.available_at||c.filing_available_at).filter(Boolean);return enrich({...last,values,period_start:cs[0].period_end,available_at:dates.length===4?dates.sort().at(-1):null,source:[...new Set(cs.map(c=>c.source))].join(' / ')});}
  function periods(model,basis,cadence,table){
    const gs=(model?.groups||[]).filter(g=>g.basis===basis),q=gs.find(g=>g.cadence==='quarter')?.columns||[];
    const changed=q.map(c=>{const input=table?.groups?.find(g=>g.id===basis+'-quarter')?.columns.find(x=>x.period_end===c.period_end);return {...c,cell_notes:{...c.cell_notes,...input?.cell_notes},values:{...c.values,ebitda:input?.values.ebitda??c.values.ebitda}};});
    if(cadence==='quarter')return changed.map(enrich);
    const rolling=[];for(let i=3;i<changed.length;i++){const cs=changed.slice(i-3,i+1);if(consecutive(cs))rolling.push(sum(cs));}
    if(cadence==='ttm')return rolling;
    const annual=gs.find(g=>g.cadence==='annual')?.columns.map(c=>{const input=table?.groups?.find(g=>g.id===basis+'-annual')?.columns.find(x=>x.period_end===c.period_end);return enrich({...c,cell_notes:{...c.cell_notes,...input?.cell_notes},values:{...c.values,ebitda:input?.values.ebitda??c.values.ebitda}});})||[];
    return [...annual,...rolling.filter(c=>c.period_end.endsWith('-12-31')&&!annual.some(a=>a.period_end===c.period_end))].sort((a,b)=>a.period_end.localeCompare(b.period_end));
  }
  function aggregate(bars,cadence){
    if(cadence==='day')return bars.map(p=>({...p}));
    const groups=new Map();for(const b of bars){const d=new Date(b.date+'T00:00:00Z');if(cadence==='week')d.setUTCDate(d.getUTCDate()-((d.getUTCDay()+6)%7));const key=cadence==='month'?b.date.slice(0,7):d.toISOString().slice(0,10);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(b);}
    return [...groups.values()].map(ps=>{const ohl=ps.every(p=>['open','high','low'].every(k=>num(p[k])));return {date:ps.at(-1).date,start:ps[0].date,close:ps.at(-1).close,open:ohl?ps[0].open:null,high:ohl?Math.max(...ps.map(p=>p.high)):null,low:ohl?Math.min(...ps.map(p=>p.low)):null,volume:ps.every(p=>num(p.volume))?ps.reduce((s,p)=>s+p.volume,0):null};});
  }
  function indicators(bars){return bars.map((p,i)=>{
    const result={...p};for(const n of [5,20,60])result['ma'+n]=i+1>=n?bars.slice(i+1-n,i+1).reduce((s,b)=>s+b.close,0)/n:null;
    if(num(result.ma20)){const deviation=Math.sqrt(bars.slice(i-19,i+1).reduce((s,b)=>s+(b.close-result.ma20)**2,0)/20);Object.assign(result,{bbHigh:result.ma20+2*deviation,bbLow:result.ma20-2*deviation,envHigh:result.ma20*1.05,envLow:result.ma20*.95});}return result;
  });}
  function relative(bars,benchmark){const bm=new Map((benchmark||[]).map(b=>[b.date,b.close])),first=bars.find(p=>num(bm.get(p.date))&&bm.get(p.date)>0);return bars.map(p=>{const value=ratio(p.close,bm.get(p.date));return {date:p.date,rs:first&&num(value)?ratio(value,ratio(first.close,bm.get(first.date)),100):null};});}
  function eventList(items,kind){return (items||[]).filter(e=>kind==='all'||e.kind===kind).sort((a,b)=>b.published_on.localeCompare(a.published_on));}
  function valuation(row,model,basis='CFS'){
    const ttm=periods(model,basis,'ttm'),qs=periods(model,basis,'quarter'),last=ttm.at(-1),v=last?.values||{},price=model?.chart?.bars.at(-1)?.close;
    const shares=ratio(row.metrics?.market_cap_eok*1e8,price),equity=x=>basis==='OFS'?x.equity:x.parent_equity,
      profit=x=>basis==='OFS'?x.net_income:x.parent_net;
    const eps=ratio(profit(v)*1e8,shares),bps=ratio(equity(v)*1e8,shares),cps=ratio(v.ocf*1e8,shares);
    const current={per:ratio(price,eps),pbr:ratio(price,bps),pcr:ratio(price,cps),eps,bps,cps,price,shares,date:model?.chart?.as_of,period:last?.period_end};
    const history=(model?.chart?.bars||[]).map(p=>{
      const c=ttm.filter(c=>c.period_end<=p.date&&(c.available_at||c.filing_available_at)&& (c.available_at||c.filing_available_at)<=p.date).at(-1);
      const cv=c?.values||{},book=ratio(equity(cv)*1e8,shares),earn=ratio(profit(cv)*1e8,shares),cash=ratio(cv.ocf*1e8,shares);
      return {date:p.date,close:p.close,period:c?.period_end,available_at:c?.available_at||c?.filing_available_at,per:ratio(p.close,earn),pbr:ratio(p.close,book),pcr:ratio(p.close,cash),eps:earn,bps:book,cps:cash};
    });
    const detail=ttm.map(c=>{const close=(model?.chart?.bars||[]).filter(p=>p.date<=c.period_end).at(-1)?.close,cv=c.values,earn=ratio(profit(cv)*1e8,shares),book=ratio(equity(cv)*1e8,shares);return {...c,values:{...cv,eps:earn,bps:book,close,per:ratio(close,earn),pbr:ratio(close,book)},provisional:true};});
    return {current,history,detail,ttm,quarters:qs};
  }
  function quantile(values,p){const sorted=values.filter(num).sort((a,b)=>a-b);if(!sorted.length)return null;const pos=(sorted.length-1)*p,i=Math.floor(pos);return sorted[i]+(sorted[Math.min(i+1,sorted.length-1)]-sorted[i])*(pos-i);}
  function distribution(history,key,current){const values=history.map(p=>p[key]).filter(v=>num(v)&&v>0);if(values.length<20||!num(current)||current<=0)return null;return {count:values.length,min:Math.min(...values),max:Math.max(...values),percentile:values.filter(v=>v<=current).length/values.length*100,bands:[.1,.25,.5,.75,.9].map(p=>quantile(values,p)),histogram:Array.from({length:12},(_,i)=>{const lo=quantile(values,0),hi=quantile(values,1),step=(hi-lo)/12||1;return {lo:lo+step*i,hi:lo+step*(i+1),count:values.filter(v=>v>=lo+step*i&&(i===11?v<=hi:v<lo+step*(i+1))).length};})};}
  function rim(bps,eps,r,decay=.9){
    if(!num(bps)||bps<=0||!num(eps)||!num(r)||r<=0||r>1||!num(decay)||decay<0||decay>1)return null;
    const excess=eps-bps*r,scenarios=[1,.9,.8].map(w=>({w,value:bps+excess*w/(1+r-w)}));
    return {excess,scenarios,years:Array.from({length:10},(_,i)=>({year:i+1,excess:excess*Math.pow(decay,i+1),pv:excess*Math.pow(decay,i+1)/Math.pow(1+r,i+1)}))};
  }
  function decomposition(startCap,endCap,startProfit,endProfit){if(![startCap,endCap,startProfit,endProfit].every(v=>num(v)&&v>0))return null;const initialMultiple=startCap/startProfit,profit=(endProfit-startProfit)*initialMultiple,multiple=endCap-startCap-profit;return {start:startCap,profit,multiple,end:endCap,initialMultiple,finalMultiple:endCap/endProfit};}
  function summary(row,model,research,meta,basis=meta.financial_basis){const qs=periods(model,basis,'quarter'),latest=qs.at(-1),v=latest?.values||{},m=basis===meta.financial_basis?(row.metrics||{}):{market_cap_eok:row.metrics?.market_cap_eok},f=research.rows?.[row.code]?.fundamental?.metrics||{},val=valuation(row,model,basis).current;
    const prior=qs.find(c=>c.period_end===String(Number(latest?.period_end?.slice(0,4))-1)+latest?.period_end?.slice(4)),growth=ratio(v.revenue-prior?.values.revenue,prior?.values.revenue,100),ttm=periods(model,basis,'ttm').at(-1),bookKey=basis==='OFS'?'equity':'parent_equity',profitKey=basis==='OFS'?'net_income':'parent_net',oldBook=prior?.values[bookKey],roe=num(oldBook)&&num(v[bookKey])?ratio(ttm?.values[profitKey],(oldBook+v[bookKey])/2,100):null;
    return [
      ['cap','시가총액',m.market_cap_eok,'억원',meta.price_date],['revenue','매출액',v.revenue,'억원',latest?.period_end],
      ['op','영업이익',v.operating_profit,'억원',latest?.period_end],['net','당기순이익',v.net_income,'억원',latest?.period_end],
      ['opMargin','영업이익률',v.operating_margin??m.operating_margin_pct,'%',latest?.period_end],
      ['growth','매출성장률',(basis===meta.financial_basis?f.revenue_growth_pct??m.revenue_growth_pct:null)??growth,'%','전년 동기 대비 · '+(latest?.period_end||'기간 미확인')],
      ['roe','ROE',m.roe_pct??roe,'%',num(m.roe_pct)?'검토 TTM 기준':'TTM 이익 / 전년동기·현재 평균자본'],
      ['per','PER',m.per??val.per,'배',num(m.per)?'검토 지표':'시총 / TTM 지배순이익 근사'],
      ['pbr','PBR',m.pbr??val.pbr,'배',num(m.pbr)?'검토 지표':'시총 / 지배자본 근사'],
      ['debt','부채비율',v.debt_ratio??m.debt_ratio_pct,'%',latest?.period_end],
      ['borrowings','총차입금',v.total_borrowings,'억원',latest?.cell_notes?.total_borrowings||latest?.period_end]
    ];
  }
  return {num,ratio,consecutive,periods,aggregate,indicators,relative,eventList,valuation,quantile,distribution,rim,decomposition,summary};
})();
if(typeof module!=='undefined')module.exports=CompanyDetailEngine;
