/* Completed-close context for comparison cards. No target prices or orders. */
'use strict';
const ComparisonPriceUI=(()=>{
 const num=v=>typeof v==='number'&&Number.isFinite(v),day=86400000;
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const fmt=(v,d=1)=>num(v)?v.toLocaleString('ko-KR',{maximumFractionDigits:d}):'—';
 const pct=v=>num(v)?(v>0?'+':'')+fmt(v)+'%':'미확보';
 const date=v=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v)&&Number.isFinite(Date.parse(v+'T00:00:00Z'))&&new Date(v+'T00:00:00Z').toISOString().slice(0,10)===v;
 function analyze(input,cutoff){
  if(!date(cutoff))return {status:'unavailable',reason:'가격 기준일 확인 필요',bars:[]};
  const selected=(input||[]).filter(p=>date(p.date)&&p.date<=cutoff);
  if(!selected.length)return {status:'unavailable',reason:'완료 종가 이력 미확보',bars:[]};
  if(selected.some(p=>!num(p.close)||p.close<=0||p.final===false)||new Set(selected.map(p=>p.date)).size!==selected.length)
   return {status:'unavailable',reason:'가격·중복 관측일 확인 필요',bars:[]};
  const bars=selected.map(p=>({...p})).sort((a,b)=>a.date.localeCompare(b.date)),totals=[0];
  for(const p of bars)totals.push(totals.at(-1)+p.close);
  bars.forEach((p,i)=>{for(const n of [50,200])p['ma'+n]=i+1>=n?(totals[i+1]-totals[i+1-n])/n:null;});
  const last=bars.at(-1),price=last.close,yearStart=new Date(Date.parse(last.date+'T00:00:00Z')-364*day).toISOString().slice(0,10);
  const year=bars.filter(p=>p.date>=yearStart),fullYear=bars[0].date<=yearStart&&year.length>=200,rangeBars=fullYear?year:bars;
  const low=Math.min(...rangeBars.map(p=>p.close)),high=Math.max(...rangeBars.map(p=>p.close));
  const gap=base=>num(base)&&base>0?(price/base-1)*100:null;
  const old200=bars.length>=221?bars.at(-22).ma200:null,rising=num(old200)&&last.ma200>old200;
  let label='장기 자료 확인',tone='neutral',setup='50·200일선이 함께 확보되면 추세상 부담을 비교할 수 있습니다.';
  if(last.no_trade===true||last.volume===0){label='거래 상태 확인';setup='마지막 관측일 거래가 없어 진입 여건 판단을 보류합니다.';}
  else if(num(last.ma200)&&num(old200)){
   if(price<last.ma200){label='추세 확인 우선';tone='caution';setup='200일선 아래입니다. 낮아진 가격과 추세 회복을 구분해 확인할 구간입니다.';}
   else if(price<last.ma50&&rising){label='상승 흐름 속 조정';setup='상승하는 200일선 위에서 50일선 아래로 조정 중입니다. 지지·회복 확인이 필요합니다.';}
   else if(price>=last.ma50&&last.ma50>last.ma200&&rising){
    if(gap(last.ma50)>10){label='추격 부담';tone='caution';setup='상승 흐름이지만 50일선과 거리가 큽니다. 추세가 강한 것과 진입 부담은 별개입니다.';}
    else if(gap(last.ma50)<=5){label='추세선 근접';tone='positive';setup='상승 정렬에서 50일선과 가까운 구간입니다. 이탈 없이 흐름이 유지되는지 확인할 만합니다.';}
    else {label='상승 흐름';tone='positive';setup='상승 정렬을 유지합니다. 가격 상승을 따라갈 때는 50일선과의 거리를 함께 보세요.';}
   }else {label='추세 혼재';setup='종가·50일선·200일선의 방향이 한쪽으로 정렬되지 않았습니다.';}
  }else if(num(last.ma50))setup=`50일선 ${price>=last.ma50?'위':'아래'}입니다. 200일선의 방향을 판단할 이력은 아직 부족합니다.`;
  return {status:'ready',bars,price,date:last.date,low,high,rangeLabel:fullYear?'52주 종가 범위':'저장 관측 범위',
   position:high>low?(price-low)/(high-low)*100:null,drawdown:gap(high),aboveLow:gap(low),
   ma50:last.ma50,ma200:last.ma200,gap50:gap(last.ma50),gap200:gap(last.ma200),label,tone,setup};
 }
 function valuation(items){
  const known=v=>typeof v==='string'&&v.trim()&&!/unknown|unverified|미확인|미명시|대기/i.test(v);
  const raw=items.filter(i=>num(i.value)).map(i=>`${i.key.toUpperCase()} ${fmt(i.value,2)}배`).join(' · ');
  const usable=items.filter(i=>i.value>0&&num(i.median)&&i.median>0&&i.count>=5&&known(i.period)&&known(i.basis)&&date(i.price_date));
  if(!usable.length)return {label:'가치 비교 대기',text:(raw?raw+' · ':'')+'동일 기준의 동종업계 비교자료가 부족해 저평가 여부는 보류합니다.'};
  const lower=usable.every(i=>i.value<i.median),higher=usable.every(i=>i.value>i.median);
  const label=usable.length<2?'일부 배수만 비교 가능':lower?'상대 배수 낮음':higher?'상대 배수 높은 편':'배수 신호 혼재';
  return {label,text:usable.map(i=>`${i.key.toUpperCase()} ${fmt(i.value,2)}배 / 업종 중앙 ${fmt(i.median,2)}배 (${i.count}개)`).join(' · ')+(lower?' · 성장·수익성까지 확인해야 가격 매력을 판단할 수 있습니다.':' · 배수 차이의 원인을 실적·성장 기대와 함께 확인하세요.')};
 }
 function plot(model,range){
  const ps=model.bars.slice(-range),values=ps.flatMap(p=>[p.close,p.ma50,p.ma200].filter(num));
  const lo0=Math.min(...values),hi0=Math.max(...values),pad=(hi0-lo0)*.08||hi0*.02,lo=Math.max(0,lo0-pad),hi=hi0+pad;
  const start=Date.parse(ps[0].date),span=Date.parse(ps.at(-1).date)-start||1,x=p=>64+(ps.length===1?.5:(Date.parse(p.date)-start)/span)*440,y=v=>190-(v-lo)/(hi-lo)*151;
  const path=k=>{let begun=false;return ps.map(p=>{if(!num(p[k])){begun=false;return '';}const d=(begun?'L':'M')+x(p)+','+y(p[k]);begun=true;return d;}).join(' ');};
  const lines=[['close','종가','#245ca6'],['ma50','50일선','#16836a'],['ma200','200일선','#8e52a3']];
  const svg=`<svg viewBox="0 0 560 232" role="img" aria-label="완료 종가와 50·200일 이동평균"><title>${esc(model.date)} · 종가 ${fmt(model.price,0)}원 · ${ps.length}개 관측</title>${lines.map(([key,label,color],i)=>`<text x="${64+i*145}" y="19" fill="${color}">${label}${key!=='close'&&!num(model[key])?' 대기':''}</text>`).join('')}${[lo,(lo+hi)/2,hi].map(v=>`<line x1="64" x2="504" y1="${y(v)}" y2="${y(v)}" stroke="#d1dae5"/><text x="57" y="${y(v)+4}" text-anchor="end">${fmt(v/10000,1)}</text>`).join('')}<text x="10" y="19">만원</text>${lines.map(([k,,c])=>`<path data-cp-series="${k}" d="${path(k)}" fill="none" stroke="${c}" stroke-width="${k==='close'?2.5:1.5}"/>`).join('')}<line data-cp-guide x1="${x(ps.at(-1))}" x2="${x(ps.at(-1))}" y1="38" y2="190" stroke="#738399" stroke-dasharray="3 3"/><circle data-cp-dot cx="${x(ps.at(-1))}" cy="${y(model.price)}" r="4" fill="#245ca6"/><text x="64" y="218">${esc(ps[0].date)}</text><text x="504" y="218" text-anchor="end">${esc(ps.at(-1).date)}</text><rect data-cp-hit x="64" y="38" width="440" height="152" fill="transparent" tabindex="0" role="slider" aria-label="관측일별 가격 · 좌우 방향키로 이동" aria-valuemin="0" aria-valuemax="${ps.length-1}" aria-valuenow="${ps.length-1}"/></svg>`;
  return {svg,ps,x,y};
 }
 function card(row,model,value,range,source,details){
  if(model.status!=='ready')return `<article class="cp-card" data-cp-card="${esc(row.code)}"><h4>${esc(row.name)}</h4><p>${esc(model.reason)}</p></article>`;
  const chart=plot(model,range);
  return `<article class="cp-card" data-cp-card="${esc(row.code)}"><div class="cp-heading"><h4>${esc(row.name)}</h4><span class="cp-badge ${model.tone}">${esc(model.label)}</span></div><div class="cp-current"><strong>${fmt(model.price,0)}<small>원</small></strong><span>완료 종가 · ${esc(model.date)}</span></div>${chart.svg}<p class="cp-hover" role="status">${esc(model.date)} · 종가 ${fmt(model.price,0)}원</p><div class="cp-range" aria-label="${esc(model.rangeLabel)}"><div><span>${model.rangeLabel} · ${fmt(model.low,0)}원</span><span>${fmt(model.high,0)}원</span></div><div class="cp-range-track">${num(model.position)?`<i style="left:${Math.max(0,Math.min(100,model.position))}%" title="범위 내 ${fmt(model.position)}%"></i>`:''}</div></div><div class="cp-stats"><span>고점 대비 <b>${pct(model.drawdown)}</b></span><span>50일선 거리 <b>${pct(model.gap50)}</b></span><span>저점 대비 <b>${pct(model.aboveLow)}</b></span><span>200일선 거리 <b>${pct(model.gap200)}</b></span></div><p class="cp-setup">${esc(model.setup)}</p><div class="cp-value"><b>가치 매력 · ${esc(value.label)}</b><p>${esc(value.text)}</p></div><button class="link" data-comparison-analysis="${esc(row.code)}">기업 분석에서 근거 확인 →</button><details class="cp-method"><summary>자료·계산 기준</summary><p>${esc(source||'저장된 일별 가격')} · ${model.bars.length}개 관측 · 선형 원화 가격·개별 축. 범위 변경은 차트 표시만 바꾸며 요약은 전체 저장 이력으로 계산합니다.</p><p>52주 범위는 마지막 종가일에서 364일 전까지, 과거 이력과 200개 이상 관측이 있는 경우에만 표시합니다. 고가/저가가 아닌 종가 범위입니다. 선이 없는 구간의 이동평균은 미확보입니다.</p><p>50일선 대비 +5% 이내/10% 초과는 화면 설명용 구간입니다. 추세선 근접·조정은 매수 신호나 저평가 판정이 아닙니다.</p><p>${esc(details)}</p><p><a href="https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/sma" target="_blank" rel="noopener">이동평균 설명</a> · <a href="https://www.investor.gov/introduction-investing/investing-basics/glossary/priceearnings-ratio" target="_blank" rel="noopener">PER 설명</a></p></details></article>`;
 }
 function bind(element,models,range){
  for(const [code,model]of models){
   const host=[...element.querySelectorAll('[data-cp-card]')].find(el=>el.dataset.cpCard===code);
   if(!host||model.status!=='ready')continue;
   const {ps,x,y}=plot(model,range),svg=host.querySelector('svg'),hit=host.querySelector('[data-cp-hit]');let index=ps.length-1;
   const show=i=>{index=Math.max(0,Math.min(ps.length-1,i));const p=ps[index];host.querySelector('.cp-hover').textContent=`${p.date} · 종가 ${fmt(p.close,0)}원 · 50일선 ${fmt(p.ma50,0)} · 200일선 ${fmt(p.ma200,0)}`;for(const key of ['x1','x2'])host.querySelector('[data-cp-guide]').setAttribute(key,x(p));host.querySelector('[data-cp-dot]').setAttribute('cx',x(p));host.querySelector('[data-cp-dot]').setAttribute('cy',y(p.close));hit.setAttribute('aria-valuenow',index);hit.setAttribute('aria-valuetext',p.date+' 종가 '+fmt(p.close,0)+'원');};
   hit.onpointermove=e=>{const box=svg.getBoundingClientRect(),px=(e.clientX-box.left)/box.width*560;let best=0;ps.forEach((p,i)=>{if(Math.abs(x(p)-px)<Math.abs(x(ps[best])-px))best=i;});show(best);};
   hit.onpointerleave=()=>show(ps.length-1);hit.onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();show(e.key==='Home'?0:e.key==='End'?ps.length-1:index+(e.key==='ArrowLeft'?-1:1));}};
  }
 }
 return {analyze,valuation,card,bind};
})();
if(typeof module!=='undefined')module.exports=ComparisonPriceUI;
