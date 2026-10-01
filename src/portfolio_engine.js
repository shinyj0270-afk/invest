/* Pure, deterministic review engine. No network, trading, or return prediction. */
'use strict';
const PortfolioEngine = (() => {
  const VERSION = '0.2.1';
  const LABEL = Object.freeze({HOLD:'보유 검토',REDUCE:'비중 축소 검토',SELL:'매도 검토',REVIEW:'재검토',WAIT:'판단 보류'});
  // These are configurable engineering examples, NOT a validated investment policy.
  const DEFAULT = Object.freeze({maxCompanies:5,companyCapPct:25,sectorCapPct:40,groupCapPct:40,minCashPct:20,maxPriceAgeDays:4,maxReviewAgeDays:120,stressShockPct:-30,stressLossLimitPct:null,policyConfirmed:false});
  const num = n => typeof n === 'number' && Number.isFinite(n);
  const text = v => typeof v === 'string' && v.trim().length > 0;
  const own = (o,k) => Object.prototype.hasOwnProperty.call(o,k);
  function dateOK(s) {return typeof s==='string' && /^\d{4}-\d{2}-\d{2}$/.test(s) && !Number.isNaN(Date.parse(s+'T00:00:00Z')) && new Date(s+'T00:00:00Z').toISOString().slice(0,10)===s;}
  function age(a,b) {return (Date.parse(a+'T00:00:00Z')-Date.parse(b+'T00:00:00Z'))/86400000;}
  function urlOK(s){try{const u=new URL(s);return ['https:','http:'].includes(u.protocol)&&!!u.hostname&&!u.username&&!u.password;}catch{return false;}}
  function amount(n,nullable=false){return (nullable&&n===null)||(num(n)&&n>=0&&n<=Number.MAX_SAFE_INTEGER);}
  function clone(v){return JSON.parse(JSON.stringify(v));}
  function cleanPolicy(p={}) {
    const q={...DEFAULT,...p};
    if(!Number.isInteger(q.maxCompanies)||q.maxCompanies<1||q.maxCompanies>5)throw Error('기업 수 상한은 1~5의 정수입니다.');
    for(const k of ['companyCapPct','sectorCapPct','groupCapPct'])if(!num(q[k])||q[k]<=0||q[k]>100)throw Error(k+': 0 초과 100 이하의 비율이 필요합니다.');
    if(!num(q.minCashPct)||q.minCashPct<0||q.minCashPct>100)throw Error('최소 현금은 0~100%입니다.');
    for(const k of ['maxPriceAgeDays','maxReviewAgeDays'])if(!Number.isInteger(q[k])||q[k]<0||q[k]>366)throw Error(k+': 0~366일의 정수가 필요합니다.');
    if(!num(q.stressShockPct)||q.stressShockPct>=0||q.stressShockPct< -100)throw Error('주식 동반 하락 가정은 -100 이상 0 미만입니다.');
    if(q.stressLossLimitPct!==null&&(!num(q.stressLossLimitPct)||q.stressLossLimitPct<=0||q.stressLossLimitPct>100))throw Error('시나리오 손실 기준은 0 초과 100 이하입니다.');
    if(typeof q.policyConfirmed!=='boolean')throw Error('설정 확인 여부가 필요합니다.');
    return q;
  }
  function validate(x){
    if(!x||x.schema_version!=='holdings-portfolio-0.1')throw Error('보유·포트폴리오 schema_version이 맞지 않습니다.');
    if(!['fixture','user_input'].includes(x.mode))throw Error('fixture 또는 user_input 모드가 필요합니다.');
    if(!dateOK(x.as_of)||!text(x.snapshot_id))throw Error('정확한 평가일과 snapshot_id가 필요합니다.');
    if(!amount(x.cash_krw,true))throw Error('현금은 0 이상의 원 단위 숫자 또는 null입니다.');
    if(!Array.isArray(x.holdings)||x.holdings.length>500||!Array.isArray(x.research)||x.research.length>3000)throw Error('holdings 500개 / research 3,000개 이하 배열이 필요합니다.');
    const codes=new Set();
    for(const h of x.holdings){
      if(!/^\d{6}$/.test(h.code)||typeof h.code!=='string'||codes.has(h.code))throw Error('보유 종목코드는 중복 없는 6자리 문자열입니다.');
      codes.add(h.code);
      if(!Number.isSafeInteger(h.quantity)||h.quantity<=0||!amount(h.avg_cost_krw,true))throw Error('보유 수량은 양의 안전한 정수, 매입가는 0 이상 또는 null입니다.');
      if(h.thesis_note!=null&&(typeof h.thesis_note!=='string'||h.thesis_note.length>4000))throw Error('투자 메모는 4,000자 이하입니다.');
    }
    codes.clear();
    const enums={thesis:['intact','weakened','broken','unknown'],business:['improving','stable','deteriorating','unknown'],finance:['sound','concern','critical','unknown'],valuation:['attractive','fair','stretched','unknown'],material_risk:['clear','unresolved','confirmed','unknown']};
    for(const r of x.research){
      if(typeof r.code!=='string'||!/^\d{6}$/.test(r.code)||codes.has(r.code))throw Error('연구 종목코드는 중복 없는 6자리 문자열입니다.');
      codes.add(r.code);
      for(const k of ['issuer_id','name','market','security_type','analysis_profile'])if(!text(r[k])||r[k].length>200)throw Error(r.code+': '+k+'가 필요합니다.');
      for(const k of ['sector','risk_group'])if(r[k]!==null&&(!text(r[k])||r[k].length>200))throw Error(k+'는 문자열 또는 null입니다.');
      if(!amount(r.price_krw,true)||r.price_krw===0)throw Error('현재가는 양수 또는 null입니다.');
      if(r.price_date!==null&&!dateOK(r.price_date))throw Error('price_date 형식 오류');
      if(!r.review||typeof r.review!=='object')throw Error(r.code+': review가 필요합니다.');
      for(const [k,values] of Object.entries(enums))if(!values.includes(r.review[k]))throw Error(r.code+': '+k+' 상태 오류');
      if(r.review.reviewed_on!==null&&!dateOK(r.review.reviewed_on))throw Error('검토일 형식 오류');
      if(r.review.next_review_on!==null&&!dateOK(r.review.next_review_on))throw Error('다음 검토일 형식 오류');
      if(!text(r.review.financial_period))throw Error('재무 보고기간을 표시해야 합니다.');
      for(const k of ['positives','negatives'])if(!Array.isArray(r.review[k])||r.review[k].length>12||r.review[k].some(v=>!text(v)||v.length>2000))throw Error('긍정·반대 근거는 12개 이하 문자열 배열입니다.');
      if(typeof r.review.invalidation!=='string'||r.review.invalidation.length>4000)throw Error('판단을 바꿀 조건을 문자열로 입력하세요.');
      if(!Array.isArray(r.evidence)||r.evidence.length>30)throw Error('근거는 30개 이하 배열입니다.');
      if(own(r,'pending_events')){
        if(!Array.isArray(r.pending_events)||r.pending_events.length>100)throw Error('미확인 이벤트는 100개 이하 배열입니다.');
        const eventIds=new Set();
        for(const e of r.pending_events){
          if(!e||!text(e.id)||eventIds.has(e.id)||!text(e.title)||e.title.length>1000||!urlOK(e.url)||!dateOK(e.published_on))throw Error('공시·뉴스 이벤트 형식 오류');
          eventIds.add(e.id);
        }
      }
      const ids=new Set();
      for(const e of r.evidence){
        if(!text(e.id)||ids.has(e.id)||!text(e.label)||!urlOK(e.url)||!dateOK(e.available_on)||typeof e.reviewed!=='boolean')throw Error('근거 ID·이름·http(s) URL·이용가능일·사용자 확인 여부를 검사하세요.');
        ids.add(e.id);
      }
      if(r.price_source!==null){
        const source=r.price_source;
        const valid=source&&text(source.label)&&(source.kind==='local_snapshot'
          ? /^[a-f0-9]{64}$/.test(source.snapshot_id||'') && !own(source,'url')
          : source.kind==='manual_input' ? (!own(source,'url') || urlOK(source.url)) : urlOK(source.url));
        if(!valid)throw Error('가격 출처 형식 오류');
      }
    }
    return x;
  }
  function evidenceBlockers(r,asOf,p){
    if(!r)return ['보유종목에 대응하는 연구 입력 없음'];
    const b=[];
    if((r.pending_events||[]).some(e=>e.published_on<=asOf))b.push('주요 공시·뉴스 재검토 필요');
    if(!['KOSPI','KOSDAQ'].includes(r.market)||r.security_type!=='ordinary'||r.analysis_profile!=='nonfinancial')b.push('비금융 보통주 외 별도 분석 필요');
    if(!r.evidence.length||r.evidence.some(e=>!e.reviewed||e.available_on>asOf))b.push('근거 미확인 또는 평가일 이후 공개된 근거');
    const v=r.review;
    if(!v.reviewed_on||v.reviewed_on>asOf||age(asOf,v.reviewed_on)>p.maxReviewAgeDays)b.push('연구 검토일 누락·미래·설정 기한 초과');
    if(v.reviewed_on && r.evidence.some(e=>e.available_on>v.reviewed_on))b.push('근거 공개일보다 앞선 연구 검토일');
    if(!v.positives.length||!v.negatives.length||!text(v.invalidation))b.push('긍정·반대 근거 또는 판단 변경 조건 미입력');
    return b;
  }
  function priceBlockers(r,asOf,p){
    if(!r)return ['가격 입력 없음'];
    const b=[];
    if(!num(r.price_krw)||r.price_krw<=0||!r.price_date||r.price_date>asOf||age(asOf,r.price_date)>p.maxPriceAgeDays)b.push('가격 누락·미래·설정 기한 초과');
    if(!r.price_source)b.push('가격 출처 미입력');
    return b;
  }
  function companyReview(r,asOf,p){
    const blockers=evidenceBlockers(r,asOf,p);
    if(!r)return {code:null,opinion:'WAIT',label:LABEL.WAIT,blockers,reasons:blockers};
    const v=r.review;
    // A verified adverse event stays visible even when unrelated inputs are missing.
    const criticalBlockers=blockers.filter(b=>!b.startsWith('긍정·반대')&&b!=='주요 공시·뉴스 재검토 필요');
    if(!criticalBlockers.length&&(v.thesis==='broken'||v.finance==='critical'||v.material_risk==='confirmed')){
      const reasons=[];
      if(v.thesis==='broken')reasons.push('검토 입력상 최초 투자 논리 훼손');
      if(v.finance==='critical')reasons.push('검토 입력상 중대한 재무 위험');
      if(v.material_risk==='confirmed')reasons.push('검토 입력상 중대 위험 확인');
      return {code:r.code,opinion:'SELL',label:LABEL.SELL,blockers:[...blockers,...priceBlockers(r,asOf,p)],reasons:[...reasons,'체결 가능성·거래정지·가격은 별도 확인; 자동 매도 아님']};
    }
    const missing=Object.keys({thesis:1,business:1,finance:1,valuation:1,material_risk:1}).filter(k=>v[k]==='unknown');
    if(missing.length)blockers.push('분석 상태 미확인: '+missing.join(', '));
    blockers.push(...priceBlockers(r,asOf,p));
    if(blockers.length)return {code:r.code,opinion:'WAIT',label:LABEL.WAIT,blockers,reasons:blockers};
    if(v.thesis==='weakened'||v.finance==='concern'||v.business==='deteriorating'||v.material_risk==='unresolved')return {code:r.code,opinion:'REVIEW',label:LABEL.REVIEW,blockers:[],reasons:['투자 논리·사업·재무 또는 미해결 위험을 재검토']};
    if(v.valuation==='stretched')return {code:r.code,opinion:'REDUCE',label:LABEL.REDUCE,blockers:[],reasons:['사업 평가와 별개로 검토 입력상 가치평가 부담']};
    return {code:r.code,opinion:'HOLD',label:LABEL.HOLD,blockers:[],reasons:['입력 근거상 투자 논리 유지, 사업·재무 상태 양호','현재 수익률이나 매입가가 아닌 연구 상태를 기준으로 판정']};
  }
  function bookSummary(x,p){
    const map=new Map(x.research.map(r=>[r.code,r]));
    let total=x.cash_krw,complete=x.cash_krw!==null;
    const missing=[];
    const positions=x.holdings.map(h=>{
      const r=map.get(h.code),bad=priceBlockers(r,x.as_of,p);
      let value=!bad.length?h.quantity*r.price_krw:null;
      if(value!==null&&(!num(value)||value>Number.MAX_SAFE_INTEGER))value=null;
      if(value===null){complete=false;missing.push(h.code);}
      else if(total!==null)total+=value;
      const cost=h.avg_cost_krw===null?null:h.quantity*h.avg_cost_krw;
      const usableCost=cost!==null&&num(cost)&&cost<=Number.MAX_SAFE_INTEGER?cost:null;
      return {...h,name:r?.name||h.code,value_krw:value,cost_krw:usableCost,pnl_krw:value!==null&&usableCost!==null?value-usableCost:null,pnl_pct:value!==null&&usableCost>0?(value/usableCost-1)*100:null,weight_pct:null};
    });
    if(!complete||total===null||!num(total)||total>Number.MAX_SAFE_INTEGER||total<=0){total=null;complete=false;}
    if(complete)for(const pos of positions)pos.weight_pct=pos.value_krw/total*100;
    return {complete,total_krw:total,cash_krw:x.cash_krw,positions,missing_codes:missing};
  }
  function reviewHoldings(x,policy={}){
    validate(x);const p=cleanPolicy(policy),book=bookSummary(x,p),map=new Map(x.research.map(r=>[r.code,r]));
    return {book,rows:book.positions.map(pos=>{
      const r=map.get(pos.code),c=companyReview(r,x.as_of,p),over=pos.weight_pct!==null&&pos.weight_pct>p.companyCapPct;
      const issuerWeight=r&&book.complete?book.positions.filter(h=>map.get(h.code)?.issuer_id===r.issuer_id).reduce((s,h)=>s+h.weight_pct,0):null;
      const companyOver=issuerWeight!==null&&issuerWeight>p.companyCapPct;
      let portfolioAction=book.complete?(companyOver?'동일 기업 합산 비중 상한 초과 · 축소 검토':'설정한 개별기업 비중 상한 이내'):'잔고·가격 부족으로 비중 판단 보류';
      return {...pos,...c,code:pos.code,company_opinion:c.opinion,portfolio_action:portfolioAction,overweight:companyOver,issuer_weight_pct:issuerWeight,research:r||null};
    })};
  }
  function candidateChecks(x,policy={}){
    validate(x);const p=cleanPolicy(policy);
    return x.research.map(r=>{
      const c=companyReview(r,x.as_of,p),reasons=[...c.blockers];
      if(c.opinion!=='HOLD')reasons.push(c.label);
      if(!r.sector)reasons.push('산업 분류 없음');
      if(!r.risk_group)reasons.push('공통 위험군 미확인');
      return {code:r.code,name:r.name,opinion:c.opinion,ready:reasons.length===0,
        missing_data:c.opinion==='WAIT'||(c.opinion==='HOLD'&&(!r.sector||!r.risk_group)),
        reasons:[...new Set(reasons)]};
    });
  }
  function propose(x,policy={}){
    validate(x);const p=cleanPolicy(policy);
    const rejected=[],pool=[];let missingCandidateData=false;
    if(!x.research.length)return {status:'DATA_REQUIRED',items:[],cash_pct:null,rejected,message:'연구 후보 입력이 없습니다. 자료 없음과 현금 100% 제안을 구분합니다.',policy:p};
    const candidates=candidateChecks(x,p),rows=new Map(x.research.map(r=>[r.code,r]));
    for(const candidate of candidates){
      if(candidate.missing_data)missingCandidateData=true;
      if(!candidate.ready)rejected.push({code:candidate.code,name:candidate.name,reasons:candidate.reasons});
      else pool.push(rows.get(candidate.code));
    }
    if(!p.policyConfirmed||p.stressLossLimitPct===null)return {status:'SETTINGS_REQUIRED',items:[],cash_pct:null,rejected,message:'가정 시나리오의 손실 기준과 비중 설정을 확인한 뒤 모의 구성안을 생성하세요.',policy:p};
    if(!pool.length&&missingCandidateData)return {status:'DATA_REQUIRED',items:[],cash_pct:null,rejected,message:'후보의 근거·가격·분류가 부족합니다. 자료 부족을 현금 100% 의견으로 바꾸지 않습니다.',policy:p};
    // Transparent, fixed-slot allocation. No statistical optimisation/alpha claim.
    const equityBudgetBps=Math.min(10000-Math.ceil(p.minCashPct*100),Math.floor(10000*p.stressLossLimitPct/Math.abs(p.stressShockPct)));
    const slotBps=Math.floor(Math.min(equityBudgetBps/p.maxCompanies,Math.floor(p.companyCapPct*100),Math.floor(p.sectorCapPct*100),Math.floor(p.groupCapPct*100)));
    if(slotBps<=0)return {status:'CASH_ONLY',items:[],cash_pct:100,rejected,message:'현금·비중 한도와 반올림 설정에 따라 편입 가능한 주식 비중이 없습니다.',policy:p};
    const held=new Set(x.holdings.map(h=>h.code));
    pool.sort((a,b)=>(a.review.valuation==='attractive'?0:1)-(b.review.valuation==='attractive'?0:1)||(a.review.business==='improving'?0:1)-(b.review.business==='improving'?0:1)||(held.has(a.code)?0:1)-(held.has(b.code)?0:1)||a.code.localeCompare(b.code));
    const issuers=new Set(),sectors=new Map(),groups=new Map(),items=[];
    for(const r of pool){
      let reason='';
      if(issuers.has(r.issuer_id))reason='동일 기업 중복';
      else if(items.length>=p.maxCompanies)reason='기업 수 상한';
      else if((sectors.get(r.sector)||0)+slotBps>Math.floor(p.sectorCapPct*100))reason='산업 비중 상한';
      else if((groups.get(r.risk_group)||0)+slotBps>Math.floor(p.groupCapPct*100))reason='공통 위험군 비중 상한';
      if(reason){rejected.push({code:r.code,name:r.name,reasons:[reason]});continue;}
      issuers.add(r.issuer_id);sectors.set(r.sector,(sectors.get(r.sector)||0)+slotBps);groups.set(r.risk_group,(groups.get(r.risk_group)||0)+slotBps);
      items.push({code:r.code,name:r.name,issuer_id:r.issuer_id,sector:r.sector,risk_group:r.risk_group,weight_pct:slotBps/100,existing:held.has(r.code),reasons:['보유 검토 조건과 근거 입력 기준 통과','고정 슬롯 균등배분; 기대수익 최적화 아님'],research:r});
    }
    const cash=100-items.reduce((s,r)=>s+Math.round(r.weight_pct*100),0)/100;
    const selected=new Set(items.map(i=>i.code));
    return {status:items.length?'MODEL_PROPOSAL':'CASH_ONLY',items,cash_pct:cash,rejected,policy:p,unselected_holdings:x.holdings.filter(h=>!selected.has(h.code)).map(h=>h.code),message:'조건부 모의 목표안입니다. 미편입 보유종목을 자동 매도하거나 현재 보유목록을 변경하지 않습니다.',allocation_method:'fixed_slot_equal_v1',sector_weights:Object.fromEntries([...sectors].map(([k,v])=>[k,v/100])),group_weights:Object.fromEntries([...groups].map(([k,v])=>[k,v/100]))};
  }
  function stress(items,shockPct){
    if(!num(shockPct)||shockPct>0||shockPct< -100)throw Error('스트레스 가정은 -100~0%입니다.');
    return items.reduce((s,i)=>s+i.weight_pct/100*shockPct,0);
  }
  function empty(asOf){return {schema_version:'holdings-portfolio-0.1',mode:'user_input',as_of:asOf,snapshot_id:'manual-'+asOf,cash_krw:null,holdings:[],research:[]};}
  function fixture(){
    const asOf='2026-09-25';const rows=[];
    for(let i=1;i<=8;i++)rows.push({code:'99'+String(i).padStart(4,'0'),issuer_id:'FICTIONAL-ISSUER-'+i,name:'가상기업 '+String.fromCharCode(64+i),market:i%2?'KOSPI':'KOSDAQ',security_type:'ordinary',analysis_profile:'nonfinancial',sector:['가상산업 A','가상산업 B','가상산업 C','가상산업 D'][i%4],risk_group:['가상위험군 A','가상위험군 B','가상위험군 C','가상위험군 D'][i%4],price_krw:10000+i*1000,price_date:asOf,price_source:{label:'가상 가격 출처 · 실제 관측값 아님',url:'https://example.invalid/fixture/price'},review:{thesis:i===6?'broken':'intact',business:'stable',finance:'sound',valuation:i===7?'stretched':'fair',material_risk:'clear',reviewed_on:asOf,financial_period:'가상 TTM 2026-06-30',positives:['기능 검증용: 사업 지표가 안정적이라는 가정'],negatives:['기능 검증용: 수요 둔화가 발생할 수 있다는 가정'],invalidation:'가정한 주요 계약이 종료되면 논리를 다시 검토',next_review_on:'2026-10-30'},evidence:[{id:'FIX-'+i,label:'가상 근거 · 실제 공시 아님',url:'https://example.invalid/fixture/'+i,available_on:asOf,reviewed:true}]});
    rows[7].review.thesis='unknown';
    return {schema_version:'holdings-portfolio-0.1',mode:'fixture',as_of:asOf,snapshot_id:'FIXTURE-ONLY-20260925',cash_krw:200000,holdings:[{code:'990001',quantity:40,avg_cost_krw:10000,thesis_note:'테스트용 투자 메모'},{code:'990006',quantity:10,avg_cost_krw:17000},{code:'990007',quantity:10,avg_cost_krw:15000},{code:'990008',quantity:10,avg_cost_krw:17000}],research:rows};
  }
  // Commit a complete manual form atomically; no quote or review is inferred from cost.
  function saveHolding(input,holding,cash,quote=null){
    validate(input);const x=clone(input),i=x.holdings.findIndex(h=>h.code===holding.code);
    if(i>=0)x.holdings[i]={...x.holdings[i],...holding};else x.holdings.push(clone(holding));
    x.cash_krw=cash;
    if(quote){
      if(!dateOK(quote.date)||quote.date>x.as_of)throw Error('가격 기준일은 평가일 '+x.as_of+' 이하여야 합니다.');
      if(!text(quote.label)||quote.label.length>200)throw Error('가격 출처를 200자 이하로 입력하세요. 가상 가격이면 가상 입력이라고 표시하세요.');
      let r=x.research.find(r=>r.code===holding.code);
      if(!r){
        r={code:holding.code,issuer_id:holding.code,name:quote.name?.trim()||holding.code,
          market:'unknown',security_type:'unknown',analysis_profile:'unknown',sector:null,risk_group:null,
          price_krw:null,price_date:null,price_source:null,evidence:[],
          review:{thesis:'unknown',business:'unknown',finance:'unknown',valuation:'unknown',material_risk:'unknown',
            reviewed_on:null,financial_period:'미입력',positives:[],negatives:[],invalidation:'',next_review_on:null}};
        x.research.push(r);
      }
      r.price_krw=quote.price;r.price_date=quote.date;
      r.price_source={kind:'manual_input',label:(x.mode==='fixture'?'가상 테스트 · ':'사용자 수기 입력 · ')+quote.label.trim()};
    }
    return validate(x);
  }
  function attachMarket(input,market){
    validate(input);validate(market);
    if(input.mode!=='user_input'||market.mode!=='user_input')throw Error('실제/가상 보유 자료 혼합 금지');
    const result=clone(input),index=new Map(result.research.map(r=>[r.code,r]));
    for(const current of market.research){
      const row=index.get(current.code);
      if(!row){result.research.push(clone(current));continue;}
      if(['market','security_type','analysis_profile','name'].some(k=>row[k]!==current[k]))
        throw Error(current.code+': 종목 식별 정보가 다릅니다. 입력을 확인하세요.');
      if(own(current,'pending_events'))row.pending_events=clone(current.pending_events);
      if(current.price_date&&(!row.price_date||(current.price_date>row.price_date || current.price_date===row.price_date&&row.price_source?.kind!=='manual_input'))){
        for(const key of ['price_krw','price_date','price_source'])row[key]=clone(current[key]);
      }
    }
    result.as_of=market.as_of;
    result.snapshot_id=market.snapshot_id;
    result.market_data_as_of=market.market_data_as_of;
    return validate(result);
  }
  return Object.freeze({VERSION,LABEL,DEFAULT,dateOK,urlOK,validate,cleanPolicy,companyReview,bookSummary,reviewHoldings,propose,stress,empty,fixture,clone,attachMarket,candidateChecks,saveHolding});
})();
if(typeof module!=='undefined')module.exports=PortfolioEngine;
