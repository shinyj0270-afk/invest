(function(){
  function create(element,live){
    let timer=null,busy=false;
    const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const stage={identity:'기업 식별',calendar:'거래일 확인',availability:'자료 제공 여부',statements:'보고서 확인',network:'제공처 연결',validation:'자료 검증',unknown:'이전 기록'};
    const request=(method,body)=>fetch('/data-recovery',{method,headers:{'X-Dashboard-Token':live.token,'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{})}).then(async r=>{const v=await r.json();if(!r.ok)throw Error(v.error||'복구 상태를 확인하지 못했습니다.');return v;});
    async function render(){
      if(!element||!live?.token||busy)return;busy=true;
      try{
        const wasOpen=element.querySelector('details')?.open===true;
        const partialWasOpen=element.querySelector('details details')?.open===true;
        const data=await request('GET');const failures=data.failures||[];
        const running=data.price_job?.status==='running'||Object.values(data.financial_jobs||{}).some(j=>j.status==='running');
        const row=f=>{const job=f.kind==='price'?data.price_job:data.financial_jobs?.[f.code];const active=job?.status==='running';return `<article class="source-card"><strong>${esc(f.name)} · ${esc(f.code)} · ${f.kind==='price'?'가격':'재무'}${f.status==='partial'?' 일부 누락':''}</strong><p>${esc(stage[f.stage]||stage.unknown)} · ${esc(f.reason)}</p><p class="muted">최근 확인 ${esc(f.checked_at||'기록 없음')} · 자동 재확인 권장 ${esc(f.retry_at||'다음 정기 점검')} (앱 실행 중)</p><button type="button" data-recovery-kind="${esc(f.kind)}" data-recovery-code="${esc(f.code)}" ${active||f.can_retry===false?'disabled':''}>${f.eligible===false?esc("\uD604\uC7AC \uC218\uC9D1 \uB300\uC0C1 \uC544\uB2D8"):f.can_retry===false?'읽기 전용':active?'조회 중':'이 종목만 재시도'}</button></article>`;};
        const failed=failures.filter(f=>f.status!=='partial'),partial=failures.filter(f=>f.status==='partial');
        element.innerHTML=`<details><summary>데이터 복구 · 실패 ${failed.length} · 일부 누락 ${partial.length}</summary><p>검증을 통과한 자료만 반영하며, 실패한 조회는 기존 자료를 유지합니다.</p><p>${esc(data.scope||"\uC800\uC7A5\uB41C \uC218\uC9D1 \uAE30\uB85D \uC804\uCCB4")}</p><p role="status" data-recovery-status>${running?'대상 자료를 조회하고 있습니다.':''}</p>${failed.map(row).join('')||'<p>확인된 전체 조회 실패가 없습니다.</p>'}${partial.length?`<details><summary>일부 보고서 누락 ${partial.length}개</summary>${partial.map(row).join('')}</details>`:''}</details>`;
        element.querySelectorAll('[data-recovery-code]').forEach(button=>button.addEventListener('click',async()=>{
          button.disabled=true;const status=element.querySelector('[data-recovery-status]');
          try{const result=await request('POST',{kind:button.dataset.recoveryKind,code:button.dataset.recoveryCode});status.textContent=result.message||'대상 자료 확인을 시작했습니다.';clearTimeout(timer);timer=setTimeout(render,2500);}
          catch(error){status.textContent=error.message;button.disabled=false;}
        }));
        if(wasOpen)element.querySelector('details').open=true;
        if(partialWasOpen&&element.querySelector('details details'))element.querySelector('details details').open=true;
        const guidance=document.createElement('p');guidance.textContent='재시도 후 새 자료는 입력을 보관한 뒤 화면 새로고침으로 반영하세요.';
        element.querySelector('details').append(guidance);
        if(running){clearTimeout(timer);timer=setTimeout(render,3000);}
      }catch(error){element.textContent=error.message;}finally{busy=false;}
    }
    return {render};
  }
  window.InvestmentDataRecovery={create};
})();
