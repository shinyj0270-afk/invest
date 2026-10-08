'use strict';
// Morning brief per holding: only important changes, impact, judgment change, risks and basis. Read-only.
const HoldingsBrief=(()=>{
 const num=v=>typeof v==='number'&&Number.isFinite(v),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),fmt=(v,d=1)=>num(v)?v.toLocaleString('ko-KR',{maximumFractionDigits:d}):'—';
 const signed=(v,d=1)=>(v>0?'+':'')+v.toFixed(d);
 // Thresholds for "important": larger moves only, to keep the brief short.
 const PRICE_MOVE_PCT=3,RS_MOVE=5;
 function snapshot(it){const t=it.technical||{},ma=t.sma?.['200'];return {day:t.as_of||null,close:num(t.close)?t.close:null,rs:t.short_rs?.['1m']?.score??null,trend:t.price_trend_status||null,below200:num(t.close)&&num(ma)?t.close<ma:null,period:it.common?.period||null,opinion:it.label||null};}
 function rollover(store,snap){
  if(!store?.current)return {prior:null,next:{current:snap,previous:null}};
  if(snap.day&&store.current.day&&store.current.day<snap.day)return {prior:store.current,next:{current:snap,previous:store.current}};
  return {prior:store.previous||null,next:{current:snap,previous:store.previous||null}};
 }
 function changes(cur,prior){
  if(!prior)return ['첫 관측 · 다음 완료 종가부터 비교'];
  const out=[];
  if(prior.day&&cur.day&&cur.day>prior.day&&num(cur.close)&&num(prior.close)&&prior.close>0){const pct=(cur.close/prior.close-1)*100;if(Math.abs(pct)>=PRICE_MOVE_PCT)out.push(`종가 ${signed(pct)}% (${prior.day} → ${cur.day})`);}
  if(num(cur.rs)&&num(prior.rs)&&Math.abs(cur.rs-prior.rs)>=RS_MOVE)out.push(`1개월 RS ${fmt(prior.rs,0)} → ${fmt(cur.rs,0)}`);
  if(['pass','fail'].includes(prior.trend)&&['pass','fail'].includes(cur.trend)&&prior.trend!==cur.trend)out.push(cur.trend==='pass'?'가격 추세 충족으로 전환':'가격 추세 이탈');
  if(typeof prior.below200==='boolean'&&typeof cur.below200==='boolean'&&prior.below200!==cur.below200)out.push(cur.below200?'200일선 하향 이탈':'200일선 상향 돌파');
  return out;
 }
 function impact(it,cur,prior){
  const out=[],m=it.common?.metrics||{},h=it.health||{};
  if(prior?.period&&cur.period&&cur.period>prior.period)out.push(`새 재무 ${cur.period} 반영 · 매출 증가율 ${fmt(m.revenue_growth_pct)}% · 영업이익률 ${fmt(m.operating_margin_pct)}%`);
  if(h.decision==='material_revision'&&h.decision_on&&(!prior?.day||h.decision_on>=prior.day))out.push(`중요 정정 ${h.material_changes||0}개 계정 반영 (${h.decision_on})`);
  return out;
 }
 function risks(it,cur){
  const out=(it.thesis?.conditions||[]).filter(c=>c.status==='triggered'&&c.role!=='context').map(c=>'붕괴 조건 충족: '+(c.text||c.label));
  if(it.verification?.status==='review')out.push('분석 검증 '+it.verification.label);
  if(cur.below200===true)out.push('200일선 아래');
  return out;
 }
 function brief(it,prior,now){
  const cur=snapshot(it),c=changes(cur,prior),i=impact(it,cur,prior),r=risks(it,cur);
  const judgment=!prior?{kind:'first',before:null,after:cur.opinion}:{kind:prior.opinion===cur.opinion?'unchanged':'changed',before:prior.opinion,after:cur.opinion};
  const basis=`종가 ${cur.day||'미확인'} · 재무 ${cur.period||'미확인'} ${it.common?.basis||''}`.trim()+` · 확인 ${now.time}`;
  return {code:it.code,name:it.name||it.code,changes:c,impact:i,judgment,reasons:it.reasons||[],risks:r,basis,thesis:it.thesis?.action||null,
   quiet:!!prior&&!c.length&&!i.length&&judgment.kind==='unchanged'&&!r.length};
 }
 function line(label,items,tone=''){return items.length?`<p class="brief-line ${tone}"><b>${label}</b> ${items.map(esc).join(' · ')}</p>`:'';}
 function render(briefs){
  if(!briefs.length)return '<p class="home-empty">직접 입력한 보유종목이 없습니다.</p>';
  return briefs.map(b=>`<article class="brief-item"><button class="home-company" data-home-code="${esc(b.code)}"><span><b>${esc(b.name)}</b><small>${esc(b.code)}</small></span><span class="brief-opinion">${esc(b.judgment.after||'판단 대기')}</span></button>${b.quiet?'<p class="brief-line quiet">변경 없음</p>':line('변화',b.changes)+line('영향',b.impact)+(b.judgment.kind==='changed'?`<p class="brief-line warn"><b>판단 변경</b> ${esc(b.judgment.before)} → ${esc(b.judgment.after)}${b.reasons.length?' · '+b.reasons.map(esc).join(' · '):''}</p>`:'')+line('위험',b.risks,'bad')}<p class="brief-basis">${esc(b.basis)}${b.thesis?' · 투자 논리 '+esc(b.thesis):''}</p></article>`).join('');
 }
 return {snapshot,rollover,brief,render,PRICE_MOVE_PCT,RS_MOVE};
})();
if(typeof module!=='undefined')module.exports=HoldingsBrief;
