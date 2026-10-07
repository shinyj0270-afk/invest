'use strict';
const FinancialCompletenessUI = (() => {
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt=v=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString('ko-KR',{maximumFractionDigits:2}):'—';
  const label=s=>s==='ready'?'확보':s==='partial'?'일부 확보':'대기';
  const names={revenue:'매출액',operating_profit:'영업이익',net_income:'순이익',assets:'자산',liabilities:'부채',equity:'자본',ocf:'영업현금흐름',parent_net:'지배순이익',parent_equity:'지배자본'};
  const safeUrl=url=>{try{const u=new URL(url);return u.protocol==='https:'&&u.hostname==='dart.fss.or.kr'?u.href:null;}catch{return null;}};
  function render(payload) {
    if(!payload)return '';
    const native=payload.native_financial,complete=payload.financial_completeness||native?.completeness||payload;
    const latest=complete.latest_stored||{},ttm=complete.ttm||{},required=complete.required_accounts||{},roe=complete.roe||{};
    let html='<section class="financial-completeness"><h3>재무 확보 상태</h3><div class="financial-completeness-grid">';
    for(const [title,status,detail] of [['최근 저장 원문',latest.status,`${latest.period_start||''}${latest.period_start?' → ':''}${latest.period_end||'기간 미확인'} · ${complete.basis||'기준 미확인'} · ${complete.currency||'통화 미확인'}`],['TTM 연속 4분기',ttm.status,ttm.reason||(ttm.periods||[]).join(' / ')],['필수 계정',required.status,(required.missing||[]).length?'미확보 '+required.missing.map(k=>names[k]||k).join(', '):'매출·영업손익·순손익·대차·영업현금흐름'],['ROE 계산 조건',roe.status,roe.reason||'TTM 귀속 손익·전년 같은 회계분기 평균 자본']])html+=`<article><strong>${esc(title)} · ${label(status)}</strong><p>${esc(detail)}</p></article>`;
    html+='</div><p>다음 확인: '+esc(complete.next_action||'공식 원문·기간·통화 확인')+'</p>';
    if(latest.available_at)html+=`<p class="psub">최근 원문 공개 ${esc(latest.available_at)} · 제출번호 ${esc(latest.receipt||'미확인')}</p>`;
    if(native?.groups?.length) {
      html+='<details open><summary>검증한 회계기간·원통화 재무</summary>';
      for(const g of native.groups) {
        const columns=(g.columns||[]).slice(-6),unit=g.amount_unit,divisor=g.amount_divisor;
        if(!['KRW','USD'].includes(g.currency)||!Number.isFinite(divisor)||divisor<=0)continue;
        const cadence={annual:'연간',quarter:'단독분기',cumulative:'누적'}[g.cadence]||g.cadence;
        html+=`<p>${esc(g.basis)} · ${esc(cadence)} · ${esc(g.currency)} · 금액 ${esc(unit)}</p><div class="risk-review-scroll"><table><thead><tr><th>계정 (${esc(unit)})</th>${columns.map(c=>`<th>${esc(c.period_start||'')}<br>${esc(c.period_end)}<br>FY${esc(c.fiscal_year)} Q${esc(c.fiscal_quarter)}</th>`).join('')}</tr></thead><tbody>`;
        for(const [key,name] of Object.entries(names))html+=`<tr><th>${esc(name)}</th>${columns.map(c=>`<td title="${esc(c.cell_notes?.[key]||'')}">${typeof c[key]==='number'?fmt(c[key]/divisor):'—'}${c.cell_notes?.[key]?' *':''}</td>`).join('')}</tr>`;
        html+='</tbody></table></div>';
      }
      const needsFx=native.groups.some(g=>g.currency==='USD');
      html+='<p class="psub">* 원문 계정·검산 잔차 참고값: 셀 주석을 확인하세요. '+(needsFx?esc(native.fx?.reason||'환산 출처·날짜·방법 확인 대기')+' · 원화 시총 기반 PER/PBR 환산 대기':'KRW 재무와 KRW 시총은 통화 환산 불필요 · PER/PBR은 동일 날짜 가격·시총 및 TTM 귀속 계정의 공통 가치평가를 확인하세요.')+'</p></details>';
    }
    const urls=(complete.source_urls||[]).map(safeUrl).filter(Boolean);
    if(urls.length)html+='<p>'+urls.slice(0,6).map((url,i)=>`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">DART 원문 ${i+1}</a>`).join(' · ')+'</p>';
    return html+'</section>';
  }
  return {render};
})();
