'use strict';
// Displays the server-side verification summary. Never recomputes or changes stored values.
const VerificationUI=(()=>{
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const TONE={pass:'ok',conditional:'warn',review:'bad'};
 function badge(v){return v?`<span class="verify-badge ${TONE[v.status]||''}">${esc(v.label)}</span>`:'<span class="verify-badge">검증 대기</span>';}
 function panel(v){
  if(!v)return '<details class="panel below verify-panel"><summary>분석 검증 · 검증 대기</summary><p class="psub">이 기업의 검증 결과가 아직 없습니다.</p></details>';
  const issues=v.issues||[];
  return `<details class="panel below verify-panel"${v.status==='pass'?'':' open'}><summary>분석 검증 ${badge(v)}</summary>${issues.length?`<ul class="verify-issues">${issues.map(([,label,detail,status])=>`<li class="${TONE[status]||''}"><b>${esc(label)}</b> ${esc(detail)}</li>`).join('')}</ul>`:'<p class="psub">출처·기준일, 단위, 재검산, 연결/별도, 근사값, 누락 항목 모두 통과.</p>'}<p class="psub">검증 기준일 ${esc(v.as_of)} · 재검토 필요는 계산 오류와 자료 부족을 구분합니다. 수치를 고치지 않고 상태만 표시합니다.</p></details>`;
 }
 return {badge,panel};
})();
if(typeof module!=='undefined')module.exports=VerificationUI;
