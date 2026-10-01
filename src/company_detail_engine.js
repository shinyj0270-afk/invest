'use strict';
const CompanyDetailEngine=(()=>{
  const num=v=>typeof v==='number'&&Number.isFinite(v);
  const ratio=(a,b,m=1)=>num(a)&&num(b)&&b>0&&num(a/b*m)?a/b*m:null;
  const flow=['revenue','operating_profit','net_income','ebitda','interest_expense'];
  const enrich=c=>({...c,values:{...c.values,operating_margin:ratio(c.values.operating_profit,c.values.revenue,100),net_margin:ratio(c.values.net_income,c.values.revenue,100),debt_ratio:ratio(c.values.liabilities,c.values.equity,100)}});
  function consecutive(cs){return cs.length===4&&cs.every((c,i)=>{
    const d=new Date(c.period_end+'T00:00:00Z'),m=d.getUTCMonth();
    const end=new Date(Date.UTC(d.getUTCFullYear(),m+1,0)).toISOString().slice(0,10);
    return [2,5,8,11].includes(m)&&end===c.period_end&&(!i||(d.getUTCFullYear()*12+m)-(Number(cs[i-1].period_end.slice(0,4))*12+Number(cs[i-1].period_end.slice(5,7))-1)===3);
  });}
  function sum(cs){const last=cs.at(-1),values={...last.values};for(const k of flow){const value=cs.every(c=>num(c.values[k]))?cs.reduce((s,c)=>s+c.values[k],0):null;values[k]=num(value)?value:null;}return enrich({...last,values,period_start:cs[0].period_end,source:[...new Set(cs.map(c=>c.source))].join(' / ')});}
  function periods(model,basis,cadence,table){
    const gs=(model?.groups||[]).filter(g=>g.basis===basis),q=gs.find(g=>g.cadence==='quarter')?.columns||[];
    const changed=q.map(c=>{const input=table?.groups?.find(g=>g.id===basis+'-quarter')?.columns.find(x=>x.period_end===c.period_end);return {...c,values:{...c.values,ebitda:input?.values.ebitda??c.values.ebitda}};});
    if(cadence==='quarter')return changed.map(enrich);
    const rolling=[];for(let i=3;i<changed.length;i++){const cs=changed.slice(i-3,i+1);if(consecutive(cs))rolling.push(sum(cs));}
    if(cadence==='ttm')return rolling;
    const annual=gs.find(g=>g.cadence==='annual')?.columns.map(c=>{const input=table?.groups?.find(g=>g.id===basis+'-annual')?.columns.find(x=>x.period_end===c.period_end);return enrich({...c,values:{...c.values,ebitda:input?.values.ebitda??c.values.ebitda}});})||[];
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
  return {num,ratio,consecutive,periods,aggregate,indicators,relative,eventList};
})();
if(typeof module!=='undefined')module.exports=CompanyDetailEngine;
