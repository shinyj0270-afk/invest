'use strict';
const LeaderStrategyUI=(()=>{
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=v=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString('ko-KR',{maximumFractionDigits:2}):'—';
function create({element,data,openCompany,openIndustry}){
 const state={market:'KOSPI',value:'',cell:null,all:false,expanded:false};
 const values=['고평가','중립','저평가','미확인'],levels=['상','중','하'];
 function render(){
  const rows=(data?.rows||[]).filter(r=>r.market===state.market&&(!state.value||r.value_band===state.value));
  const candidates=rows.filter(r=>r.candidate);
  const selected=state.cell?rows.filter(r=>r.momentum_band+'|'+r.turnover_band===state.cell):state.all?rows:candidates;
  const shown=state.expanded?selected:selected.slice(0,100),c=data?.config;
  const industries=[...new Set(candidates.map(r=>r.industry))].sort();
  element.innerHTML=`<div class="section-title"><h2>주도주 전략 <span class="ind-badge observed">관측</span></h2><p>저장된 모멘텀·거래대금·밸류의 자체 근사 분류 · 투자 판단·매수 추천 아님</p></div><form id="leaderFilters" class="panel controls"><label>시장<select name="market">${['KOSPI','KOSDAQ'].map(m=>`<option ${m===state.market?'selected':''}>${m}</option>`).join('')}</select></label><label>밸류<select name="value"><option value="">전체</option>${values.map(v=>`<option ${v===state.value?'selected':''}>${v}</option>`).join('')}</select></label><button>적용</button><button type="button" id="leaderCandidates">주도+밸류 중립 후보</button><button type="button" id="leaderAll">전체·미확보 보기</button></form>
  <article class="panel below"><h3>${esc(state.market)} 9칸 분포</h3><p class="psub">${esc(data?.as_of||'기준일 미확인')} · 표시 대상 ${rows.length}개 · 좌표 미확인 ${rows.filter(r=>r.momentum_band==='미확인'||r.turnover_band==='미확인').length}개 · 밸류 필터 ${esc(state.value||'전체')} · 후보 ${candidates.length}개</p>${data?.status!=='ready'?`<p role="status">${esc(data?.reason||'가격·거래·재무 자료 대기')}</p>`:''}<div class="leader-grid">${levels.flatMap(a=>levels.map(b=>{const key=a+'|'+b,count=rows.filter(r=>r.momentum_band===a&&r.turnover_band===b).length;return `<button data-leader-cell="${key}" aria-pressed="${state.cell===key}"><span>수익률 ${a} · 거래대금 ${b}</span><b>${count}개</b><small>${a==='상'&&b==='상'?'주도 후보 좌표':'관측 좌표'}</small></button>`;})).join('')}</div></article>
  <article class="panel below"><h3>${state.cell?'선택 좌표 '+esc(state.cell):state.all?'전체·미확보 기업':'주도+밸류 중립 후보'} · ${selected.length}개</h3><div class="tscroll"><table class="ind-table"><thead><tr><th>기업</th><th>모멘텀 (%)</th><th>거래대금 변화 (%)</th><th>모멘텀 z / 거래대금 z</th><th>좌표</th><th>밸류</th><th>판정·제외 사유</th></tr></thead><tbody>${shown.map(r=>`<tr><td><button class="company-link" data-leader-company="${esc(r.code)}">${esc(r.name)}<small>${esc(r.code)} · ${esc(r.industry)}</small></button></td><td>${fmt(r.momentum_pct)}</td><td>${fmt(r.turnover_change_pct)}<small>${r.turnover_method==='stored_turnover'?'저장 거래대금':r.turnover_method?'조정종가×거래량 근사':'미확보'}</small></td><td>${fmt(r.momentum_z)} / ${fmt(r.turnover_z)}</td><td>${esc(r.momentum_band)} / ${esc(r.turnover_band)}</td><td>${esc(r.value_band)}<small>${esc((r.value_metrics||[]).join('·'))} · ${esc(r.value_period||'기간 미확인')} · ${esc(r.value_basis||'기준 미확인')}</small></td><td>${esc(r.reason||(r.candidate?'조건 충족 관측 후보':'주도+밸류 중립 조건 미충족'))}</td></tr>`).join('')||'<tr><td colspan="7">해당 기업 없음 · 없는 후보를 생성하지 않습니다.</td></tr>'}</tbody></table></div>${selected.length>100?'<button id="leaderExpand">'+(state.expanded?'100개만 보기':'전체 '+selected.length+'개 보기')+'</button>':''}</article>
  <article class="panel below"><h3>산업별 후보 분포</h3><div class="research-actions">${industries.map(s=>`<button data-leader-industry="${esc(state.market+'|'+s)}">${esc(s)} · ${candidates.filter(r=>r.industry===s).length}개 → 산업 연구</button>`).join('')||'<p>현재 후보 없음</p>'}</div></article>
  <article class="panel below"><h3>정의·출처·보고서와 차이</h3><p>${esc(data?.source_note||'SK증권 2025-04-30 보고서(사용자 제공 자료, 공개 URL 미확인)')}</p>${c?`<ul class="ind-missing"><li>모멘텀: 최근 ${c.window}거래일 조정종가×거래량 VWAP / ${c.momentum_lag}거래일 전 ${c.window}일 VWAP − 1. 보고서 월간 VWAP 근사.</li><li>거래대금: 최근 ${c.window}일 / 직전 ${c.window}일 합 − 1. 원값 미확보 시 전 구간 조정종가×거래량 근사. 실제 거래대금·권리변동 보정 검증과 다릅니다.</li><li>시장별 시총 MinMax ${c.size_floor}~1, ${esc({divide_raw:'원지표 ÷ 규모 보정값 → 극단값 대체 → z',multiply_z:'극단값 대체 → z × 규모 보정값',none:'규모 보정 미적용'}[c.size_adjustment])}. 유동시총 대신 현재 시총 사용. 상하위 ${c.winsor_tail*100}% 선형 분위값으로 대체, 모집단 표준편차. ±${c.z_threshold} 경계 포함. 동일 시총은 보정값1, 상수/유효${c.min_members} 미만 미확인.</li><li>밸류: 동일 기간·기준·통화·가격일의 양수 PER/PBR/PCR/EV·EBITDA 중 2개 이상 역백분위 평균. 동률 중간순위, 최종 상·하 ${c.value_tail_pct}% 저평가/고평가, 나머지 중립. 단일 종목도 표본 부족 시 미확인.</li><li>보고서 샤프·MDD는 보고서 집계이며 이 화면의 검증된 성과가 아닙니다. HRP·헤지·1개월 자동 보유/매매는 이번 구현에 포함하지 않습니다.</li></ul>`:''}</article>`;
  element.querySelector('#leaderFilters').onsubmit=e=>{e.preventDefault();const f=new FormData(e.target);state.market=f.get('market');state.value=f.get('value');state.cell=null;state.expanded=false;render();};
  element.querySelectorAll('[data-leader-cell]').forEach(b=>b.onclick=()=>{state.cell=b.dataset.leaderCell;state.expanded=false;render();});
  element.querySelectorAll('[data-leader-company]').forEach(b=>b.onclick=()=>openCompany(b.dataset.leaderCompany));
  element.querySelectorAll('[data-leader-industry]').forEach(b=>b.onclick=()=>openIndustry(b.dataset.leaderIndustry));
  element.querySelector('#leaderCandidates').onclick=()=>{state.cell=null;state.all=false;render();};
  element.querySelector('#leaderAll').onclick=()=>{state.cell=null;state.all=true;render();};
  element.querySelector('#leaderExpand')?.addEventListener('click',()=>{state.expanded=!state.expanded;render();});
 }
 return {render};
}
return {create};})();
