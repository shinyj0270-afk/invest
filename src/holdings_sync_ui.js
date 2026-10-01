/* Local first, authenticated loopback sync. GitHub credentials never enter this page. */
'use strict';
const HoldingsSyncUI = (() => {
  function create({getState,applyState}){
    const H=HoldingsSync,config=window.INVESTMENT_HOLDINGS_SYNC;
    const namespace=window.INVESTMENT_INITIAL_SNAPSHOT?.meta?.data_mode||'standalone';
    const key='investment-holdings-private-v1-'+namespace;
    const note=document.getElementById('pSaveStatus'),conflictBox=document.getElementById('pSyncConflict');
    let state=null,base=null,dirty=false,busy=false,conflict=null,timer=null,stopped=false,storage=null,localSaved=false,unreadable=null,retryAt=0,retryMs=3000;
    const say=t=>note.textContent=t;
    try{storage=(window.parent===window?window:window.parent).localStorage;}catch{}
    function save(){
      try{if(!storage)throw Error();if(unreadable!==null){storage.setItem(key+'-unreadable-backup',unreadable);unreadable=null;}storage.setItem(key,JSON.stringify({version:1,state,base,dirty}));localSaved=true;return true;}
      catch{localSaved=false;say('이 브라우저의 저장이 차단됐습니다. 현재 입력 내보내기로 보관하세요.');return false;}
    }
    function showConflict(c){
      conflict=c;conflictBox.hidden=false;
      const names={quantity:'수량',avg_cost_krw:'평균 매입가',cash_krw:'현금',price_record:'가격·기준일·출처',identity_record:'기업 식별',review:'기업 검토',policy:'구성 설정'};
      const summary=c.conflicts.map(v=>v.path.split('/').filter(Boolean).map(k=>names[k]||k).join(' · ')).join(' / ');
      document.getElementById('pConflictText').textContent='두 PC에서 다르게 수정한 항목: '+summary+'. 내 입력을 유지하고 자동 덮어쓰기를 멈췄습니다.';
      say('동기화 충돌 · 적용할 값을 선택하세요.');
    }
    function accept(result,sent){
      if(result.status==='conflict'){
        showConflict({base:result.base,local:state||sent,remote:result.remote,conflicts:result.conflicts});return;
      }
      if(result.status!=='synced'){
        const saved=localSaved||result.local_saved===true;
        say((dirty?(saved?'이 PC에 저장 · 연결되면 자동 전송':'현재 화면에만 입력 유지 · 내보내기로 보관하세요.'):'마지막 저장내역 유지 · 연결 대기')+(result.message?' · '+result.message:''));return;
      }
      if(!result.state){say(state?'마지막 입력 유지 · 원격 저장내역 확인 필요':'PC 동기화 연결됨 · 보유종목을 직접 입력하세요.');return;}
      const merged=H.merge(sent,state||sent,result.state);
      if(merged.conflicts.length){showConflict({base:sent,local:state,remote:result.state,conflicts:merged.conflicts});return;}
      state=merged.state;base=result.state;dirty=!H.equal(state,base);conflict=null;conflictBox.hidden=true;
      const stored=save();applyState(state);
      if(stored)say(dirty?'이 PC에 저장 · 변경사항 전송 대기':'회사·집 동기화 완료 · '+new Date().toLocaleTimeString('ko-KR',{timeZone:'Asia/Seoul'}));
      else if(!dirty)say('회사·집 동기화 완료 · 이 브라우저의 로컬 저장은 차단됐습니다.');
    }
    async function sync(){
      if(stopped||!config?.enabled||busy||conflict||Date.now()<retryAt||getState().input.mode!=='user_input')return;
      busy=true;const sent=state,wasDirty=dirty;say('동기화 확인 중 · 입력은 이 PC에 유지됩니다.');
      try{
        const headers={'X-Dashboard-Token':config.token};let options={headers,cache:'no-store'};
        if(wasDirty){options={...options,method:'POST',headers:{...headers,'Content-Type':'application/json'},body:JSON.stringify({state:sent,base})};}
        const response=await fetch(config.endpoint||'/holdings',options);
        if(!response.ok)throw Error();const result=await response.json();
        // Changes made while a request was in flight are rebased, not replaced.
        accept(result,sent);
        if(result.status==='synced'){retryMs=3000;retryAt=0;}else {retryAt=Date.now()+retryMs;retryMs=Math.min(60000,retryMs*2);}
      }catch{retryAt=Date.now()+retryMs;retryMs=Math.min(60000,retryMs*2);say(dirty?(localSaved?'이 PC에 저장 · 연결되면 자동 전송':'현재 화면에만 입력 유지 · 내보내기로 보관하세요.'):'마지막 입력 유지 · 동기화 연결 대기');}
      finally{busy=false;if(dirty&&!conflict&&!stopped)timer=setTimeout(sync,Math.max(250,retryAt-Date.now()));}
    }
    function changed(next){
      if(next.input.mode!=='user_input'){say('가상 예제 · 저장된 실제 보유내역은 유지됩니다.');return;}
      H.validate(next);state=PortfolioEngine.clone(next);dirty=true;
      const stored=save();if(stored)say(config?.enabled?'이 PC에 저장 · 동기화 대기':'이 브라우저에 저장 완료 · PC 동기화는 연결 앱에서 사용하세요.');
      if(config?.enabled&&!conflict){retryAt=0;clearTimeout(timer);timer=setTimeout(sync,250);}
    }
    function restore(){if(state){applyState(state);say(config?.enabled?'저장된 보유내역 복원 · 동기화 확인 중':'이 브라우저의 보유내역 복원 완료');}if(config?.enabled)sync();}
    function resolve(choice){
      if(!conflict)return;
      const result=H.merge(conflict.base,state||conflict.local,conflict.remote,choice);
      base=conflict.remote;conflict=null;conflictBox.hidden=true;state=result.state;dirty=true;retryAt=0;save();applyState(state);sync();
    }
    document.getElementById('pKeepLocal').onclick=()=>resolve('local');
    document.getElementById('pUseRemote').onclick=()=>resolve('remote');
    document.getElementById('pSyncNow').onclick=()=>{retryAt=0;if(!conflict)sync();};
    document.getElementById('pReturnSaved').onclick=restore;
    document.getElementById('pOpenSync').hidden=!!config?.enabled;
    document.getElementById('pSyncNow').hidden=!config?.enabled;
    try{
      const raw=storage?.getItem(key);
      if(raw){const v=JSON.parse(raw);if(v.version!==1)throw Error();H.validate(v.state);if(v.base)H.validate(v.base);state=v.state;base=v.base||null;dirty=v.dirty===true;localSaved=true;restore();}
      else say(config?.enabled?'PC 동기화 연결 확인 중':'직접 입력을 반영하면 이 브라우저에 자동 저장합니다.');
    }catch{try{unreadable=storage?.getItem(key)??null;}catch{}say('저장된 보유내역 형식 확인 필요 · 기존 저장 내용을 보존합니다.');}
    if(config?.enabled){sync();const interval=setInterval(sync,20000);window.addEventListener('pagehide',()=>{stopped=true;clearInterval(interval);clearTimeout(timer);});}
    return {changed,restore,policy:()=>state?.policy||PortfolioEngine.DEFAULT};
  }
  return Object.freeze({create});
})();
