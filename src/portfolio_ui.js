/* Browser-only UI. All imported holdings stay in memory until explicit export. */
'use strict';
(() => {
  const P=PortfolioEngine;
  const marketInput=window.INVESTMENT_HOLDINGS_INPUT||null;
  const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  let data=P.empty(today()),proposal=null,detailCode='';
  window.INVESTMENT_GET_HOLDINGS=()=>P.clone(data);
  window.INVESTMENT_GET_POLICY=()=>policy();
  window.INVESTMENT_RESTORE_SESSION=(input,savedPolicy)=>{
    let result='market_updated';
    try{apply(input);}catch{
      // Keep reviewed input when an issuer identity changed; do not attach new prices.
      P.validate(input);data=P.clone(input);proposal=null;detailCode='';
      $('pCash').value=data.cash_krw??'';refresh();result='identity_review_needed';
    }
    if(savedPolicy){
      for(const [id,key] of [['pMax','maxCompanies'],['pCompanyCap','companyCapPct'],['pSectorCap','sectorCapPct'],
          ['pGroupCap','groupCapPct'],['pCashMin','minCashPct'],['pShock','stressShockPct'],
          ['pLossLimit','stressLossLimitPct'],['pPriceAge','maxPriceAgeDays'],['pReviewAge','maxReviewAgeDays']]){
        $(id).value=savedPolicy[key]??'';
      }
      $('pConfirm').checked=savedPolicy.policyConfirmed===true;
      refresh();
    }
    return result;
  };
  const n=id=>$(id).value.trim()===''?null:Number($(id).value);
  function policy(){return P.cleanPolicy({maxCompanies:n('pMax'),companyCapPct:n('pCompanyCap'),sectorCapPct:n('pSectorCap'),groupCapPct:n('pGroupCap'),minCashPct:n('pCashMin'),stressShockPct:n('pShock'),stressLossLimitPct:n('pLossLimit'),maxPriceAgeDays:n('pPriceAge'),maxReviewAgeDays:n('pReviewAge'),policyConfirmed:$('pConfirm').checked});}
  function tag(code){return `<span class="tag ${code==='HOLD'?'good':code==='SELL'?'fail':'warning'}">${esc(P.LABEL[code]||code)}</span>`;}
  function bindDetails(root){$(root).querySelectorAll('[data-review-detail]').forEach(b=>b.addEventListener('click',()=>{detailCode=b.dataset.reviewDetail;activate('holdings');renderDetail();$('pDetail').scrollIntoView({behavior:'smooth',block:'start'});}));}
  function renderHoldings(p){
    const result=P.reviewHoldings(data,p),b=result.book;
    $('pMode').textContent=data.mode==='fixture'?'가상 테스트 · 실제 투자 자료 아님':data.holdings.length||data.research.length?'사용자 입력 · 원문 대조 미실행':'보유·연구 입력 대기';
    $('pScope').innerHTML=[`평가 기준일 ${data.as_of}`,data.market_data_as_of?`저장 시장자료 ${data.market_data_as_of} · 가격 기한 검사 적용 · 공시 검토 별도`:`가격·공시 최신성 자동확인 없음`,`후보 ${data.research.length}개 / 보유 ${data.holdings.length}개`,`스냅샷 ${data.snapshot_id}`].map(s=>`<span>${esc(s)}</span>`).join('');
    if(data.as_of!==today())$('pScope').innerHTML+=`<span class="p-date-warn">현재 날짜가 아닌 입력 평가일의 검토입니다.</span>`;
    $('pValue').textContent=fmt(b.total_krw,'원',0);
    $('pReviewCount').textContent=data.holdings.length?String(result.rows.filter(r=>['SELL','REVIEW','REDUCE'].includes(r.opinion)).length):'—';
    $('pWaitCount').textContent=data.holdings.length?String(result.rows.filter(r=>r.opinion==='WAIT').length):'—';
    $('pHoldBody').innerHTML=result.rows.length?result.rows.map(r=>`<tr><td class="left"><b>${esc(r.name)}</b><div class="sub">${esc(r.code)}</div></td><td>${fmt(r.quantity,'',0)}</td><td>${fmt(r.value_krw,'',0)}</td><td>${fmt(r.pnl_pct,'%',2)}</td><td>${fmt(r.weight_pct,'%',2)}</td><td class="left">${tag(r.opinion)}</td><td class="left">${esc(r.portfolio_action)}</td><td><button class="small" data-review-detail="${esc(r.code)}">근거 보기</button></td></tr>`).join(''):'<tr><td colspan="8" style="text-align:center;padding:40px">보유목록을 직접 입력하거나 JSON 파일을 가져오세요. 실제 보유종목은 포함되어 있지 않습니다.</td></tr>';
    $('pBookNote').textContent=b.complete?'비중의 분모는 입력한 보유종목 평가액과 현금입니다. 동일 기업 여러 주식은 기업 한도 판단 시 합산합니다. 일부 자료만 입력하면 전체 계좌나 전체 재산을 대표하지 않습니다. 비중 상한은 포트폴리오 탭의 개발 가정이며 적합성이 검증된 기준이 아닙니다.':'현금 또는 일부 보유종목의 유효 가격이 없어 전체 평가액·비중을 계산하지 않습니다. 확인된 종목만으로 비중을 100% 재정규화하지 않습니다.';
    bindDetails('pHoldBody');
    renderDetail();
    return result;
  }
  function renderDetail(){
    const r=data.research.find(r=>r.code===detailCode);
    if(!detailCode){$('pDetail').innerHTML='<h3>판단 근거</h3><p class="hint">보유목록의 근거 버튼을 누르면 투자 논리·반대 근거·출처·재검토 조건을 확인할 수 있습니다.</p>';return;}
    if(!r){$('pDetail').innerHTML=`<h3>${esc(detailCode)} · 판단 보류</h3><p class="hint">대응하는 가격·연구 근거가 없습니다. 보유했다고 좋은 기업으로 가정하지 않습니다.</p>`;return;}
    const v=r.review,c=P.companyReview(r,data.as_of,policy());
    const events=(r.pending_events||[]).filter(e=>e.published_on<=data.as_of);
    $('pDetail').innerHTML=`<div class="card-head"><h3>${esc(r.name)} · 근거와 변경 조건</h3><span class="sub">연구 검토 ${esc(v.reviewed_on||'미확인')} / ${esc(v.financial_period)}</span></div><div class="p-block">${tag(c.opinion)}<p class="p-ev">${esc(c.reasons.join(' / '))}</p>${c.blockers.length?`<p class="hint">추가 확인: ${esc(c.blockers.join(' / '))}</p>`:''}<p class="hint">가격 ${fmt(r.price_krw,'원',0)} · 기준일 ${esc(r.price_date||'미확인')} · ${esc(r.price_source?.label||'가격 출처 미입력')}</p></div><div class="grid-two"><div><p class="p-ev"><b>긍정 근거</b></p>${v.positives.map(t=>`<p class="p-ev">${esc(t)}</p>`).join('')||'<p class="hint">미입력</p>'}</div><div><p class="p-ev"><b>반대 근거</b></p>${v.negatives.map(t=>`<p class="p-ev">${esc(t)}</p>`).join('')||'<p class="hint">미입력</p>'}</div></div><div class="p-block"><b>판단을 바꿀 조건</b><p class="p-ev">${esc(v.invalidation||'미입력')}</p><p class="sub">다음 검토 예정일 ${esc(v.next_review_on||'미입력')} · 예약 알림은 등록하지 않습니다.</p></div><div class="p-block"><b>근거 출처</b>${r.evidence.map(e=>`<p class="p-ev">${data.mode==='fixture'?esc(e.label):`<a href="${esc(e.url)}" target="_blank" rel="noopener noreferrer">${esc(e.label)}</a>`} · 이용가능일 ${esc(e.available_on)} · ${e.reviewed?'입력자가 확인 표시':'확인 대기'}</p>`).join('')||'<p class="hint">출처 없음</p>'}<p class="hint">출처 존재·내용의 정확성을 이 HTML이 외부에서 검증하지는 않습니다.</p></div>`;
    if(events.length)$('pDetail').innerHTML+=`<div class="p-block"><b>주요 공시·뉴스 재검토 필요</b>${events.map(e=>`<p class="p-ev"><a href="${esc(e.url)}" target="_blank" rel="noopener noreferrer">${esc(e.title)}</a> · ${esc(e.published_on)}</p>`).join('')}<p class="hint">기업 상세의 공시·뉴스 패널에서 원문과 투자 논리를 검토하세요. 제목만으로 매수·매도를 판정하지 않습니다.</p></div>`;
  }
  function renderProposal(){
    try{
      const checks=P.candidateChecks(data,policy()),ready=checks.filter(r=>r.ready).length;
      $('pReadiness').textContent=`입력 후보 ${checks.length}개 · 편입 조건 충족 ${ready}개 · 제외/확인 필요 ${checks.length-ready}개 · 최대 ${policy().maxCompanies}개 기업`;
    }catch(e){$('pReadiness').textContent='후보 검사: 구성 설정을 확인하세요.';}
    $('pAllocation').innerHTML='';$('pProposalBody').innerHTML='';$('pCashLabel').textContent='현금 —';$('pStress').innerHTML='';$('pExposure').innerHTML='';$('pRejected').innerHTML='';$('pUnselected').textContent='';
    $('pExportReport').disabled=!proposal;
    if(!proposal){$('pProposalTitle').textContent='입력과 설정 확인 대기';$('pProposalBadge').textContent='아직 계산하지 않음';$('pProposalNote').textContent='설정을 바꾸거나 입력 파일을 교체하면 이전 구성안은 해제됩니다. 조건을 확인한 뒤 계산하세요.';return;}
    const a=proposal;
    $('pProposalTitle').textContent=a.status==='MODEL_PROPOSAL'?`${a.items.length}개 기업 + 현금`:a.status==='CASH_ONLY'?'현재 조건의 편입 기업 0개':'조건·자료 확인 필요';
    $('pProposalBadge').textContent=data.mode==='fixture'?'가상 결과':'입력 기반 모의 결과';
    $('pProposalNote').textContent=a.message;
    $('pProposalBody').innerHTML=a.items.map(r=>`<tr><td class="left"><b>${esc(r.name)}</b><div class="sub">${esc(r.code)}</div></td><td class="left">${esc(r.sector)}</td><td><b>${fmt(r.weight_pct,'%',2)}</b></td><td>${r.existing?'보유 중':'신규 후보'}</td><td><button class="small" data-review-detail="${esc(r.code)}">근거</button></td></tr>`).join('');
    if(a.cash_pct!==null){
      $('pCashLabel').textContent=`현금 ${fmt(a.cash_pct,'%',2)} · 빈 자리를 억지로 채우지 않습니다.`;
      $('pAllocation').innerHTML=`<div class="p-bar" aria-label="주식과 현금 비중">${a.items.map(r=>`<span style="width:${r.weight_pct}%" title="${esc(r.name)} ${r.weight_pct}%"></span>`).join('')}<span style="width:${a.cash_pct}%" title="현금 ${a.cash_pct}%"></span></div>`;
      const p=a.policy,shock=P.stress(a.items,p.stressShockPct),worse=P.stress(a.items,-50);
      $('pStress').innerHTML=`<div class="p-metric"><span>주식 동반 ${fmt(p.stressShockPct,'%')} 가정</span><b>${fmt(shock,'%',2)}</b></div><div class="p-metric"><span>별도 하락 -50% 가정</span><b>${fmt(worse,'%',2)}</b></div><p class="hint">첫 시나리오 기준 ${fmt(p.stressLossLimitPct,'%')}를 주식 비중에 반영했습니다. 실제 손실 상한이 아닙니다.</p>`;
    }
    const sectors=a.sector_weights||{},groups=a.group_weights||{};
    $('pExposure').innerHTML=Object.entries(sectors).map(([k,v])=>`<div class="p-metric"><span>${esc(k)}</span><b>${fmt(v,'%',2)}</b></div>`).join('')+`<p class="hint">공통 위험군: ${Object.entries(groups).map(([k,v])=>`${esc(k)} ${fmt(v,'%',2)}`).join(' / ')||'없음'}</p>`;
    $('pRejected').innerHTML=a.rejected.map(r=>`<div class="p-block"><b>${esc(r.name)} · ${esc(r.code)}</b><p class="hint">${esc(r.reasons.join(' / '))}</p></div>`).join('')||'<p class="hint">현재 표시할 제외 사유가 없습니다.</p>';
    if(a.unselected_holdings?.length)$('pUnselected').textContent=`모의안 미편입 보유종목: ${a.unselected_holdings.join(', ')}. 이는 자동 매도 의견이 아닙니다. 보유종목 점검에서 개별 근거를 확인하세요. 현재 보유목록은 유지됩니다.`;
    bindDetails('pProposalBody');
  }
  function refresh(){try{renderHoldings(policy());renderProposal();}catch(e){proposal=null;renderProposal();$('pHoldBody').innerHTML='<tr><td colspan="8">설정 오류로 재계산을 보류합니다.</td></tr>';$('pValue').textContent='—';toast('설정 검사: '+e.message);}}
  function apply(x){P.validate(x);data=marketInput&&x.mode==='user_input'?P.attachMarket(x,marketInput):P.clone(x);proposal=null;detailCode='';$('pConfirm').checked=false;$('pCash').value=data.cash_krw??'';refresh();}
  function protectReplace(){return !data.holdings.length&&!data.research.length||confirm('현재 입력을 교체합니다. 필요한 내용은 먼저 내보내세요. 원본 파일은 변경하지 않습니다.');}
  function report(){
    const h=P.reviewHoldings(data,policy()),a=proposal;
    let s=`# INVESTMENT 보유·포트폴리오 검토\n\n평가일: ${data.as_of}\n데이터 모드: ${data.mode==='fixture'?'가상 테스트 (실제 기업·수치 아님)':'사용자 입력 (원문 자동 검증 미실행)'}\n스냅샷: ${data.snapshot_id}\n엔진: ${P.VERSION}\n\n의견은 의사결정 보조이며 매매 지시·수익 보장·손실 한도 보장이 아닙니다.\n\n## 보유종목\n`;
    for(const r of h.rows){s+=`\n### ${r.name} (${r.code})\n기업 의견: ${r.label}\n비중 의견: ${r.portfolio_action}\n현재 비중: ${fmt(r.weight_pct,'%',2)}\n판정 근거: ${r.reasons.join(' / ')}\n`;if(r.research){s+=`긍정: ${r.research.review.positives.join(' / ')}\n반대: ${r.research.review.negatives.join(' / ')}\n변경 조건: ${r.research.review.invalidation}\n`;for(const e of r.research.evidence)s+=`출처: ${e.label} | ${e.url} | ${e.available_on}\n`;}}
    s+='\n## 최대 5개 기업 모의 목표안\n';
    if(a){s+=`${a.message}\n`;for(const r of a.items){s+=`\n### ${r.name} (${r.code}) · ${r.weight_pct}%\n편입 이유: ${r.reasons.join(' / ')}\n가격 기준일: ${r.research.price_date}\n긍정: ${r.research.review.positives.join(' / ')}\n반대: ${r.research.review.negatives.join(' / ')}\n변경 조건: ${r.research.review.invalidation}\n`;for(const e of r.research.evidence)s+=`출처: ${e.label} | ${e.url} | ${e.available_on}\n`;}s+=`현금: ${fmt(a.cash_pct,'%',2)}\n\n고정 슬롯 균등배분이며 최적 기대수익 모형이 아닙니다. 미편입 보유종목을 자동 매도하지 않습니다.\n\n### 적용 설정\n\`\`\`json\n${JSON.stringify(a.policy,null,2)}\n\`\`\`\n`;}
    if(a&&a.cash_pct!==null)s+=`\n가정 시나리오: 주식 ${a.policy.stressShockPct}% / 구성안 ${fmt(P.stress(a.items,a.policy.stressShockPct),'%',2)}. 실제 손실 상한이 아닙니다.\n`;
    if(a?.rejected?.length)s+='\n제외·확인 대기: '+a.rejected.map(r=>`${r.name} (${r.code}): ${r.reasons.join(' / ')}`).join('\n')+'\n';
    s+='\n실제 시세·공시 수집, 계좌 연결, 외부 LLM 호출, 상관관계 추정, 거래비용, 자동 주문은 미구현입니다.\n';return s;
  }
  $('pImport').addEventListener('click',()=>$('pFile').click());
  $('pFile').addEventListener('change',async e=>{const f=e.target.files[0];if(!f)return;try{if(f.size>12*1024*1024)throw Error('12MB 이하 JSON만 지원합니다.');const x=JSON.parse(await f.text());P.validate(x);if(protectReplace()){apply(x);toast('입력 파일을 검사해 불러왔습니다. 원문 검증이나 실제 계좌 연결은 아닙니다.');}}catch(err){toast('보유·연구 불러오기 실패: '+err.message);}e.target.value='';});
  $('pTemplate').addEventListener('click',()=>download('holdings_research_empty.json',JSON.stringify(P.empty(today()),null,2)));
  $('pFixture').addEventListener('click',()=>{if(protectReplace()){apply(P.fixture());$('pLossLimit').value=25;toast('모든 기업·가격·출처가 허구인 테스트 예제입니다.');}});
  $('pExport').addEventListener('click',()=>download('holdings_research_private.json',JSON.stringify(data,null,2)));
  $('pClear').addEventListener('click',()=>{if(protectReplace()){apply(P.empty(today()));$('pJsonEditor').value='';toast('새 보유·연구 입력만 비웠습니다. 원본 파일과 기존 조건검색 자료는 유지합니다.');}});
  $('pLoadEditor').addEventListener('click',()=>{$('pJsonEditor').value=JSON.stringify(data,null,2);});
  $('pApplyEditor').addEventListener('click',()=>{try{apply(JSON.parse($('pJsonEditor').value));toast('형식 검사를 통과한 편집 내용을 적용했습니다.');}catch(e){toast('편집 적용 실패: '+e.message);}});
  $('pSaveHolding').addEventListener('click',()=>{try{const x=P.clone(data),code=$('pCode').value.trim(),h={code,quantity:n('pQty'),avg_cost_krw:n('pCost')};const i=x.holdings.findIndex(v=>v.code===code);if(i>=0)x.holdings[i]={...x.holdings[i],...h};else x.holdings.push(h);apply(x);toast('보유 입력을 반영했습니다. 연구 근거가 없으면 판단 보류입니다.');}catch(e){toast('보유 입력 실패: '+e.message);}});
  $('pDeleteHolding').addEventListener('click',()=>{const code=$('pCode').value.trim();if(!data.holdings.some(h=>h.code===code)){toast('보유목록에 없는 코드입니다.');return;}if(!confirm('보유 입력에서 이 종목을 제거할까요? 실제 주식 매도가 아닙니다.'))return;const x=P.clone(data);x.holdings=x.holdings.filter(h=>h.code!==code);apply(x);});
  $('pSaveCash').addEventListener('click',()=>{try{const x=P.clone(data);x.cash_krw=n('pCash');apply(x);toast('입력한 현금을 평가액에 반영했습니다.');}catch(e){toast('현금 입력 실패: '+e.message);}});
  for(const id of ['pMax','pCompanyCap','pSectorCap','pGroupCap','pCashMin','pShock','pLossLimit','pPriceAge','pReviewAge'])$(id).addEventListener('input',()=>{proposal=null;$('pConfirm').checked=false;refresh();});
  $('pConfirm').addEventListener('change',()=>{proposal=null;refresh();});
  $('pGenerate').addEventListener('click',()=>{try{proposal=P.propose(data,policy());renderHoldings(policy());renderProposal();}catch(e){proposal=null;renderProposal();toast('구성안 계산 실패: '+e.message);}});
  $('pExportReport').addEventListener('click',()=>download('INVESTMENT_Review_'+data.as_of+'.md',report(),'text/markdown;charset=utf-8'));
  if(marketInput){try{
    apply(window.INVESTMENT_INITIAL_HOLDINGS||marketInput);
    if(window.INVESTMENT_INITIAL_POLICY){
      const initial=P.cleanPolicy(window.INVESTMENT_INITIAL_POLICY);
      for(const [id,key] of Object.entries({pMax:'maxCompanies',pCompanyCap:'companyCapPct',pSectorCap:'sectorCapPct',pGroupCap:'groupCapPct',pCashMin:'minCashPct',pShock:'stressShockPct',pLossLimit:'stressLossLimitPct',pPriceAge:'maxPriceAgeDays',pReviewAge:'maxReviewAgeDays'}))$(id).value=initial[key]??'';
      $('pConfirm').checked=initial.policyConfirmed;
      if(initial.policyConfirmed)proposal=P.propose(data,initial);
      renderHoldings(initial);renderProposal();
    }
    activate('holdings');
  }catch(e){toast('저장 시장자료 연결 실패: '+e.message);refresh();}}
  else refresh();
})();
