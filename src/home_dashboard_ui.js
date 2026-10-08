'use strict';
// Home dashboard pieces for the soft UI layout. Values come from stored payloads only.
const HomeDashboardUI=(()=>{
 const num=v=>typeof v==='number'&&Number.isFinite(v),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),fmt=(v,d=1)=>num(v)?v.toLocaleString('ko-KR',{maximumFractionDigits:d}):'—';
 const MARKETS=['KOSPI','KOSDAQ'],JOSA={KOSPI:'는',KOSDAQ:'은'};
 const HEADLINES={narrow:'지수는 오르는데, 따라 오르는 기업은 적습니다',weak:'지수와 기업 참여가 함께 약합니다',resilient:'지수는 약하지만 기업 참여는 유지됩니다',mixed:'지수 방향이 뚜렷하지 않은 혼조 구간입니다',strong:'지수와 기업 참여가 함께 강합니다'};
 const PRIORITY=['narrow','weak','resilient','mixed','strong'];
 const breadthPct=m=>m?.breadth?.above?.['200']?.pct;
 const ready=m=>m?.index?.status==='ready'&&num(breadthPct(m));
 function pattern(m){const up=m.index.label==='상승 정렬',down=m.index.label==='하락 정렬',wide=breadthPct(m)>=50;return up&&!wide?'narrow':down&&!wide?'weak':down?'resilient':up?'strong':'mixed';}
 function topSector(insights){return (insights?.sectors||[]).filter(s=>num(s.short_rs?.['1m']?.score)).sort((a,b)=>b.short_rs['1m'].score-a.short_rs['1m'].score||a.industry.localeCompare(b.industry))[0];}
 function verdict(explanation,insights){
  const byName=Object.fromEntries((explanation?.markets||[]).map(m=>[m.market,m])),shown=MARKETS.map(n=>byName[n]||{market:n}),usable=shown.filter(ready);
  const found=PRIORITY.find(p=>usable.some(m=>pattern(m)===p)&&(p!=='strong'||usable.every(m=>pattern(m)==='strong')));
  const lines=shown.map(m=>ready(m)?`${m.market}${JOSA[m.market]||'은(는)'} ${m.index.label} · 200일선 위 기업 ${fmt(breadthPct(m))}% · 상승 ${m.breadth.advancing??'—'} / 하락 ${m.breadth.declining??'—'}`:`${m.market} 판단 자료 대기`);
  const vols=shown.filter(m=>num(m.volatility?.annual20_pct)),top=topSector(insights);
  const label=vols.find(m=>m.volatility.label)?.volatility.label;
  lines.push(vols.length?`변동성 ${vols.map(m=>`${m.market} ${fmt(m.volatility.annual20_pct)}%`).join(' · ')}${label?` (${label})`:''}${top?` · 1개월 RS 최상위 업종 ${top.industry}(${top.market})`:''}`:'변동성 자료 대기');
  return {headline:usable.length?HEADLINES[found]:'시장 판단 자료 대기',lines,as_of:explanation?.as_of||null};
 }
 // 11-A scale: weaker tiles cool teal, stronger tiles warm coral, neutral in the middle.
 function tileColor(t){const w=t>=.5?(t-.5)*2:0,c=t<.5?(.5-t)*2:0;return w>0?`hsl(352,${Math.round(20+w*65)}%,${Math.round(95-w*13)}%)`:`hsl(188,${Math.round(20+c*45)}%,${Math.round(95-c*8)}%)`;}
 function sectorTiles(insights,limit=8){
  const all=insights?.sectors||[],total=all.reduce((a,s)=>a+(s.short_rs?.['1m']?.cap_eok||0),0);
  const top=all.filter(s=>num(s.short_rs?.['1m']?.score)).sort((a,b)=>b.short_rs['1m'].score-a.short_rs['1m'].score||a.industry.localeCompare(b.industry)).slice(0,limit);
  const rets=top.map(s=>s.short_rs['1m'].return_pct).filter(num),lo=Math.min(...rets),hi=Math.max(...rets);
  return top.map(s=>{const x=s.short_rs['1m'],t=!num(x.return_pct)||hi===lo?.5:(x.return_pct-lo)/(hi-lo);return {industry:s.industry,market:s.market,count:x.count??s.count,ret:x.return_pct,rs:x.score,share:total?(x.cap_eok||0)/total*100:0,t,bg:tileColor(t),fg:'#2a2f3a'};});
 }
 function candidates(rows,research,sel,limit=5){
  if(!sel)return [];
  const tech=r=>research?.rows?.[r.code]?.technical||{},score=r=>tech(r).short_rs?.['1m']?.score;
  const trend=s=>s==='pass'?'가격 추세 충족':s==='fail'?'추세 미충족':'추세 판정 대기';
  return (rows||[]).filter(r=>r.market===sel.market&&r.industry===sel.industry&&r.discovery_allowed!==false&&num(score(r)))
   .sort((a,b)=>score(b)-score(a)||a.code.localeCompare(b.code)).slice(0,limit)
   .map(r=>({code:r.code,name:r.name||r.code,rs:score(r),ret:tech(r).short_rs['1m'].return_pct,trend:trend(tech(r).price_trend_status)}));
 }
 function verdictPanel(v){return `<p class="home-kicker">오늘의 결론 · 종가 ${esc(v.as_of||'기준일 대기')}</p><h2>${esc(v.headline)}</h2><ol class="home-points">${v.lines.map(l=>`<li>${esc(l)}</li>`).join('')}</ol><p class="psub">규칙 기반 요약 · 지수 방향 / 200일선 위 기업 비율 / 변동성. 매매 신호가 아닙니다.</p>`;}
 function signalRows(m){if(!ready(m))return '<div class="home-signal"><span>시장 신호</span><b>자료 대기</b></div>';const v=m.volatility||{};return `<div class="home-signal"><span>방향</span><b class="${m.index.label==='상승 정렬'?'up':m.index.label==='하락 정렬'?'down':''}">${esc(m.index.label)}</b></div><div class="home-signal"><span>참여 · 200일선 위 ${fmt(breadthPct(m))}%</span><b class="${breadthPct(m)>=50?'':'warn'}">${esc(m.breadth.label)}</b></div><div class="home-signal"><span>변동성 · 이전 ${fmt(v.prior20_pct)}%</span><b>${fmt(v.annual20_pct)}%</b></div>`;}
 function detail(m){if(!m?.explanation)return '';return `<details class="home-market-detail"><summary>해석·판정 기준</summary><p>${esc(m.explanation)}</p><p>${esc(m.index?.definition)}</p><p>${esc(m.breadth?.definition)}</p><p>${esc(m.volatility?.definition)}</p><p>${esc(m.source_note)}</p><p>${esc(m.verification)}</p></details>`;}
 function marketCards(trend,explanation,summary,miniChart){
  const byName=Object.fromEntries((explanation?.markets||[]).map(m=>[m.market,m])),series=Object.fromEntries((trend?.markets||[]).filter(m=>m.series?.length&&m.series.at(-1).date===trend.as_of).map(m=>[m.market,m])),closes=Object.fromEntries((summary||[]).map(r=>[r.market,r]));
  return MARKETS.map(name=>{const s=series[name],c=closes[name],close=s?.close??c?.close,chg=s?.change_pct??c?.change_pct,day=s?trend.as_of:c?.date;
   const chart=s&&miniChart?miniChart(s.series,{market:true,label:name+' 지수와 이동평균'}):'<p class="home-chart-empty">같은 기준일의 완료 가격 그래프 연결 대기</p>';
   return `<article class="panel home-market"><div class="panel-heading"><h3>${name}</h3><button data-go="trend-following">추세추종 →</button></div><p class="home-price"><strong>${fmt(close,2)}</strong> ${num(chg)?`<span class="${chg>0?'up':chg<0?'down':''}">${chg>0?'+':''}${fmt(chg,2)}%</span>`:''}<small>${esc(day||'관측일 대기')} · 전 관측일 대비</small></p>${signalRows(byName[name])}${chart}${detail(byName[name])}</article>`;}).join('');
 }
 function sectorMap(tiles,selected){
  if(!tiles.length)return '<p class="psub">같은 시장 유효기업 5개 이상인 업종의 완료 가격 자료 대기</p>';
  const rets=tiles.map(t=>t.ret).filter(num);
  return `<div class="home-tiles">${tiles.map((t,i)=>`<button class="home-tile" data-home-tile="${i}" aria-pressed="${i===selected}" style="flex:${Math.max(1,t.count||1)} 1 ${Math.max(130,(t.count||1)*2.6)}px;background-color:${esc(t.bg)};color:${esc(t.fg)}"><small>${esc(t.market)} · ${fmt(t.count,0)}개</small><span class="home-tile-name">${esc(t.industry)}</span><span><b>${num(t.ret)&&t.ret>0?'+':''}${fmt(t.ret)}%</b><small>RS ${fmt(t.rs)} · 시총 ${fmt(t.share)}%</small></span></button>`).join('')}</div><div class="home-scale"><span>${fmt(Math.min(...rets))}%</span><i></i><span>${fmt(Math.max(...rets))}%</span> · 표시 업종 안의 상대 비교 · 타일을 누르면 오른쪽 후보가 바뀝니다</div>`;
 }
 function candidatesPanel(sel,list){
  if(!sel)return '<h3>업종 후보</h3><p class="psub">왼쪽 섹터 맵에서 업종을 선택하세요.</p>';
  return `<div class="panel-heading"><h3>${esc(sel.industry)} 후보 <small>${esc(sel.market)}</small></h3><button class="link" data-sector-search="${esc(sel.industry)}" data-sector-market="${esc(sel.market)}">조건검색 →</button></div>${list.length?`<table class="home-candidates"><thead><tr><th>기업</th><th>RS</th><th>1개월</th></tr></thead><tbody>${list.map(c=>`<tr><td><button class="link" data-home-code="${esc(c.code)}">${esc(c.name)}</button><span class="home-tag">${esc(c.trend)}</span></td><td>${fmt(c.rs,0)}</td><td class="${c.ret>0?'up':c.ret<0?'down':''}">${num(c.ret)&&c.ret>0?'+':''}${fmt(c.ret)}%</td></tr>`).join('')}</tbody></table>`:'<p class="psub">같은 업종의 RS 산출 기업이 없습니다.</p>'}<p class="psub">1개월 RS 내림차순 최대 5개 · 발굴 범위(시총 1,500억원 초과) 안의 기업 · 투자 추천이 아닙니다.</p>`;
 }
 const DONUT=['#e0506a','#f4a3b0','#2a9fae','#8fd0d8','#ff9aaa','#c9d2dc'];
 function donut(parts){const r=40,c=2*Math.PI*r;let off=0;return `<svg class="home-donut" viewBox="0 0 100 100" width="96" height="96" role="img" aria-label="추천 비중">${parts.map((w,i)=>{const len=c*w/100,el=`<circle r="${r}" cx="50" cy="50" fill="none" stroke="${DONUT[i%DONUT.length]}" stroke-width="13" stroke-dasharray="${Math.max(0,len-1.5)} ${c-Math.max(0,len-1.5)}" stroke-dashoffset="${-off}" transform="rotate(-90 50 50)"/>`;off+=len;return el;}).join('')}</svg>`;}
 function recommendation(r){
  if(!r)return '이번 달 추천안 작성 대기';
  const ws=[...r.targets.map(t=>num(t.weight_pct)?t.weight_pct:0),num(r.cash_pct)?r.cash_pct:0];
  return `<p>${esc(r.month)} · ${esc(r.review_status)}</p><div class="home-rec">${donut(ws)}<div class="recommendation-preview">${r.targets.map((t,i)=>`<button data-home-rec-code="${esc(t.code)}"><i style="background:${DONUT[i%DONUT.length]}"></i>${esc(t.name)} <b>${fmt(t.weight_pct)}%</b></button>`).join('')}<span><i style="background:${DONUT[5]}"></i>현금 <b>${fmt(r.cash_pct)}%</b></span></div></div>`;
 }
 function kpis({universe,cash,watched,pending}){return [['탐색 범위',fmt(universe,0),'개'],['추천 현금',num(cash)?fmt(cash):'—',num(cash)?'%':''],['관심 기업',fmt(watched,0),'개'],['확인 필요',fmt(pending,0),'개']].map(([k,v,u])=>`<span>${k} <b>${v}</b>${u}</span>`).join('');}
 return {verdict,tileColor,sectorTiles,candidates,verdictPanel,marketCards,sectorMap,candidatesPanel,recommendation,kpis};
})();
if(typeof module!=='undefined')module.exports=HomeDashboardUI;
