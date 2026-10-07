'use strict';
const TrendChangesUI=(()=>{
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const identity=r=>[r.market,r.code,r.name].join('|');
 const num=v=>typeof v==='number'&&Number.isFinite(v);
 function observation(row,asOf){const ready=!!row&&row.ready===true&&row.technical?.as_of===asOf;return {identity:row?[row.market,row.code,row.name]:null,ready,rs:ready&&num(row.rs)?row.rs:null,qualified:ready&&row.discovery_allowed!==false&&num(row.cap_eok)&&row.cap_eok>=1000&&num(row.rs)&&row.rs>=70,phase:ready?row.phase:'현재 자료 대기',ma_fail:ready&&num(row.technical?.sma?.['50'])?row.technical.close<row.technical.sma['50']:null};}
 function renderChanges(data={}){
  const c=data.changes||{},prior=c.status==='ready';
  const groups=[['new_qualified','새로 기본 조건 충족'],['dropouts','기본 조건 이탈'],['near','돌파선 3% 이내'],['breakouts','20일 최고종가 돌파'],['ma_fail','50일선 아래'],['pending','자료·대상 변경 확인']];
  return `<section class="panel tf-changes" aria-label="관측 후보 변화"><h3>관측 후보 변화</h3><p>${esc(c.prior_as_of||'이전 체크포인트 없음')} → ${esc(data.as_of)} · ${esc(c.comparison||'신규/이탈 판정 대기')}${c.revision?' · 수정본 '+esc(c.revision):''}</p><p class="psub">시총 1,000억원 이상·RS70의 고정 기본 조건. 현재 검색·정렬 필터와 별도 · ${esc(c.observed_at||'아직 저장되지 않은 조회')}</p><div class="tf-change-grid">${groups.map(([key,label])=>{const list=c[key]||[];return `<details ${list.length?'open':''}><summary>${label} · ${!prior&&['new_qualified','dropouts'].includes(key)?'비교 대기':list.length+'개'}</summary><div class="tf-change-list">${list.map(r=>`<button type="button" data-tfc-go="${esc(r.code)}"><b>${esc(r.name)}</b><small>${esc(r.market)} · ${esc(r.code)} · 당시 RS ${num(r.rs)?r.rs.toFixed(1):'—'}${r.newly_observed===true?' · 이번 관측 새 확인':''}${key==='breakouts'?' · '+(r.volume_confirmed?'거래량 동반':'거래량 보강/확인 필요'):''}${r.reason?' · '+esc(r.reason):''}</small></button>`).join('')||'<p class="psub">'+(!prior&&['new_qualified','dropouts'].includes(key)?'과거 관측이 없어 전일 사실을 추정하지 않습니다.':'해당 관측 없음')+'</p>'}</div></details>`;}).join('')}</div><p class="psub">${esc(c.note||'작성 당시 관측 비교 · 백테스트 아님')}${c.unreadable_records?' · 읽을 수 없는 기존 기록 '+esc(c.unreadable_records)+'개 제외':''}</p></section>`;
 }
 function create({data,go=()=>{},refresh=()=>{}}){
  const key='investment-trend-watch-v1-'+(data.mode||'unknown');let saved={version:1,identities:[],checkpoints:[]},message='';
  try{const v=JSON.parse(localStorage.getItem(key)||'null');if(v?.version===1&&Array.isArray(v.identities)&&Array.isArray(v.checkpoints))saved=v;}catch{}
  function persist(){try{localStorage.setItem(key,JSON.stringify(saved));message='이 브라우저에 저장됨';}catch{message='브라우저 저장 불가 · 현재 화면만 유지';}}
  function isWatched(row){return saved.identities.some(i=>i.join('|')===identity(row));}
  function toggle(row){if(isWatched(row))saved.identities=saved.identities.filter(i=>i.join('|')!==identity(row));else saved.identities.push([row.market,row.code,row.name]);persist();refresh();}
  function checkpoint(){
   const rows=saved.identities.map(i=>{const row=(data.rows||[]).find(r=>identity(r)===i.join('|'));return row?observation(row,data.as_of):{identity:i,ready:false,qualified:false,rs:null,phase:'현재 관찰 대상에 없음',ma_fail:null};});
   const body=JSON.stringify({as_of:data.as_of,rows}),last=saved.checkpoints.at(-1);
   if(!last||last.fingerprint!==body)saved.checkpoints.push({as_of:data.as_of,observed_at:new Date().toISOString(),revision:saved.checkpoints.filter(c=>c.as_of===data.as_of).length+1,rows,fingerprint:body});
   persist();refresh();
  }
  function render(){const latest=saved.checkpoints.at(-1);return renderChanges(data)+`<section class="panel tf-watch" aria-label="관심종목 체크포인트"><div class="panel-heading"><h3>관심종목 · ${saved.identities.length}개</h3><button type="button" id="tfWatchCheckpoint" ${saved.identities.length?'':'disabled'}>현재 점검 저장</button></div><p class="psub">이 브라우저 로컬 기록 · 사용자가 저장한 당시 점검 · 백테스트 아님. 후보 기본 조건과 화면 필터는 관심목록을 바꾸지 않습니다.</p><p role="status">${esc(message)}</p><div class="tf-watch-grid">${saved.identities.map(i=>{const r=(data.rows||[]).find(r=>identity(r)===i.join('|')),now=r?observation(r,data.as_of):null,prior=latest?.rows?.find(p=>p.identity?.join('|')===i.join('|'));return `<div><b>${esc(i[2])}</b><small>${esc(i[0])} · ${esc(i[1])} · ${esc(data.as_of)} ${esc(now?.phase||'현재 자료·대상 확인 대기')}</small><small>${latest?'직전 저장 '+esc(latest.as_of)+' · 수정본 '+esc(latest.revision)+' · '+esc(prior?.phase||'당시 관심목록에 없음'):'이전 관심 체크포인트 없음'}</small><button type="button" data-tfw-remove="${esc(i.join('|'))}">관심 해제</button></div>`;}).join('')||'<p class="psub">종목 카드의 관심 추가로 관찰 대상을 고르세요.</p>'}</div><details><summary>저장된 관심 점검 ${saved.checkpoints.length}회</summary>${saved.checkpoints.slice().reverse().map(c=>`<p>${esc(c.as_of)} · 수정본 ${esc(c.revision)} · ${esc(c.observed_at)} · ${c.rows.length}개 · 기본 조건 ${c.rows.filter(r=>r.qualified).length}개 충족 · 50일선 아래 ${c.rows.filter(r=>r.ma_fail===true).length}개 · 자료 대기 ${c.rows.filter(r=>!r.ready).length}개</p>`).join('')||'<p>저장 기록 없음</p>'}</details></section>`;}
  function bind(element){element.querySelectorAll('[data-tfc-go]').forEach(b=>b.onclick=()=>go('trend',b.dataset.tfcGo));element.querySelector('#tfWatchCheckpoint')?.addEventListener('click',checkpoint);element.querySelectorAll('[data-tfw-remove]').forEach(b=>b.onclick=()=>{saved.identities=saved.identities.filter(i=>i.join('|')!==b.dataset.tfwRemove);persist();refresh();});element.querySelectorAll('[data-tf-watch]').forEach(b=>b.onclick=()=>{const r=(data.rows||[]).find(r=>r.code===b.dataset.tfWatch);if(r)toggle(r);});}
  return {render,bind,isWatched,checkpoint};
 }
 return {renderChanges,observation,create};
})();
if(typeof module!=='undefined')module.exports=TrendChangesUI;
