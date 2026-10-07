'use strict';
(() => {
const $=id=>document.getElementById(id), esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const snap=WORKSPACE_DATA.analysis_snapshot||WORKSPACE_DATA.snapshot, rows=eligible(snap.companies), meta=snap.meta;
const discovery=WORKSPACE_DATA.discovery?.snapshot?.meta?.discovery===true?WORKSPACE_DATA.discovery:null;
const researchSnap=discovery?.snapshot||snap,researchData=discovery?.research||WORKSPACE_DATA.research,researchRows=DiscoveryEngine.prepare(researchSnap,researchData||{});
const discoveryRows=researchRows.filter(r=>r.discovery_allowed!==false);
const allRows=[...rows,...researchRows.filter(r=>!rows.some(c=>c.code===r.code))];
const canUseLegacy=c=>rows.some(r=>r.code===c)&&researchRows.find(r=>r.code===c)?.legacy_available!==false;
let liveReceipt=INVESTMENT_LIVE?.receipt||null;
const handoffKey='investment-live-refresh-handoff';
let handoff=null,restorationNote="";
if(INVESTMENT_LIVE){
  try{handoff=JSON.parse(sessionStorage.getItem(handoffKey)||'null');}catch{}
  sessionStorage.removeItem(handoffKey);
  $('refreshData').hidden=false;
  if(INVESTMENT_LIVE.daily_prices)$('priceRefreshStatus').textContent='일별 종가는 자동 갱신 · 새로고침은 최신 제공 가격 조회';
  $('sourceModeHint').textContent='화면을 열 때 저장자료의 최신 여부를 확인합니다. 일별 종가는 앱을 열 때와 열어둔 동안 자동 갱신합니다. 새로고침은 최신 제공 가격을 조회합니다.';
}
const specs={...METRICS,per:{label:'PER',unit:'배'},pbr:{label:'PBR',unit:'배'}};
const keys=['market_cap_eok','roe_pct','operating_margin_pct','revenue_growth_pct','debt_ratio_pct','per','pbr'];
const heatKeys=['roe_pct','operating_margin_pct','revenue_growth_pct','debt_ratio_pct'];
const fmt=(v,d=1)=>isNum(v)?v.toLocaleString('ko-KR',{maximumFractionDigits:d}):'—';
const pages=[['검토 자료 개요','overview','통합 개요'],['검토 자료 개요','prices','관측 가격 이력'],['검토 자료 비교','bars','지표별 데이터바'],['검토 자료 비교','heatmap','기업 × 지표 히트맵'],['검토 자료 비교','scatter','수익성 · 재무 관계'],['검토 기업 분석','screen','검토 조건검색'],['검토 기업 분석','company','검토 상세분석'],['검토 기업 분석','compare','검토 산업비교'],['보유 · 포트폴리오','holdings','보유 입력 · 검토'],['보유 · 포트폴리오','waterfall','평가손익 기여'],['보유 · 포트폴리오','portfolio','구성 · 시나리오'],['보유 · 포트폴리오','recommendations','월간 추천 기록'],['데이터','data','원수치 · 산출 기준']];
pages.unshift(['기업 발굴','trend-following','추세추종'],['고급 시각화','advanced','Advanced Visuals'],['기업 발굴','finder','수익성 · 가치 조건검색'],['기업 발굴','watch','관심 기업'],['기업 발굴','sectors','산업별 후보'],['기업 분석','brief','기업 간단 분석'],['기업 분석','trend','추세 확인']);
pages.unshift(['내 투자','home','대시보드']);
const mainPages=[['home','대시보드'],['finder','기업 찾기'],['watch','관심 기업'],['brief','기업 분석'],['holdings','내 보유종목'],['recommendations','포트폴리오']];
const extraPages=pages.filter(p=>p[1]!=='trend-following'&&!mainPages.some(([id])=>id===p[1]));
let page='overview',code=rows[0]?.code||'',frameReady=false,pendingTab='screen';
const researchUI=ResearchUI.create({element:$('research'),snapshot:researchSnap,research:researchData,insights:WORKSPACE_DATA.market_insights,references:WORKSPACE_DATA.references||{},financialTables:WORKSPACE_DATA.financial_tables||{},companyModels:WORKSPACE_DATA.company_details||{},reviewedMeta:meta,lazyTables:INVESTMENT_LIVE?.lazy_company_views===true,getCode:()=>code,setCode:c=>{code=c;},go,initial:handoff?.mode===meta.data_mode?handoff.research:undefined});
const companyUI=CompanyDetailUI.create({element:$('companyDetail'),rows,models:WORKSPACE_DATA.company_details,research:WORKSPACE_DATA.research,meta,getCode:()=>code,setCode:c=>{code=c;},shared:researchUI,go,initial:handoff?.mode===meta.data_mode?handoff.companyDetail:undefined});
const trendFollowingUI=TrendFollowingUI.create({element:$('trendFollowing'),data:WORKSPACE_DATA.trend_following||{},insights:WORKSPACE_DATA.market_insights,research:researchData,getCompany:c=>WORKSPACE_DATA.company_details?.[c],loadCompany:INVESTMENT_LIVE?.lazy_company_views?c=>window.INVESTMENT_LOAD_COMPANY_VIEW(c):null,isActive:()=>page==='trend-following',go:(id,c)=>{if(c)code=c;go(id);}});
const advancedUI=AdvancedVisuals.create({element:$('advanced'),snapshot:researchSnap,research:researchData||{},getHoldings:()=>$('detailFrame').contentWindow?.INVESTMENT_GET_HOLDINGS?.(),getPolicy:()=>$('detailFrame').contentWindow?.INVESTMENT_GET_POLICY?.()||{},getCompany:c=>WORKSPACE_DATA.company_details?.[c],loadCompany:c=>{if(INVESTMENT_LIVE?.lazy_company_views&&!companyViews.has(c))window.INVESTMENT_LOAD_COMPANY_VIEW?.(c);},go:(id,c)=>{if(c)code=c;go(id);}});
const recommendationUI=DashboardUpgradeUI.recommendations($('recommendationView'),{live:INVESTMENT_LIVE,go:(id,c)=>{if(c)code=c;go(id);},onStatus:message=>{$('recommendationHome').textContent=message;},onLoaded:data=>{const r=data.records.at(-1);$('recommendationHome').innerHTML=r?`<p>${esc(r.month)} · ${esc(r.review_status)}</p><div class="recommendation-preview">${r.targets.map(t=>`<button data-home-rec-code="${esc(t.code)}">${esc(t.name)} <b>${fmt(t.weight_pct)}%</b></button>`).join('')}<span>현금 <b>${fmt(r.cash_pct)}%</b></span></div>`:'이번 달 추천안 작성 대기';$('recommendationHome').querySelectorAll('[data-home-rec-code]').forEach(b=>b.onclick=()=>{code=b.dataset.homeRecCode;go('brief');});}});
$('navigation').innerHTML=mainPages.map(([id,t])=>`<button class="nav-item" data-page="${id}">${esc(t)}</button>`).join('')+`<details id="moreNavigation"><summary>비교 도구 · 자료</summary>${extraPages.map(([g,id,t])=>`<button class="nav-item" data-page="${id}">${esc(t)}</button>`).join('')}</details>`;
$('pageSelect').innerHTML='<optgroup label="내 투자">'+mainPages.map(([id,t])=>`<option value="${id}">${esc(t)}</option>`).join('')+'</optgroup><optgroup label="비교 도구 · 자료"><option value="trend-following">추세추종</option>'+extraPages.map(([g,id,t])=>`<option value="${id}">${esc(t)}</option>`).join('')+'</optgroup>';
for(const id of ['barMetric','xMetric','yMetric'])$(id).innerHTML=keys.map(k=>`<option value="${k}">${esc(specs[k].label)} (${specs[k].unit})</option>`).join('');
$('barMetric').value='market_cap_eok';$('xMetric').value='roe_pct';$('yMetric').value='operating_margin_pct';
for(const [id,key] of [['viewMarket','market'],['viewIndustry','industry']])$(id).innerHTML+=[...new Set(rows.map(r=>r[key]))].sort().map(v=>`<option>${esc(v)}</option>`).join('');
$('asof').textContent=(discovery?researchSnap.meta.price_date:meta.price_date)||'미연결';$('sideSource').textContent=discovery?`발굴 ${discoveryRows.length}개 · 기존 분석 ${rows.length}개 · 인포맥스 우선 / 공개자료 보완`:`${meta.data_mode==='fixture'?'가상 테스트':'Infomax 저장자료'} · ${rows.length}개 적격 기업 · ${meta.price_date}`;
$('sourceNotice').textContent=`${meta.data_mode==='fixture'?'가상 테스트 · 실제 관측 아님':'실제 저장 스냅샷 · 새 API 조회 없음'} · 가격 ${meta.price_date} · 재무 ${meta.financial_period} ${meta.financial_basis}`;
$('footerScope').textContent=`${discovery?'발굴 종가 '+researchSnap.meta.price_date+' · ':''}검토 종가 ${meta.price_date} · 검토 재무 ${meta.financial_period} ${meta.financial_basis}`;
function selected(){const q=$('viewSearch').value.trim().toLowerCase();return rows.filter(r=>(!$('viewMarket').value||r.market===$('viewMarket').value)&&(!$('viewIndustry').value||r.industry===$('viewIndustry').value)&&(!q||r.name.toLowerCase().includes(q)||r.code.includes(q)));}
function scope(){const all=selected();return all.slice(0,30);}
function empty(text){return `<div class="empty"><strong>자료 대기</strong><span>${esc(text)}</span></div>`;}
function homeList(rs,missing){return rs.length?rs.slice(0,6).map(r=>{const t=researchData?.rows?.[r.code]?.technical,q=r.latest_quote;return `<button class="home-company" data-home-code="${esc(r.code)}" ${allRows.some(a=>a.code===r.code)?'':'disabled title="기업 분석 자료 연결 대기"'}><span><b>${esc(r.name||r.code)}</b><small>${esc(r.code)} · ${esc(r.industry||r.market)}</small></span><span>${fmt(q?.price??t?.close??r.price_krw,0)}원<small>${q?'최신 제공 가격 · 조회 '+esc(q.retrieved_at?.slice(5,16).replace('T',' ')||'시각 미확인'):'저장 종가'}</small></span></button>`;}).join(''):`<p class="home-empty">${esc(missing)}</p>`;}
function renderHome(){
 DashboardUpgradeUI.overview($('upgradeOverview'),{rows:researchRows,research:researchData,insights:WORKSPACE_DATA.market_insights});
 const indices=WORKSPACE_DATA.market_summary||[];
 $('marketSummary').innerHTML=indices.map(r=>`<div class="kpi"><span>${esc(r.market)} · 완료 종가</span><strong>${fmt(r.close,2)}</strong><small>${esc(r.date)} · 전 관측일 대비 ${fmt(r.change_pct,2)}%</small></div>`).join('')+`<div class="kpi"><span>기업 탐색 범위</span><strong>${discoveryRows.length.toLocaleString()}개</strong><small>${esc(researchSnap.meta.price_date||'기준일 대기')} · 시가총액 850억원 초과</small></div><div class="kpi"><span>관심 기업</span><strong>${researchRows.filter(r=>researchUI.isWatched(r.code)).length}개</strong><small>직접 선택한 관심목록</small></div>`;
 if(!indices.length)$('marketSummary').insertAdjacentHTML('afterbegin','<div class="kpi"><span>시장 지수</span><strong>—</strong><small>같은 기준일의 완료 관측 자료 대기</small></div>');
 $('homeWatch').innerHTML=homeList(researchRows.filter(r=>researchUI.isWatched(r.code)),'기업 찾기에서 별표를 눌러 관심 기업을 추가하세요.');
 const input=$('detailFrame').contentWindow?.INVESTMENT_GET_HOLDINGS?.();
 const held=(input?.holdings||[]).map(h=>({...input.research?.find(r=>r.code===h.code),...h,...allRows.find(r=>r.code===h.code)}));
 $('homeHoldings').innerHTML=homeList(held,frameReady?'직접 입력한 보유종목이 없습니다.':'보유 입력을 불러오는 중…')+(input?.holdings?.length?`<p class="psub">${input.mode==='fixture'?'가상 테스트 · 실제 보유 아님':'현재 보유 입력'} · 평가는 보유 검토에서 확인하세요.</p>`:'');
 $('homeSectors').innerHTML=DashboardJourney.sectors(WORKSPACE_DATA.market_insights);
 if(!WORKSPACE_DATA.market_insights){const groups=DiscoveryEngine.sectors(discoveryRows,researchData||{}).filter(g=>g.cap>0).slice(0,8);$('homeSectors').innerHTML='<p class=psub>업종 RS 미확보 · 아래는 저장 후보 시가총액 순서입니다.</p>'+groups.map(g=>`<button data-home-sector="${esc(g.name)}">${esc(g.name)} · ${g.count}개</button>`).join('');}
 $('upgradeOverview').insertAdjacentHTML('beforeend',DashboardJourney.healthQueue(researchRows));
 const bindJourney={rows:researchRows,go:c=>{code=c;go('brief');},search:(industry,market)=>{researchUI.search('',industry,market);go('finder');}};
 DashboardJourney.bind($('home'),bindJourney);
 $('home').querySelectorAll('[data-home-code]').forEach(el=>el.onclick=()=>{code=el.dataset.homeCode;go('brief');});
 $('home').querySelectorAll('[data-home-sector]').forEach(el=>el.onclick=()=>{researchUI.search('',el.dataset.homeSector);go('finder');});
}
function contextNavigation(id){
 const groups=[['trend-following','finder','sectors'],['brief','company','trend','compare'],['holdings','waterfall'],['recommendations','portfolio']];
 const group=groups.find(g=>g.includes(id))||[];
 const labels={'trend-following':'추세추종',finder:'조건검색',sectors:'산업별 후보',brief:'핵심 요약',company:'재무 · 가치 상세',trend:'가격 추세',compare:'검토 산업비교',holdings:'보유 입력 · 검토',waterfall:'손익 기여',portfolio:'구성 · 시나리오',recommendations:'월간 추천 기록'};
 $('contextNavigation').innerHTML=group.length>1?group.map(p=>`<button data-context-page="${p}" aria-current="${p===id?'page':'false'}" ${p==='company'&&!canUseLegacy(code)?'disabled title="상세 재무 원자료 연결 대기"':''}>${labels[p]}</button>`).join(''):'';
 $('contextNavigation').querySelectorAll('button').forEach(el=>el.onclick=()=>go(el.dataset.contextPage));
}
function companyButton(r){return `<button class="company-link" data-code="${r.code}">${esc(r.name)}<small>${r.code}</small></button>`;}
function bars(rs,key){const valid=rs.filter(r=>isNum(val(r,key))).sort((a,b)=>val(b,key)-val(a,key));if(!valid.length)return empty('선택 지표의 유효한 값이 없습니다.');const lo=Math.min(0,...valid.map(r=>val(r,key))),hi=Math.max(0,...valid.map(r=>val(r,key))),span=hi-lo||1,z=-lo/span*100;return valid.map(r=>{const v=val(r,key),x=(v-lo)/span*100;return `<div class="bar-row">${companyButton(r)}<div class="bar-track"><i style="left:${Math.min(x,z)}%;width:${Math.abs(x-z)}%"></i><em style="left:${z}%"></em></div><span class="bar-value">${fmt(v)}</span></div>`}).join('')+`<p class="psub">유효 ${valid.length}/${rs.length}개 · ${esc(specs[key].unit)} · 막대 길이는 값의 크기</p>`;}
function heat(rs,ks){if(!rs.length)return empty('필터에 맞는 기업이 없습니다.');const ranges=ks.map(k=>{const vs=rs.map(r=>val(r,k)).filter(isNum);return [Math.min(...vs),Math.max(...vs)];});return `<div class="tscroll"><table class="heat"><thead><tr><th>기업</th>${ks.map(k=>`<th>${esc(specs[k].label)}<br>${specs[k].unit}</th>`).join('')}</tr></thead><tbody>${rs.map(r=>`<tr><td>${companyButton(r)}</td>${ks.map((k,i)=>{const v=val(r,k),[lo,hi]=ranges[i],p=v===null?null:hi===lo?.5:(v-lo)/(hi-lo),bg=p===null?'#f1f3f6':`rgb(${Math.round(237-188*p)},${Math.round(245-115*p)},${Math.round(255-9*p)})`;return `<td><button data-code="${r.code}" data-key="${k}" class="${v===null?'missing ':''}${code===r.code?'selected':''}" style="background:${bg};color:${p>.65?'white':'#333d4b'}" title="${esc(r.name+' · '+specs[k].label+': '+fmt(v)+' '+specs[k].unit)}">${fmt(v)}</button></td>`}).join('')}</tr>`).join('')}</tbody></table></div><div class="ramp">선택 기업 내 상대 크기 <span>낮음</span><i></i><span>높음</span></div><p class="psub">셀 숫자는 원값. 지표별 최솟값~최댓값으로 색을 계산하며 동일 값은 중간색입니다. 부채비율도 큰 값이 진합니다. 투자 점수가 아닙니다.</p>`;}
function table(rs){return `<table><thead><tr><th>기업</th>${keys.map(k=>`<th>${esc(specs[k].label)} (${specs[k].unit})</th>`).join('')}</tr></thead><tbody>${rs.map(r=>`<tr><td>${companyButton(r)}</td>${keys.map(k=>`<td>${fmt(val(r,k))}</td>`).join('')}</tr>`).join('')}</tbody></table>`;}
function framePlot(content,title){return `<svg class="plot" viewBox="0 0 660 390" role="img" aria-label="${esc(title)}">${content}</svg>`;}
function scatter(rs){const xk=$('xMetric').value,yk=$('yMetric').value,vs=rs.filter(r=>isNum(val(r,xk))&&isNum(val(r,yk)));if(!vs.length)return empty('두 지표가 함께 있는 기업이 없습니다. 결측을 0으로 대체하지 않습니다.');const bounds=k=>{let lo=Math.min(...vs.map(r=>val(r,k))),hi=Math.max(...vs.map(r=>val(r,k))),pad=(hi-lo)*.1||Math.abs(lo)*.1||1;return[lo-pad,hi+pad]};const [xl,xh]=bounds(xk),[yl,yh]=bounds(yk),x=v=>76+(v-xl)/(xh-xl)*550,y=v=>320-(v-yl)/(yh-yl)*285;let svg='';for(let i=0;i<=5;i++){const xx=76+i*110,yy=320-i*57;svg+=`<line class="grid" x1="${xx}" x2="${xx}" y1="35" y2="320"/><line class="grid" x1="76" x2="626" y1="${yy}" y2="${yy}"/><text x="${xx}" y="343" text-anchor="middle">${fmt(xl+(xh-xl)*i/5)}</text><text x="65" y="${yy+4}" text-anchor="end">${fmt(yl+(yh-yl)*i/5)}</text>`;}svg+=vs.map(r=>`<circle role="button" tabindex="0" aria-label="${esc(r.name+' '+r.code)}" class="point ${r.code===code?'selected':''}" data-code="${r.code}" cx="${x(val(r,xk))}" cy="${y(val(r,yk))}" r="8"><title>${esc(r.name)} · ${r.code}\n${esc(specs[xk].label)} ${fmt(val(r,xk))} ${specs[xk].unit}\n${esc(specs[yk].label)} ${fmt(val(r,yk))} ${specs[yk].unit}</title></circle>`).join('');svg+=`<text class="axis-label" x="350" y="375" text-anchor="middle">${esc(specs[xk].label)} (${specs[xk].unit})</text><text class="axis-label" transform="translate(18,180) rotate(-90)" text-anchor="middle">${esc(specs[yk].label)} (${specs[yk].unit})</text>`;return framePlot(svg,'기업별 두 지표 산점도')+`<p class="psub">유효 ${vs.length}/${rs.length}개 · 점 클릭 또는 Enter로 기업 선택 · 표본의 관계이며 인과가 아닙니다.</p>`;}
function observedPrices(r){return (r?.prices||[]).filter(p=>isNum(p.close)&&p.close>0&&p.date<=meta.price_date&&typeof p.final==='boolean'&&Object.hasOwn(p,'venue')&&typeof p.adjustment_basis==='string'&&p.adjustment_basis);}
function price(r){const ps=observedPrices(r);if(!ps.length)return empty('이 기업의 저장된 관측 종가 이력이 없습니다.');const ys=ps.map(p=>p.close),lo=Math.min(...ys),hi=Math.max(...ys),span=hi-lo||1,dates=ps.map(p=>Date.parse(p.date+'T00:00:00Z')),t0=dates[0],td=dates.at(-1)-t0||1,x=i=>ps.length===1?350:76+(dates[i]-t0)/td*550,y=v=>310-(v-lo)/span*260;let out='';for(let i=0;i<=4;i++){const yy=310-i*65;out+=`<line class="grid" x1="76" x2="626" y1="${yy}" y2="${yy}"/><text x="67" y="${yy+4}" text-anchor="end">${fmt(lo+span*i/4,0)}</text>`;}out+=`<path d="${ps.map((p,i)=>(i?'L':'M')+x(i)+','+y(p.close)).join(' ')}" fill="none" stroke="#3182f6" stroke-width="3"/>`+ps.map((p,i)=>`<circle cx="${x(i)}" cy="${y(p.close)}" r="4" fill="#3182f6"><title>${esc(p.date)} · ${fmt(p.close,0)}원</title></circle>`).join('')+`<text x="76" y="346">${ps[0].date}</text><text x="626" y="346" text-anchor="end">${ps.at(-1).date}</text><text x="350" y="375" text-anchor="middle">관측 종가 (원) · ${ps.length}건</text>`;return framePlot(out,'관측 종가 이력');}
function renderFocus(rs){if(!rs.some(r=>r.code===code))code=rs[0]?.code||'';$('focusCompany').innerHTML=rs.map(r=>`<option value="${r.code}">${esc(r.name)} · ${r.code}</option>`).join('');$('focusCompany').value=code;const r=rs.find(r=>r.code===code);$('focusMetrics').innerHTML=r?keys.map(k=>`<div class="focus-row"><span>${esc(specs[k].label)}</span><b>${fmt(val(r,k))} ${specs[k].unit}</b></div>`).join(''):empty('기업을 선택하세요.');}
function updateStatus(rs,total){if(page==='trend-following'){$('sourceNotice').textContent=`${meta.data_mode==='fixture'?'가상 테스트 · 실제 관측 아님':'실제 저장자료'} · 추세추종 · 완료 종가 ${WORKSPACE_DATA.trend_following?.as_of||'대기'} · 시총 기본 1,000억원 이상 · 시장과 종목 차트`;return;}if(page==='home'){$('sourceNotice').textContent=`${meta.data_mode==='fixture'?'가상 테스트 · 실제 관측 아님':'실제 저장자료'} · 종가 ${researchSnap.meta.price_date} · 후보 ${researchRows.length}개 · 인포맥스 우선 / 공개자료 보완 · 최신 제공 가격의 시세시각·지연 미확인`+restorationNote;return;}if(page==='advanced'){$('sourceNotice').textContent=`${researchSnap.meta.data_mode==='fixture'?'가상 테스트 · 실제 관측 아님':'실제 저장자료'} · Advanced 모집단 ${researchRows.length}개 · 기준일 ${researchSnap.meta.price_date||'unknown'} · 검토 상세 ${rows.length}개 · 필터 결과는 아래 표시`;return;}const liveNote=liveReceipt?` · ${liveReceipt.stale?'오래된 자료':'기준일 확인'} · 갱신 ${liveReceipt.status}${liveReceipt.error?' · '+liveReceipt.error:''}`:'';$('sourceNotice').textContent=`${meta.data_mode==='fixture'?'가상 테스트 · 실제 관측 아님':'실제 저장 스냅샷'+(INVESTMENT_LIVE?' · 열 때 최신 자료 확인':' · 새 API 조회 없음')} · 가격 ${meta.price_date} · 재무 ${meta.financial_period} ${meta.financial_basis}${liveNote} · ${$('viewMarket').value||'전체 시장'} / ${$('viewIndustry').value||'전체 산업'}${$('viewSearch').value?' / 검색: '+$('viewSearch').value:''} · 표시 ${rs.length}/${total}개 (최대 30)`+restorationNote;if(researchUI.isPage(page))$('sourceNotice').textContent=(discovery?`기업 발굴 ${discoveryRows.length}개 · 참고 기준일 ${researchSnap.meta.price_date} · ${researchSnap.meta.discovery_note||'인포맥스 우선 · 네이버 공개 보완자료 · 종목 분류 및 재무 기간·기준 확인 필요'}`:`${meta.data_mode==='fixture'?'가상 테스트 · 실제 관측 아님':'실제 저장 스냅샷'} · 가격 ${meta.price_date} · 재무 ${meta.financial_period} ${meta.financial_basis}${liveNote} · 저장 적격 기업 ${rows.length}개`)+restorationNote;}
function render(){if(page==='trend-following'){trendFollowingUI.render();return;}if(page==='recommendations'){recommendationUI.render();return;}if(page==='home'){renderHome();updateStatus([],researchRows.length);return;}if(page==='company'){companyUI.render();return;}if(page==='advanced'){advancedUI.render();return;}if(researchUI.isPage(page)){researchUI.render(page);updateStatus([],rows.length);return;}const rs=scope(),total=selected().length;renderFocus(rs);updateStatus(rs,total);$('scope').textContent=`표시 ${rs.length}/${total}개 · 최대 30개 · 비교 차트·원수치·CSV에 동일 범위 적용`;$('sourceTable').innerHTML=table(rs);const overviewKeys=['roe_pct','operating_margin_pct','debt_ratio_pct'];if(page==='overview'){$('kpis').innerHTML=[['표시 기업',String(rs.length),'현재 비교 범위'],['ROE 중앙값',fmt(median(rs.map(r=>val(r,'roe_pct'))))+'%','유효 '+rs.filter(r=>val(r,'roe_pct')!==null).length+'개'],['영업이익률 중앙값',fmt(median(rs.map(r=>val(r,'operating_margin_pct'))))+'%','유효 '+rs.filter(r=>val(r,'operating_margin_pct')!==null).length+'개'],['관측 가격 보유',rs.filter(r=>observedPrices(r).length).length+' / '+rs.length,'종가 이력 포함 기업']].map(([l,v,n])=>`<div class="kpi"><span>${l}</span><strong>${v}</strong><small>${n}</small></div>`).join('');$('overviewBars').innerHTML=bars(rs,'market_cap_eok');$('overviewHeat').innerHTML=heat(rs,overviewKeys);$('overviewTable').innerHTML=table(rs);}
const labels={bars:['지표별 데이터바','하나의 지표를 같은 기준선으로 비교합니다.','기업별 '+specs[$('barMetric').value].label,'막대 또는 기업명을 눌러 오른쪽 상세를 확인하세요.'],heatmap:['기업 × 지표 히트맵','같은 보고기간의 재무 지표를 함께 비교합니다.','재무 지표 한눈에','셀 클릭으로 기업을 선택합니다.'],scatter:['수익성 · 재무 관계','선택한 두 지표의 기업별 분포를 살펴봅니다.','두 지표의 관계','X/Y 지표를 바꾸고 기업 점을 선택하세요.'],prices:['관측 가격 이력','선택 기업의 저장된 종가를 확인합니다.','선택 기업의 가격 추이','저장된 날짜를 기준으로 표시하며 가격 이력을 임의 생성하지 않습니다.']};if(labels[page]){const [t,d,c,n]=labels[page];$('exploreTitle').textContent=t;$('exploreDescription').textContent=d;$('chartTitle').textContent=c;$('chartNote').textContent=n;$('barMetric').parentElement.hidden=page!=='bars';for(const id of ['xMetric','yMetric'])$(id).parentElement.hidden=page!=='scatter';$('metricControls').hidden=!['bars','scatter'].includes(page);$('mainChart').innerHTML=page==='bars'?bars(rs,$('barMetric').value):page==='heatmap'?heat(rs,heatKeys):page==='scatter'?scatter(rs):price(rs.find(r=>r.code===code));}
bindCompanies();}
function pick(c,key){code=c;if(page==='overview'){go('heatmap');}else render();$('selectionNote').textContent=(rows.find(r=>r.code===c)?.name||c)+(key?' · '+specs[key].label:'')+' 선택';}
function bindCompanies(){document.querySelectorAll('[data-code]').forEach(el=>{el.addEventListener('click',()=>pick(el.dataset.code,el.dataset.key));if(el.tagName.toLowerCase()==='circle')el.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();pick(el.dataset.code);}});});}
function waterfall(){const data=$('detailFrame').contentWindow?.INVESTMENT_GET_HOLDINGS?.();$('waterfallScope').textContent=data?`${data.mode==='fixture'?'가상 테스트 · 실제 보유 아님':'현재 브라우저의 보유 입력'} · 평가 ${data.as_of}`:'보유 입력 대기';if(!data?.holdings.length){$('waterfallChart').innerHTML=empty('보유 입력 · 검토에서 보유종목을 입력하거나 입력 파일을 불러오세요.');return;}let pos;try{pos=PortfolioEngine.reviewHoldings(data,$('detailFrame').contentWindow.INVESTMENT_GET_POLICY?.()||{}).rows;}catch{$('waterfallChart').innerHTML=empty('포트폴리오 설정을 확인하면 손익을 다시 계산합니다.');return;}if(pos.some(r=>!isNum(r.cost_krw)||!isNum(r.value_krw))){$('waterfallChart').innerHTML=empty('모든 보유종목의 유효 가격과 매입 원가가 필요합니다.');return;}const start=pos.reduce((s,r)=>s+r.cost_krw,0),end=pos.reduce((s,r)=>s+r.value_krw,0);if(!Number.isSafeInteger(Math.round(start))||!Number.isSafeInteger(Math.round(end))){$('waterfallChart').innerHTML=empty('합계가 안전한 계산 범위를 초과합니다.');return;}const sorted=[...pos].sort((a,b)=>Math.abs(b.pnl_krw)-Math.abs(a.pnl_krw)),drivers=sorted.slice(0,10).map(r=>[r.name+' · '+r.code,r.value_krw-r.cost_krw]);if(sorted.length>10)drivers.push(['그 외 '+(sorted.length-10)+'종목',sorted.slice(10).reduce((s,r)=>s+r.value_krw-r.cost_krw,0)]);let cursor=start,vs=[['주식 원가',0,start,start]];for(const [n,v]of drivers){vs.push([n,cursor,cursor+v,v]);cursor+=v;}vs.push(['주식 평가액',0,end,end]);const lo=Math.min(0,...vs.flatMap(r=>[r[1],r[2]])),hi=Math.max(0,...vs.flatMap(r=>[r[1],r[2]])),span=hi-lo||1,y=v=>285-(v-lo)/span*225,step=550/vs.length;let svg='';for(let i=0;i<=4;i++)svg+=`<line class="grid" x1="70" x2="630" y1="${285-i*56.25}" y2="${285-i*56.25}"/><text x="64" y="${289-i*56.25}" text-anchor="end">${fmt(lo+span*i/4,0)}</text>`;svg+=vs.map(([n,a,b,v],i)=>`<rect x="${76+i*step}" y="${Math.min(y(a),y(b))}" width="${step*.65}" height="${Math.max(1,Math.abs(y(a)-y(b)))}" rx="3" fill="${i===0||i===vs.length-1?'#6b7684':v>=0?'#f06b63':'#3182f6'}"><title>${esc(n)} · ${fmt(v,0)}원</title></rect><text transform="translate(${83+i*step},310) rotate(28)" font-size="10">${esc(n.length>13?n.slice(0,12)+'…':n)}</text>`).join('');$('waterfallChart').innerHTML='<div class="chart-scroll">'+framePlot(svg,'보유 평가손익 워터폴')+'</div>'+`<p class="psub">${fmt(start,0)} + ${fmt(end-start,0)} = ${fmt(end,0)}원 · 이익 빨강 / 손실 파랑 / 합계 회색</p>`;}
function go(id){if(!pages.some(p=>p[1]===id))return;if(id!=='trend-following')trendFollowingUI.deactivate();if(id==='company'&&!canUseLegacy(code)){$('sourceNotice').textContent='선택 기업은 기존 상세·보유 평가용 자료가 연결되지 않았습니다. 기업 발굴·간단 분석·추세 화면에서 확인하세요.';return;}if(id==='company')$('research').replaceChildren();else $('companyDetail').replaceChildren();try{sessionStorage.setItem('investment-current-page',id);sessionStorage.setItem('investment-current-company',code);sessionStorage.setItem('investment-advanced-open',id==='advanced'?'1':'0');}catch{}window.scrollTo(0,0);page=id;document.body.dataset.currentPage=id;$('sourceDetails').open=false;contextNavigation(id);$('moreNavigation').open=extraPages.some(p=>p[1]===id)&&!['sectors','company','trend','compare','waterfall'].includes(id);$('pageSelect').value=id;const p=pages.find(p=>p[1]===id);$('workspacePath').textContent=p[0]+' / '+p[2];const primaryId=({'trend-following':'finder',sectors:'finder',company:'brief',trend:'brief',compare:'brief',waterfall:'holdings',portfolio:'recommendations'})[id]||id;document.querySelectorAll('.nav-item').forEach(el=>el.setAttribute('aria-current',el.dataset.page===id||el.dataset.page===primaryId?'page':'false'));const legacy=['screen','compare','holdings','portfolio','data'].includes(id);for(const v of ['home','overview','explorer','waterfall','legacy','research','advanced','companyDetail','recommendationView','trendFollowing'])$(v).hidden=v!==(id==='trend-following'?'trendFollowing':id==='recommendations'?'recommendationView':id==='company'?'companyDetail':id==='advanced'?'advanced':researchUI.isPage(id)?'research':legacy?'legacy':['home','overview','waterfall'].includes(id)?id:'explorer');$('exportCsv').hidden=legacy||['trend-following','recommendations','home','company','advanced','waterfall','brief','trend'].includes(id);if(legacy){$('legacyTitle').textContent=p[2];pendingTab=id;if(frameReady){const w=$('detailFrame').contentWindow;w.INVESTMENT_ACTIVATE(id);if(id==='company'){const sel=w.document.getElementById('companySelect');if([...sel.options].some(o=>o.value===code)){sel.value=code;sel.dispatchEvent(new Event('change'));}}}}else if(id==='waterfall')waterfall();else render();updateStatus(scope(),selected().length);}
window.INVESTMENT_CAN_OPEN_HOLDING_COMPANY=c=>allRows.some(r=>r.code===c);
window.INVESTMENT_OPEN_HOLDING_COMPANY=c=>{if(allRows.some(r=>r.code===c)){code=c;go('brief');}else $('sourceNotice').textContent='연결된 기업 간단 분석 자료가 없습니다.';};
window.INVESTMENT_OPEN_COMPANY=c=>{if(canUseLegacy(c)){code=c;go('company');}};
$('detailFrame').addEventListener('load',()=>{frameReady=true;const f=$('detailFrame'),w=f.contentWindow;w.INVESTMENT_ACTIVATE?.(pendingTab);if(handoff?.input&&handoff.mode===meta.data_mode){try{const status=w.INVESTMENT_RESTORE_SESSION(handoff.input,handoff.policy);if(status==='identity_review_needed')restorationNote=' · 보유 입력은 복원했습니다. 종목 식별이 바뀌어 새 가격을 연결하지 않았습니다. 확인하세요.';}catch{ restorationNote=' · 이전 보유 입력 복원 실패 · 내보낸 JSON을 다시 불러오세요.';}}if(handoff?.draft&&handoff.mode===meta.data_mode)w.INVESTMENT_RESTORE_DRAFT?.(handoff.draft);new w.ResizeObserver(()=>{f.style.height=Math.max(700,w.document.body.scrollHeight+30)+'px';}).observe(w.document.body);if(page==='advanced')advancedUI.render();if(page==='waterfall')waterfall();if(page==='home')renderHome();updateStatus(scope(),selected().length);});$('detailFrame').srcdoc=WORKSPACE_DATA.detail_html;
document.querySelectorAll('[data-page]').forEach(el=>el.onclick=()=>go(el.dataset.page));document.querySelectorAll('[data-go]').forEach(el=>el.onclick=()=>go(el.dataset.go));$('pageSelect').onchange=()=>go($('pageSelect').value);
for(const id of ['viewMarket','viewIndustry','barMetric','xMetric','yMetric'])$(id).onchange=render;$('viewSearch').oninput=render;$('focusCompany').onchange=()=>pick($('focusCompany').value);
$('reset').onclick=()=>{for(const id of ['viewMarket','viewIndustry','viewSearch'])$(id).value='';$('barMetric').value='market_cap_eok';$('xMetric').value='roe_pct';$('yMetric').value='operating_margin_pct';code=rows[0]?.code||'';render();};
$('exportCsv').onclick=()=>{if(researchUI.isPage(page)){researchUI.csv();return;}const safe=v=>{let s=String(v??'');if(/^[\s\uFEFF]*[=+@\-]/.test(s)&&!/^[-+]?\d+(\.\d+)?$/.test(s.trim()))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};const csv=[['code','name','market','industry','price_date','financial_period',...keys],...scope().map(r=>[r.code,r.name,r.market,r.industry,meta.price_date,meta.financial_period,...keys.map(k=>val(r,k))])].map(r=>r.map(safe).join(',')).join('\r\n');const url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='investment_comparison.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
function reloadWithInputs(){
  try{
  const w=$('detailFrame').contentWindow;
  const state={mode:meta.data_mode,input:w?.INVESTMENT_GET_HOLDINGS?.(),policy:w?.INVESTMENT_GET_POLICY?.(),draft:w?.INVESTMENT_GET_DRAFT?.(),
    page,code,research:researchUI.state(),companyDetail:companyUI.state(),filters:Object.fromEntries(['viewMarket','viewIndustry','viewSearch','barMetric','xMetric','yMetric'].map(id=>[id,$(id).value]))};
  sessionStorage.setItem(handoffKey,JSON.stringify(state));location.reload();}
  catch{$('priceRefreshStatus').textContent='새 가격은 저장됐습니다. 입력을 내보낸 뒤 이 페이지를 다시 열어주세요.';}
}
let priceTimer=null,pricePending=false,autoWasRunning=false;
const financialJobs=new Map();
const companyViews=new Map();
window.INVESTMENT_LOAD_COMPANY_VIEW=async(c,force=false)=>{
 if(!INVESTMENT_LIVE?.lazy_company_views)return false;
 if(!force&&companyViews.has(c))return companyViews.get(c);
 const pending=(async()=>{
  const response=await fetch('/company-view?code='+encodeURIComponent(c),{headers:{'X-Dashboard-Token':INVESTMENT_LIVE.token},cache:'no-store'});
  if(!response.ok)throw Error('기업 자료 연결 대기');
  const data=await response.json(),row=researchRows.find(r=>r.code===c);
  if(!row||data.code!==c||data.name!==row.name||data.market!==row.market)throw Error('기업 식별 확인 필요');
  WORKSPACE_DATA.financial_tables[c]=data.table;WORKSPACE_DATA.company_details[c]=data.model;
  const common=data.model?.common_financial,rr=researchRows.find(r=>r.code===c);
  if(rr&&data.model?.collection_health){rr.collection_health=data.model.collection_health;researchUI.updateHealth(c,data.model.collection_health);}
  if(common&&rr){researchUI.updateCommon(c,common);rr.common_financial=common;Object.assign(rr.metrics,common.metrics);Object.assign(rr.metric_details||(rr.metric_details={}),common.metric_details);const raw=researchSnap.companies.find(r=>r.code===c);if(raw){raw.common_financial=common;Object.assign(raw.metrics,common.metrics);Object.assign(raw.metric_details||(raw.metric_details={}),common.metric_details);}const f=researchData.rows[c].fundamental;Object.assign(f.metrics,common.metrics);Object.assign(f.metric_details||(f.metric_details={}),common.metric_details);f.period=common.period;f.basis=common.basis;}
  if(researchData.rows?.[c]?.technical)Object.assign(researchData.rows[c].technical,{series:data.series,series_pending:false,trend_analysis:data.trend_analysis});
  if(code===c&&['brief','trend'].includes(page))researchUI.render(page);if(page==='advanced')advancedUI.render();
  return true;
 })();
 companyViews.set(c,pending);
 try{return await pending;}catch{companyViews.delete(c);if(code===c&&$('financialLoadStatus'))$('financialLoadStatus').textContent='기업 자료 연결 대기 · 다시 선택하거나 새로고침하세요.';return false;}
};
window.INVESTMENT_ENSURE_FINANCIALS=c=>{
 if(!INVESTMENT_LIVE?.company_financials)return;
 const show=message=>{if(page==='brief'&&code===c&&$('financialLoadStatus'))$('financialLoadStatus').textContent=message;};
 if(financialJobs.has(c)){show(financialJobs.get(c));return;}
 financialJobs.set(c,'공개 연결 재무자료 확인 중…');show(financialJobs.get(c));
 async function check(start=true){
  try{
   const r=await fetch('/company-financials?code='+encodeURIComponent(c),{method:start?'POST':'GET',headers:{'X-Dashboard-Token':INVESTMENT_LIVE.token},cache:'no-store'});
   if(!r.ok)throw Error();const job=await r.json();
   if(job.status==='cached'){
    financialJobs.set(c,'저장 재무자료 확인 완료');show(financialJobs.get(c));
    if(INVESTMENT_LIVE?.lazy_company_views){await window.INVESTMENT_LOAD_COMPANY_VIEW(c,true);return;}
    try{const key='investment-financial-cache-'+c;if(sessionStorage.getItem(key)!==job.cache_revision){sessionStorage.setItem(key,job.cache_revision);reloadWithInputs();}}
    catch{show('재무자료는 저장됐습니다. 입력을 보존한 뒤 새로고침하세요.');}return;
   }
   if(job.status==='complete'){financialJobs.set(c,'재무자료 저장 완료');if(INVESTMENT_LIVE?.lazy_company_views)await window.INVESTMENT_LOAD_COMPANY_VIEW(c,true);else reloadWithInputs();return;}
   const message=job.status==='failed'?job.message:job.status==='busy'?'다른 기업 조회 완료 후 재무자료를 확인합니다.':`DART 연결 재무자료 조회 중 ${job.completed||0}/${job.total||'—'}`;
   financialJobs.set(c,message);show(message);
   if(['running','busy','idle'].includes(job.status))setTimeout(()=>check(job.status!=='running'),2000);
  }catch{financialJobs.set(c,'재무자료 연결 대기 · 기존 자료 유지');show(financialJobs.get(c));}
 }
 check();
};
try{pricePending=sessionStorage.getItem('investment-daily-pending')==='1';}catch{}
function showPriceJob(job){
  const running=job.status==='running';$('refreshData').disabled=running;
  $('refreshData').textContent=running?'조회 중…':'새로고침';
  if(running)$('priceRefreshStatus').textContent='최신 제공 가격 조회 중…';
  else if(job.status==='complete'){
    $('priceRefreshStatus').textContent=`최근 가격 조회 ${job.retrieved_at||'완료'} · ${job.updated_companies}개 · 시세시각/지연 미확인`;
    if(pricePending){pricePending=false;try{sessionStorage.removeItem('investment-daily-pending');}catch{}reloadWithInputs();}
  }else if(job.status==='failed'){
    pricePending=false;try{sessionStorage.removeItem('investment-daily-pending');}catch{}
    $('priceRefreshStatus').textContent=job.message||'가격 조회 실패 · 기존 자료 유지';
  }
  if(running){clearTimeout(priceTimer);priceTimer=setTimeout(pollPrices,2000);}
}
async function pollPrices(){
  try{const r=await fetch('/quote-refresh',{headers:{'X-Dashboard-Token':INVESTMENT_LIVE.token},cache:'no-store'});if(!r.ok)throw Error();showPriceJob(await r.json());}
  catch{$('priceRefreshStatus').textContent='가격 조회 상태 연결 대기 · 기존 화면 유지';priceTimer=setTimeout(pollPrices,5000);}
}
async function pollDaily(){
  let delay=60000;
  try{
    const r=await fetch('/market-refresh',{headers:{'X-Dashboard-Token':INVESTMENT_LIVE.token},cache:'no-store'});if(!r.ok)throw Error();
    const job=await r.json();
    if(job.status==='running'){
      autoWasRunning=true;delay=5000;
      if(!pricePending)$('priceRefreshStatus').textContent=`일별 종가 자동 갱신 ${job.completed||0}/${job.total||'—'} · 새로고침으로 최신 제공 가격을 조회할 수 있습니다.`;
    }else if(job.status==='complete'&&!pricePending&&job.updated_companies>0&&(autoWasRunning||job.target_date!==$('asof').textContent)){
      autoWasRunning=false;reloadWithInputs();
    }else if(job.status==='complete'&&!pricePending){$('priceRefreshStatus').textContent=`일별 종가 ${job.target_date||'기준일 대기'} · 일부 실패 ${job.failed||0}개${job.failed?' · 기존 자료 유지·재시도 예정':''} · 장후18:30 이후 당일 일봉 확인`;}else if(job.status==='failed'&&!pricePending)$('priceRefreshStatus').textContent='일별 자동 갱신 대기 · 기존 종가 유지 · 잠시 후 재시도';
  }catch{if(!pricePending)$('priceRefreshStatus').textContent='일별 자동 갱신 연결 대기 · 기존 자료 유지';}
  setTimeout(pollDaily,delay);
}
if(INVESTMENT_LIVE?.daily_prices)pollDaily();
if(INVESTMENT_LIVE?.latest_prices)pollPrices();
let financialRevision=INVESTMENT_LIVE?.financial_revision;
const financialVersions=INVESTMENT_LIVE?.financial_versions||{};
async function pollFinancials(){
 let delay=60000;
 try{
  const r=await fetch('/financial-monitor',{headers:{'X-Dashboard-Token':INVESTMENT_LIVE.token},cache:'no-store'});
  if(!r.ok)throw Error();const job=await r.json();
  if(job.status==='running'){delay=15000;$('financialRefreshStatus').textContent=`재무 자동 확인 ${job.completed||0}/${job.total||'—'} · 반영 ${job.updated||0} · 일부 기간 대기 ${job.partial||0} · ${job.failure_label||'미확보'} ${job.failed||0}`;}
  else if(job.status==='complete')$('financialRefreshStatus').textContent=`재무 공시 확인 ${job.checked_on} · 반영 ${job.updated||0} · 7% 미만·미변경 ${job.deferred||0} · 일부 기간 대기 ${job.partial||0} · ${job.failure_label||'미확보'} ${job.failed||0}`;
  else if(job.status==='failed')$('financialRefreshStatus').textContent=job.message;
  const selectedRevision=job.versions?.[code];
  const selectedChanged=['brief','company'].includes(page)&&selectedRevision&&selectedRevision!==financialVersions[code];
  if(selectedChanged||(job.status==='complete'&&job.revision&&job.revision!==financialRevision)){
   financialRevision=job.revision;if(selectedRevision)financialVersions[code]=selectedRevision;reloadWithInputs();
  }
 }catch{$('financialRefreshStatus').textContent='재무 자동 확인 연결 대기 · 기존 자료 유지';}
 setTimeout(pollFinancials,delay);
}
if(INVESTMENT_LIVE?.financial_monitor)pollFinancials();
$('refreshData').onclick=async()=>{
  if(!INVESTMENT_LIVE)return;
  const button=$('refreshData');button.disabled=true;button.textContent='확인 중…';
  try{
    const response=await fetch('/refresh',{method:'POST',headers:{'X-Dashboard-Token':INVESTMENT_LIVE.token}});
    if(!response.ok)throw Error('갱신 요청 실패');
    const result=await response.json();liveReceipt=result.receipt;
    if(INVESTMENT_LIVE.latest_prices){
      const r=await fetch('/quote-refresh',{method:'POST',headers:{'X-Dashboard-Token':INVESTMENT_LIVE.token}});
      if(!r.ok)throw Error('가격 갱신 요청 실패');
      pricePending=true;try{sessionStorage.setItem('investment-daily-pending','1');}catch{}
      showPriceJob(await r.json());return;
    }
    if(result.snapshot_id&&result.snapshot_id!==INVESTMENT_LIVE.snapshot_id){
      const w=$('detailFrame').contentWindow;
      const state={mode:meta.data_mode,input:w?.INVESTMENT_GET_HOLDINGS?.(),policy:w?.INVESTMENT_GET_POLICY?.(),
                   page,code,research:researchUI.state(),companyDetail:companyUI.state(),filters:Object.fromEntries(['viewMarket','viewIndustry','viewSearch','barMetric','xMetric','yMetric'].map(id=>[id,$(id).value]))};
      try{sessionStorage.setItem(handoffKey,JSON.stringify(state));}
      catch{ $('sourceNotice').textContent+=' · 새 자료가 저장됐습니다. 보유 입력을 JSON으로 내보낸 뒤 이 페이지를 다시 열어주세요.';return;}
      location.reload();return;
    }
    render();
  }catch{ $('sourceNotice').textContent+=' · 연결 실패 · 현재 저장자료를 계속 표시합니다.';}
  finally{if(!pricePending){button.disabled=false;button.textContent='새로고침';}}
};
$('homeSearch').onsubmit=e=>{e.preventDefault();researchUI.search($('homeQuery').value.trim());go('finder');};
$('print').onclick=()=>window.print();
if(handoff?.filters){for(const [id,value] of Object.entries(handoff.filters))if($(id)&&[...($(id).options||[])].some(o=>o.value===value)||$(id)?.tagName==='INPUT')$(id).value=value;}
render();
if(handoff?.code&&allRows.some(r=>r.code===handoff.code))code=handoff.code;else{try{const savedCode=sessionStorage.getItem('investment-current-company');if(allRows.some(r=>r.code===savedCode))code=savedCode;}catch{}}
let restoreAdvanced=false;try{restoreAdvanced=sessionStorage.getItem('investment-advanced-open')==='1';}catch{}
let savedPage=null;try{savedPage=sessionStorage.getItem('investment-current-page');}catch{}
recommendationUI.load();
go(handoff?.page||(pages.some(p=>p[1]===savedPage)?savedPage:restoreAdvanced?'advanced':'home'));
})();
