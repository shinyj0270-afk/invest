'use strict';
// 산업 연구 화면: 산업 개요 → 산업 상세 → 구성기업 · Research Library · 원문.
// 관측값은 저장 payload에서만, 연구 해석은 읽기 전용 /research-library에서만 가져온다.
const IndustryUI=(()=>{
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=v=>typeof v==='number'&&Number.isFinite(v);
const fmt=(v,d=1)=>num(v)?v.toLocaleString('ko-KR',{maximumFractionDigits:d}):'—';
const pct=(v,d=1)=>num(v)?fmt(v,d)+'%':'—';
const safeLink=(url,label)=>{try{const u=new URL(url);return ['https:','http:'].includes(u.protocol)?`<a href="${esc(u.href)}" target="_blank" rel="noopener noreferrer">${esc(label||'원문 열기')} ↗</a>`:'';}catch{return '';}};
const SORTS=[['rs1m','1개월 RS'],['rs3m','3개월 RS'],['rs6m','6개월 RS'],['breadth','200일선 위 비중'],['cap','시가총액 합계']];
const MISSING=['마진 변화(전년 대비 증감) · 수준만 표시','ROIC · WACC(자본비용) · 미확보','수주잔고 · 산업 출하/가격 통계 · 미확보','투자 가능한 업종지수 총수익률 · 미확보'];
const KIND={thesis:'산업 가설',master:'연구카드',agent_note:'사람 검토 연구노트',source:'원문 참조'};
const STANCE={support:'지지',refute:'반박',context:'배경'};

function create({element,rows,research,insights,meta,live,resultView,sectorMap,phaseData,openCompany,openLibrary}){
 const E=IndustryEngine,all=E.groups(rows,research,insights);
 const state={sort:'rs1m',market:'',query:'',selected:null,showAll:false};
 let library=null,libraryState=resultView?'excluded':live?.token?'idle':'static';
 const mode=meta?.data_mode==='fixture'?'가상 테스트 · 실제 관측 아님 · ':'';
 const badge=(kind)=>kind==='observed'?'<span class="ind-badge observed">관측</span>':'<span class="ind-badge research">연구 해석 · 검증 전</span>';

 function phase(g){return phaseData?.sectors?.find(s=>s.market===g.market&&s.industry===g.industry);}
 function phaseCell(g){const p=phase(g);return p?`<td>${pct(p.growth.pct,0)}<small>생+왕 ${p.growth.count}/${p.eligible} · 미확인 ${p.missing}${p.rankable?'':' · 유효5 미만 비순위'}</small></td>`:'<td>—<small>국면 미확인</small></td>';}
 function phaseFacts(g){const p=phase(g),c=phaseData?.config;if(!p||!c)return '<article class="panel below"><h3>국면 확산 <span class="ind-badge observed">관측</span></h3><p>국면 자료 미확인 · '+esc(phaseData?.reason||'완료 가격 이력 대기')+'</p></article>';
 return `<article class="panel below" data-phase-facts><h3>국면 확산 ${badge('observed')}</h3><div class="ind-facts"><p>생+왕 기업 비중<b>${pct(p.growth.pct,0)}</b><small>${p.growth.count}/${p.eligible}개 · 미확인 ${p.missing}개</small></p><p>쇠+사 기업 비중<b>${pct(p.decline.pct,0)}</b><small>${p.decline.count}/${p.eligible}개</small></p><p>생+왕 / 쇠+사 시총 비중<b>${pct(p.growth.cap_pct,0)} / ${pct(p.decline.cap_pct,0)}</b><small>국면·양수 시총 확보 ${p.cap_eligible}개 · 분모 ${fmt(p.growth.cap_total_eok,0)}억원</small></p><p>최근 ${c.alert_days}거래일 쇠 진입<b>${p.recent_weak}개</b><small>기업별 중복 진입은 1개 · 관측 경보, 매매 신호 아님</small></p></div><p class="psub">자체 고정 규칙: 생=사 이후 첫 ${c.breakout_days}거래일 최고종가 돌파, 왕=${c.ma_fast}일선&gt;${c.ma_slow}일선·${c.high_weeks}주 최고종가 하락 ${c.weak_drawdown_pct}% 이내, 쇠=하락 ${c.weak_drawdown_pct}~${c.dead_drawdown_pct}% 또는 ${c.ma_fast}일선 이탈, 사=하락 ${c.dead_drawdown_pct}% 초과 또는 ${c.ma_fast}일선&lt;${c.ma_slow}일선. 우선순위 ${c.priority==='birth_first'?'생→사→쇠→왕':'사→쇠→생→왕'}, 그 외·이력 부족 미확인. 원문 학습 엔진 재현·주도산업 판정 아님.${p.rankable?'':' 유효5개 미만 비순위.'}</p></article>`;}
 function rsCell(g,k){const s=g.rs?.[k];return s?`<td>${fmt(s.score)}<small>${pct(s.return_pct)}</small></td>`:'<td>—<small>미확보</small></td>';}
 function researchCell(g){
  if(libraryState!=='ready')return '<td><small>'+({excluded:'결과 화면 제외',static:'실행 앱에서 확인',error:'연결 대기',loading:'확인 중'}[libraryState]||'—')+'</small></td>';
  const links=E.related(library,g,sectorMap);return `<td>${links.length?`${links.filter(l=>l.kind==='thesis').length} 가설 · ${links.filter(l=>l.kind==='master').length} 카드`:'—'}</td>`;
 }
 function row(g,rank){
  return `<tr><td><button class="company-link" data-industry="${esc(g.key)}">${rank?`<span class="ind-rank">${rank}</span>`:''}${esc(g.industry)}<small>${esc(g.market)} · ${g.count}개</small></button></td>${phaseCell(g)}${rsCell(g,'1m')}${rsCell(g,'3m')}${rsCell(g,'6m')}<td>${pct(g.breadth.above200.pct,0)}<small>${g.breadth.above200.count}/${g.breadth.above200.eligible}</small></td><td>${pct(g.revenue.pct,0)}<small>${g.revenue.count}/${g.revenue.eligible}</small></td><td>${pct(g.profit.pct,0)}<small>${g.profit.count}/${g.profit.eligible}</small></td><td>${pct(g.concentration.top_share_pct,0)}<small>${esc(g.concentration.top?.name||'—')}</small></td><td>${fmt(g.financial.revenue_growth_pct?.value)}<small>${g.financial.revenue_growth_pct?.count??0}개</small></td><td>${fmt(g.financial.operating_margin_pct?.value)}<small>${g.financial.operating_margin_pct?.count??0}개</small></td><td>${fmt(g.financial.roe_pct?.value)}<small>${g.financial.roe_pct?.count??0}개</small></td>${researchCell(g)}</tr>`;
 }
 const head=()=>`<thead><tr><th>산업 · 시장 · 구성</th><th>국면 확산<small>생+왕 기업 비중</small></th><th>1개월 RS<small>가중 수익률</small></th><th>3개월 RS</th><th>6개월 RS</th><th>200일선 위</th><th>매출 증가 기업<small>같은 기간·기준</small></th><th>영업이익 증가 기업<small>단독분기 전년동기</small></th><th>최대 기업 비중</th><th>매출성장률 중앙값 (%)</th><th>영업이익률 중앙값 (%)</th><th>ROE 중앙값 (%)</th><th>연결 연구<small>근거 수 아님</small></th></tr></thead>`;

 function overviewView(){
  const v=E.overview(all,state);
  return `<div class="section-title"><h2>산업 연구</h2><p>${mode}산업의 흐름과 확산을 먼저 보고, 구성기업·투자대가 연구·원문으로 이어갑니다.</p></div>
<form id="industryFilters" class="panel controls ind-filters"><label>산업 검색<input name="query" value="${esc(state.query)}" placeholder="산업명"></label><label>시장<select name="market"><option value="">전체</option>${['KOSPI','KOSDAQ'].map(m=>`<option ${state.market===m?'selected':''}>${m}</option>`).join('')}</select></label><label>정렬 기준<select name="sort">${SORTS.map(([k,l])=>`<option value="${k}" ${state.sort===k?'selected':''}>${l}</option>`).join('')}</select></label><button>적용</button><button type="button" id="industryReset">초기화</button></form>
<article class="panel"><div class="panel-heading"><h3>산업 비교 ${badge('observed')}</h3><span class="psub">종가 ${esc(meta?.price_date||'미확인')}</span></div><p class="psub">${esc(insights?.definition||'업종 RS 자료 미확보 · 순위를 만들지 않습니다.')}</p>${v.markets.map(m=>`<section data-industry-market="${esc(m.market)}"><h4>${esc(m.market)} · 시장 내 순위</h4><div class="tscroll"><table class="ind-table">${head()}<tbody>${m.ranked.map((g,i)=>row(g,i+1)).join('')||'<tr><td colspan="13">정렬 기준을 계산할 수 있는 산업이 없습니다.</td></tr>'}</tbody></table></div></section>`).join('')||'<p>표시할 산업이 없습니다.</p>'}
<p class="psub">구성: 네이버 공개 업종 분류의 시가총액 1,500억원 초과 탐색 대상 · 같은 거래소 안에서만 비교 · RS는 자체 백분위(IBD 공식 RS 아님) · 200일선 위 = 완료 종가 &gt; 200일 단순이동평균인 기업 비중 · 재무 중앙값은 기간·회계기준이 모두 같을 때만 표시합니다. 표시된 순서는 관측값 정렬이며 주도산업 판정이 아닙니다.</p></article>
<details class="panel below" ${v.ranked.length?'':'open'}><summary>자료 부족으로 순위에서 제외한 산업 · ${v.limited.length}개</summary><p class="psub">유효 구성기업 ${E.MIN_MEMBERS}개 미만이거나 정렬 기준값이 없는 산업입니다. 시장별로 나누고 서로 순위를 매기지 않고 이름순으로 둡니다.</p>${v.markets.map(m=>`<section><h4>${esc(m.market)}</h4><div class="tscroll"><table class="ind-table">${head()}<tbody>${m.limited.map(g=>row(g,0)).join('')||'<tr><td colspan="13">없음</td></tr>'}</tbody></table></div></section>`).join('')||'<p>없음</p>'}</details>
<article class="panel below"><h3>미확보 지표 ${badge('observed')}</h3><ul class="ind-missing">${MISSING.map(t=>`<li>${esc(t)}</li>`).join('')}</ul><p class="psub">자료가 없는 지표는 계산하거나 추정해 채우지 않습니다.</p></article>`;
 }

 function weightingFacts(g){
  return `<article class="panel below" data-sector-weighting><h3>업종 강세의 폭 · 가중방식과 기여 분해 ${badge('observed')}</h3><p>50일선 위 ${pct(g.breadth.above50?.pct)} (${g.breadth.above50?.count??0}/${g.breadth.above50?.eligible??0}개) · 200일선 위 ${pct(g.breadth.above200.pct)} (${g.breadth.above200.count}/${g.breadth.above200.eligible}개)</p><div class="tscroll"><table><thead><tr><th>관측기간</th><th>동일 비교 기업</th><th>현재 시총 가중 %</th><th>동일가중 평균 %</th><th>중앙값 %</th><th>양수 기업</th><th>시총 상위3 기여 %p</th><th>상위3 절대기여 비중 %</th></tr></thead><tbody>${[['1m','1개월'],['3m','3개월'],['6m','6개월']].map(([k,label])=>{const s=g.rs?.[k]||{};return `<tr><td>${label}</td><td>${s.count??0}개 · 제외 ${s.excluded??'—'}개</td><td>${fmt(s.return_pct)}</td><td>${fmt(s.equal_weight_return_pct)}</td><td>${fmt(s.median_return_pct)}</td><td>${s.positive_count??'—'}/${s.count??0}</td><td>${fmt(s.top3_contribution_pp)}</td><td>${fmt(s.top3_absolute_share_pct)}</td></tr>`;}).join('')}</tbody></table></div><p class="psub">각 기간 안에서는 수익률과 양수 시총이 모두 있는 같은 기업을 비교합니다. 상위3은 현재 시총 순, 기여는 비중×수익률(%p)입니다. 절대기여 비중은 상쇄되는 상승·하락을 구분하며 전체 절대기여가 0이면 —입니다. 현재 구성·현재 시총을 사용한 관측 분해로 당시 업종지수·투자수익률이 아닙니다. 5개 미만은 비순위입니다.</p></article>`;
 }
 function memberRows(g){
  const ms=[...g.members].sort((a,b)=>(b.metrics?.market_cap_eok||0)-(a.metrics?.market_cap_eok||0)||a.code.localeCompare(b.code));
  const shown=state.showAll?ms:ms.slice(0,20),total=g.concentration.cap_eok;
  return `<div class="tscroll"><table class="ind-table"><thead><tr><th>기업</th><th>시가총액 (억원)</th><th>산업 내 비중</th><th>1개월 수익률</th><th>3개월 수익률</th><th>1개월 RS</th><th>200일선 위</th><th>매출성장률 (%)</th><th>영업이익률 (%)</th><th>ROE (%)</th><th>재무 기간 · 기준</th><th>국면</th><th>종가일</th></tr></thead><tbody>${shown.map(r=>{const t=research?.rows?.[r.code]?.technical||{},s=t.short_rs||{},d=r.metric_details?.roe_pct||{},cap=r.metrics?.market_cap_eok,above=num(t.close)&&num(t.sma?.['200'])?(t.close>t.sma['200']?'예':'아니오'):'—';
   return `<tr><td><button class="company-link" data-company="${esc(r.code)}">${esc(r.name)}<small>${esc(r.code)}</small></button></td><td>${fmt(cap,0)}</td><td>${num(cap)&&cap>0&&total?pct(cap/total*100):'—'}</td><td>${pct(s['1m']?.return_pct)}</td><td>${pct(s['3m']?.return_pct)}</td><td>${fmt(s['1m']?.score)}</td><td>${above}</td><td>${fmt(r.metrics?.revenue_growth_pct)}</td><td>${fmt(r.metrics?.operating_margin_pct)}</td><td>${fmt(r.metrics?.roe_pct)}</td><td>${esc(d.period||'미확인')} · ${esc(d.basis||'미확인')}</td><td>${esc(phaseData?.rows?.[r.code]?.phase||'미확인')}</td><td>${esc(t.as_of||'미확인')}</td></tr>`;}).join('')}</tbody></table></div>${ms.length>20?`<button id="industryShowAll">${state.showAll?'상위 20개만 보기':'구성기업 전체 '+ms.length+'개 보기'}</button>`:''}`;
 }
 function checks(g){
  const fin=Object.entries(g.financial).filter(([,m])=>m.count&&m.value===null).map(([k])=>({roe_pct:'ROE',operating_margin_pct:'영업이익률',revenue_growth_pct:'매출성장률',debt_ratio_pct:'부채비율',per:'PER',pbr:'PBR'})[k]||k);
  return [`가격 확인: 완료 종가가 확인된 기업 ${g.priced_count}/${g.count}개 · 미확보 기업은 확산 계산에서 제외`,
   fin.length?`재무 기간·회계기준 혼재: ${fin.join(', ')} 중앙값 미표시 · 기업별 원문 확인 필요`:'재무 중앙값: 표시된 항목은 같은 기간·회계기준 기업만 사용',
   `집중도: 최대 기업 ${esc(g.concentration.top?.name||'—')} ${pct(g.concentration.top_share_pct)} · 상위 3개 ${pct(g.concentration.top3_share_pct)} · 대표주 상승을 산업 전체 실적 개선으로 해석하지 않습니다.`,
   '공시·뉴스·재무 원문: 구성기업의 기업 분석 화면에서 공시일·보고기간과 함께 확인'];
 }
 function source(s){const v=s.value||{};return `<li>${safeLink(v.url,v.title||s.id)||esc(v.title||s.id)}<small>원문 발행 ${esc(v.published_on||'미확인')} · 확인 ${esc(v.accessed_on||'미확인')}${v.locator?' · '+esc(v.locator):''}</small></li>`;}
 function researchRecord({kind,record:r,link}){
  const v=r.value||{},title=v.title||v.theme||v.principle||v.claim||r.id,body=v.claim||v.principle||v.hypothesis||'',list=(label,xs)=>xs?.length?`<p><b>${label}</b> ${esc(xs.join(' / '))}</p>`:'';
  const ev=(r.evidence||[]).map(e=>`<li>${esc(STANCE[e.value?.stance]||e.value?.stance||'근거')} · 관측 ${esc(e.value?.observed_on||'미확인')} · ${esc(e.value?.observation||'')}</li>`).join('');
  return `<article class="ind-record"><p class="ind-record-meta">${esc(KIND[kind]||kind)} · ${link==='company'?'구성기업 직접 연결':'사용자 확정 산업 대응표 연결'} · 연구 기록 ${esc((r.recorded_at||'미확인').slice(0,10))}${kind==='thesis'?' · '+esc(E.statusLabel(v.status)):''}${v.as_of?' · 내용 기준 '+esc(v.as_of):''}</p><h4>${esc(title)}</h4>${kind==='source'||body===title?'':`<p>${esc(body)}</p>`}${list('적용 조건',v.conditions)}${list('반증 조건',v.invalidation)}${list('반례',v.counterexamples)}${list('더 필요한 자료',v.missing_evidence)}${ev?`<details><summary>기록된 근거 (지지·반박·배경 구분, 개수는 독립 근거 수 아님)</summary><ul>${ev}</ul></details>`:''}${(kind==='source'?[r]:r.provenance||[]).length?`<ul class="ind-sources">${(kind==='source'?[r]:r.provenance).map(source).join('')}</ul>`:''}</article>`;
 }
 function researchSection(g){
  if(libraryState==='excluded')return '<p class="psub">회사 결과 조회 화면에는 연구자료가 포함되지 않습니다. 실행 중인 회사 앱에서 확인하세요.</p>';
  if(libraryState==='static')return '<p class="psub">정적 화면 · 로컬 연구 목록은 실행 중인 앱에서 확인하세요.</p>';
  if(libraryState==='error')return '<p class="psub" role="status">연구 목록 연결 대기 · 기존 연구는 보존됩니다.</p><button id="industryLibraryRetry">연구 다시 확인</button>';
  if(libraryState!=='ready')return '<p class="psub" role="status">저장 연구를 확인하는 중…</p>';
  const links=E.related(library,g,sectorMap),matched=new Set(links.flatMap(l=>[l.record.metadata?.sector,l.record.value?.sector]));
  const others=E.librarySectors(library).filter(s=>!matched.has(s));
  return `${links.length?links.map(researchRecord).join(''):'<p class="psub">이 산업과 직접 연결되거나 산업명이 대응하는 저장 연구가 없습니다.</p>'}
<p class="psub">연결 규칙: 연구의 종목 연결이 구성기업과 같으면 직접 연결, 연구 산업 태그는 사용자 확정 대응표(${esc(sectorMap?.status==='ready'?sectorMap.decided_on:'확인 필요 · 종목 직접 연결만 표시')})로만 연결합니다. 연구 적용 후보이며 현재 주도산업 판정·투자 판단이 아닙니다. 연구 기록·출처·revision 수를 독립 근거 수로 합산하지 않습니다.</p>
<div class="research-actions"><button data-library-sector="${esc([...links].sort((a,b)=>(a.link==='map'?0:1)-(b.link==='map'?0:1)).map(l=>l.record.metadata?.sector||l.record.value?.sector).find(Boolean)||'')}">Research Library에서 보기</button>${others.map(s=>`<button data-library-sector="${esc(s)}">다른 연구 산업: ${esc(s)}</button>`).join('')}</div>`;
 }
 function profitFacts(g){
  const p=g.profit,labels={profit_growth:'흑자 증가',turnaround:'흑자 전환',loss_narrowing:'적자 축소',breakeven:'적자→손익분기',from_zero:'0→흑자'};
  return `<p data-profit-summary><span>영업이익 증가 기업 비중</span><b>${pct(p.pct,0)}</b><small>${p.count}/${p.eligible}개 · ${esc(p.period_start||'기간 미확인')}~${esc(p.period||'미확인')} vs ${esc(p.previous_period_start||'전년 미확인')}~${esc(p.previous_period||'미확인')} · ${esc(p.basis||'기준 미확인')} · ${esc(p.currency||'통화 미확인')}</small><small>${Object.entries(labels).map(([k,label])=>label+' '+p.categories[k]+'개').join(' · ')}</small><small>다른 비교기간·기준·통화 ${p.excluded}개 제외 · 비교자료 미확보 ${p.missing}개${p.unknown_publication?' · 공개일 미확인 '+p.unknown_publication+'개':''}${p.qualified?' · 원문 계정 주석 확인 '+p.qualified+'개':''}</small><small>전년동기보다 영업이익 금액이 늘어난 기업. 적자 축소도 포함하며 증가율·흑자 기업 비율이 아닙니다.${p.unknown_publication?' 공개일 미확인 자료는 과거 시점 검증용이 아닙니다.':''}</small></p>`;
 }
 function detailView(g){
  const other=all.find(x=>x.industry===g.industry&&x.market!==g.market);
  return `<div class="section-title"><button class="link" id="industryBack">← 산업 비교로</button><h2>${esc(g.industry)} <small>${esc(g.market)}</small></h2><p>${mode}구성 ${g.count}개 · 종가 ${esc(meta?.price_date||'미확인')} · 같은 거래소 저장 유효기업 분포 대비${other?` · <button class="link" data-industry="${esc(other.key)}">${esc(other.market)} 같은 업종 보기</button>`:''}</p></div>
<div class="grid2"><article class="panel"><h3>추세의 지속 · 약화 확인 ${badge('observed')}</h3><div class="tscroll"><table><thead><tr><th>기간</th><th>RS 백분위</th><th>시총 가중 수익률</th><th>유효 기업</th></tr></thead><tbody>${[['1m','1개월 (21거래일)'],['3m','3개월 (63거래일)'],['6m','6개월 (126거래일)']].map(([k,l])=>`<tr><td>${l}</td><td>${fmt(g.rs?.[k]?.score)}</td><td>${pct(g.rs?.[k]?.return_pct)}</td><td>${g.rs?.[k]?.count??'—'}</td></tr>`).join('')}</tbody></table></div><p class="psub">RS는 ${E.MIN_MEMBERS}개 이상일 때만 계산된 기존 업종 지표입니다. 짧은 기간이 긴 기간보다 약하면 흐름 둔화 여부를 원문·실적으로 확인하세요.</p></article>
<article class="panel"><h3>구성기업으로의 확산 ${badge('observed')}</h3><div class="ind-facts"><p><span>200일선 위 기업</span><b>${pct(g.breadth.above200.pct,0)}</b><small>${g.breadth.above200.count}/${g.breadth.above200.eligible}개</small></p><p><span>3개월 수익률 양수 기업</span><b>${pct(g.breadth.positive3m.pct,0)}</b><small>${g.breadth.positive3m.count}/${g.breadth.positive3m.eligible}개</small></p><p><span>1개월 수익률 중앙값 (동일가중)</span><b>${pct(g.spread.median1m_pct)}</b><small>${g.spread.count}개</small></p><p><span>최대 기업 제외 시총 가중 1개월</span><b>${pct(g.spread.ex_top1m_pct)}</b><small>${g.spread.ex_top_count}개</small></p></div><p class="psub">가중 수익률과 중앙값·최대 기업 제외 값의 차이가 크면 소수 대형주의 영향일 수 있습니다. 가격 확산이며 실적 확산이 아닙니다.</p></article></div>
${weightingFacts(g)}${phaseFacts(g)}<article class="panel below"><h3>재무 · 투자효율 ${badge('observed')}</h3><div class="ind-facts">${[['revenue_growth_pct','매출성장률 중앙값'],['operating_margin_pct','영업이익률 중앙값 (수준)'],['roe_pct','ROE 중앙값'],['debt_ratio_pct','부채비율 중앙값']].map(([k,l])=>`<p><span>${l}</span><b>${pct(g.financial[k]?.value)}</b><small>${g.financial[k]?.count??0}개${g.financial[k]?.reason?' · '+esc(g.financial[k].reason):''}</small></p>`).join('')}<p><span>매출 증가 기업 비중</span><b>${pct(g.revenue.pct,0)}</b><small>${g.revenue.count}/${g.revenue.eligible}개 · ${esc(g.revenue.period||'기간 미확인')} · ${esc(g.revenue.basis||'기준 미확인')}${g.revenue.excluded?' · 다른 기간·기준 '+g.revenue.excluded+'개 제외':''}${g.revenue.missing?' · 매출성장률 미확보 '+g.revenue.missing+'개':''}</small></p>${profitFacts(g)}<p><span>ROIC · WACC</span><b>미확보</b><small>계산하지 않음</small></p></div></article>
<article class="panel below"><h3>확인할 공시 · 재무 · 위험</h3><ul class="ind-missing">${checks(g).map(t=>`<li>${esc(t)}</li>`).join('')}</ul></article>
<article class="panel below"><h3>구성기업 ${badge('observed')}</h3><p class="psub">시가총액 순 · 기업을 누르면 기업 분석으로 이동합니다. 가격·재무·공시의 기준일이 서로 다를 수 있습니다.</p>${memberRows(g)}</article>
<article class="panel below" id="industryResearch"><h3>관련 연구 · 원문 ${badge('research')}</h3>${researchSection(g)}</article>`;
 }

 async function loadLibrary(){
  if(!['idle','error'].includes(libraryState))return;
  libraryState='loading';
  try{library=await ResearchLibraryUI.load(live);libraryState='ready';}catch{libraryState='error';}
  if(!element.hidden)paint();
 }
 function bind(){
  const form=element.querySelector('#industryFilters');
  if(form)form.onsubmit=e=>{e.preventDefault();const f=new FormData(form);state.query=String(f.get('query')||'').trim();state.market=f.get('market')||'';state.sort=f.get('sort')||'rs1m';paint();};
  element.querySelector('#industryReset')?.addEventListener('click',()=>{Object.assign(state,{sort:'rs1m',market:'',query:''});paint();});
  element.querySelectorAll('[data-industry]').forEach(b=>b.onclick=()=>{state.selected=b.dataset.industry;state.showAll=false;paint();window.scrollTo?.(0,0);});
  element.querySelector('#industryBack')?.addEventListener('click',()=>{state.selected=null;paint();});
  element.querySelector('#industryShowAll')?.addEventListener('click',()=>{state.showAll=!state.showAll;paint();});
  element.querySelectorAll('[data-company]').forEach(b=>b.onclick=()=>openCompany(b.dataset.company));
  element.querySelectorAll('[data-library-sector]').forEach(b=>b.onclick=()=>openLibrary({sector:b.dataset.librarySector}));
  element.querySelector('#industryLibraryRetry')?.addEventListener('click',loadLibrary);
 }
 function paint(){const g=all.find(x=>x.key===state.selected);element.innerHTML=g?detailView(g):overviewView();bind();}
 function render(){paint();loadLibrary();}
 return {render,select:key=>{state.selected=all.some(g=>g.key===key)?key:null;}};
}
return {create};
})();
if(typeof module!=='undefined')module.exports=IndustryUI;
