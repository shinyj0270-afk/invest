'use strict';
const RiskReviewUI = (() => {
  const esc = s => String(s ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = v => typeof v==='number' && Number.isFinite(v) ? v.toLocaleString('ko-KR',{maximumFractionDigits:2}) : '—';
  const flags={concentration_increased:'집중도 증가',volatility_higher:'같은 기간 변동성 상승',drawdown_deeper:'같은 기간 과거 낙폭 확대',missing_price:'공통 가격 자료 대기',unknown_industry:'산업 미확인'};
  function comparison(review) {
    if(!review)return '<p>구성 변경 위험 비교 대기</p>';
    const policy=review.policy||{},limits=policy.limits||{};
    const policyLine=review.policy_status==='not_configured'?'개인 위험 정책 미설정':review.policy_status==='pending'?'구성 한도 근거·효력일 확인 대기':`사용자 확인 구성 한도: 최대 ${fmt(limits.max_positions)}종목 · 종목당 ${fmt(limits.max_position_pct)}% · 현금 최소 ${fmt(limits.min_cash_pct)}% · ${review.policy_status==='violated'?'한도 검토 필요':'한도 이내'}`;
    const window=review.window;
    let html=`<p>${esc(policyLine)}</p><p class="psub">${esc(policy.provenance||'변동성·낙폭의 개인 허용 한도는 별도로 확정하지 않았습니다.')}${policy.effective_on?' · 효력 '+esc(policy.effective_on):''}</p>`;
    if(window)html+=`<p>동일 관측기간 ${esc(window.start_date)} → ${esc(window.as_of)} · ${fmt(window.observations)}개 일별 수익률</p>`;
    if(review.status!=='ready')html+=`<p class="financial-empty">비교 대기: ${esc(review.reason||'같은 기간 가격 자료 미확보')} · 위험 차이를 계산하거나 순위를 정하지 않습니다.</p>`;
    else {
      const metric=(r,k)=>r?.status==='cash_only'?0:r?.[k];
      html+='<div class="risk-review-scroll"><table><thead><tr><th>같은 기간 과거 위험</th><th>이전 구성</th><th>검토 구성</th><th>차이</th></tr></thead><tbody>';
      for(const [key,label] of [['annual_volatility_pct','연율 변동성 (%)'],['max_drawdown_pct','최대 낙폭 (%)']])html+=`<tr><th>${label}</th><td>${fmt(metric(review.previous,key))}</td><td>${fmt(metric(review.proposed,key))}</td><td>${fmt(review.deltas?.[key])} %p</td></tr>`;
      html+='</tbody></table></div>';
    }
    const warnings=(review.flags||[]).map(f=>flags[f]||f);
    if(warnings.length)html+=`<p class="risk-review-flags">추가 검토: ${warnings.map(esc).join(' · ')}</p>`;
    return html;
  }
  function render(payload) {
    if(!payload)return '';
    const review=payload.risk_review||payload;
    let html='<section class="risk-review"><h3>구성 변경 위험 검토</h3>'+comparison(review);
    if(payload.allocation)html+=`<p class="psub">${esc(payload.allocation.method)} · ${esc(payload.allocation.reason)} · 가격 확인 대기 후보 ${fmt(payload.allocation.risk_unavailable_candidates?.length||0)}개</p>`;
    if(payload.alternatives?.length)html+='<details><summary>작성 당시 조건을 통과한 교체 대안</summary>'+payload.alternatives.map(a=>`<article><h4>${esc(a.name)} · ${esc(a.replaces)} 교체 참고</h4><p>${esc(a.advisory)}</p>${a.reviewed_on?'<p class="psub">재점검 '+esc(a.reviewed_on)+' · '+esc(a.identity_source||'식별 확인 대기')+'</p>':''}${comparison(a.review)}</article>`).join('')+'</details>';
    return html+'<p class="psub">과거 고정 비중 가격 시나리오·현금수익 0·배당/비용 제외. 변동성·낙폭 차이는 미래 손실이나 기대수익률이 아닙니다. 작성 당시 검토와 최신 재점검은 별도입니다.</p></section>';
  }
  return {render};
})();
