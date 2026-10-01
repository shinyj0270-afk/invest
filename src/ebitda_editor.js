'use strict';
const EbitdaEditor = (() => {
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const numeric = v => typeof v === 'number' && Number.isFinite(v);
  const names = {annual:'연간 실적',quarter:'분기 실적',cumulative:'누적 실적'};
  const selectedGroup = (table,selected) => table?.groups?.find(g=>g.id===selected)||table?.groups?.find(g=>g.cadence==='quarter')||table?.groups?.[0];
  function render(row,group,store,state) {
    if(!store)return '';
    const toolbar=`<div class="ebitda-files"><button id="ebitdaExport" type="button">입력값 파일 저장</button><label class="research-file">입력값 불러오기<input id="ebitdaImport" type="file" accept=".json,application/json"></label></div>`;
    if(group.cadence==='reference')return `<div class="ebitda-inputs"><p>EBITDA는 보고기간·연결/별도가 확인된 재무표에 입력할 수 있습니다.</p>${toolbar}<p class="ebitda-status psub" role="status">${esc(state.notice||store.storageNote())}</p></div>`;
    const column=group.columns.find(c=>c.period_end===state.period)||group.columns.at(-1);
    const entry=store.find(row,group,column),method=state.method||entry?.method||'direct';
    const value=entry?.value ?? column.values.ebitda;
    const op=entry?.components?.operating_profit ?? column.values.operating_profit;
    const input=(id,label,value)=>`<label>${label}<input id="${id}" type="text" inputmode="decimal" value="${numeric(value)?esc(value):''}" placeholder="미확보" autocomplete="off"></label>`;
    return `<div class="ebitda-inputs">${toolbar}<details id="ebitdaEditor" ${state.open?'open':''}><summary>EBITDA 입력 · 계산</summary>
      <p class="psub">${esc(row.name)} · ${esc(group.basis)} · ${names[group.cadence]} · 모든 금액은 억원</p>
      <form id="ebitdaForm" novalidate><div class="ebitda-grid">
      <label>입력 기간<select id="ebitdaPeriod">${group.columns.map(c=>`<option value="${esc(c.period_end)}" ${column.period_end===c.period_end?'selected':''}>${esc(c.period_end)}</option>`).join('')}</select></label>
      <label>입력 방식<select id="ebitdaMethod"><option value="direct" ${method==='direct'?'selected':''}>EBITDA 직접 입력</option><option value="operating" ${method==='operating'?'selected':''}>영업이익 + 상각비로 계산</option></select></label></div>
      <fieldset id="ebitdaDirectFields" ${method==='direct'?'':'hidden'}>${input('ebitdaValue','EBITDA (억원)',value)}</fieldset>
      <fieldset id="ebitdaCalculationFields" ${method==='operating'?'':'hidden'}><div class="ebitda-grid">
      ${input('ebitdaOperatingProfit','영업이익 (억원)',op)}${input('ebitdaDepreciation','감가상각비 (억원)',entry?.components?.depreciation)}${input('ebitdaAmortization','무형자산상각비 (억원)',entry?.components?.amortization)}
      </div><p class="psub">영업이익 + 감가상각비 + 무형자산상각비. 감가상각비가 무형상각비를 포함한 합계라면 무형상각비에 0을 입력하세요. 모두 같은 기간·연결/별도 기준을 사용하세요.</p>
      <p>계산 결과 <output id="ebitdaPreview">—</output> 억원</p></fieldset>
      <label>출처 / 메모<input id="ebitdaNote" type="text" maxlength="500" value="${esc(entry?.note||'')}" placeholder="보고서·페이지 또는 적용한 계산 기준"></label>
      <div class="ebitda-actions"><button type="submit" class="research-primary">표에 반영</button><button id="ebitdaReset" type="button" ${entry?'':'disabled'}>이 기간 수기값 지우기</button></div></form>
      <p class="psub">영업이익 기준 계산값은 회사 공시 EBITDA와 다를 수 있습니다. 표에서 사용자 계산값으로 구분합니다. <a href="https://wcomp.fnguide.com/Help/Guide" target="_blank" rel="noopener noreferrer">산식 참고</a></p>
      <p class="psub">이 브라우저에 저장됩니다. 다른 PC에서는 입력값 파일을 저장한 뒤 불러오세요. 분기 EBITDA를 연간으로 환산하지 않습니다.</p></details>
      <p class="ebitda-status psub" role="status">${esc(state.notice||store.storageNote())}</p></div>`;
  }
  function bind(element,row,table,selected,store,state,onChange) {
    const $=id=>element.querySelector('#'+id),group=selectedGroup(table,selected);
    const status=message=>{state.notice=message;const el=element.querySelector('.ebitda-status');if(el)el.textContent=message;};
    if($('ebitdaExport'))$('ebitdaExport').onclick=()=>{
      const url=URL.createObjectURL(new Blob([JSON.stringify(store.pack(),null,2)],{type:'application/json'})),a=document.createElement('a');
      a.href=url;a.download='investment_ebitda_inputs.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    };
    if($('ebitdaImport'))$('ebitdaImport').onchange=async e=>{
      const file=e.target.files?.[0];if(!file)return;
      try{if(file.size>2000000)throw Error('2MB 이하 입력 파일을 선택하세요.');const result=store.import(JSON.parse(await file.text()));
        state.notice=`입력 ${result.accepted}개 불러옴 · 현재 기업·기간과 다른 ${result.skipped}개 제외. ${store.storageNote()}`;state.method=undefined;onChange();
      }catch(error){status(error.message||'입력 파일을 확인하세요.');}
    };
    if(!group||!$('ebitdaForm'))return;
    const column=()=>group.columns.find(c=>c.period_end===$('ebitdaPeriod').value);
    $('ebitdaEditor').ontoggle=e=>{state.open=e.target.open;};
    $('ebitdaPeriod').onchange=e=>{state.period=e.target.value;state.method=undefined;state.open=true;state.notice='';onChange();};
    const preview=()=>{try{$('ebitdaPreview').textContent=EbitdaInputs.calculate(...['ebitdaOperatingProfit','ebitdaDepreciation','ebitdaAmortization'].map(id=>EbitdaInputs.number($(id).value))).toLocaleString('ko-KR',{maximumFractionDigits:6});}catch{$('ebitdaPreview').textContent='—';}};
    $('ebitdaMethod').onchange=e=>{state.method=e.target.value;$('ebitdaDirectFields').hidden=e.target.value!=='direct';$('ebitdaCalculationFields').hidden=e.target.value!=='operating';preview();};
    for(const id of ['ebitdaOperatingProfit','ebitdaDepreciation','ebitdaAmortization'])$(id).oninput=preview;
    preview();
    $('ebitdaForm').onsubmit=e=>{
      e.preventDefault();
      try {
        const method=$('ebitdaMethod').value,note=$('ebitdaNote').value.trim();let input;
        if(method==='direct')input={method,note,value:EbitdaInputs.number($('ebitdaValue').value)};
        else {
          const components=Object.fromEntries([['operating_profit','ebitdaOperatingProfit'],['depreciation','ebitdaDepreciation'],['amortization','ebitdaAmortization']].map(([key,id])=>[key,EbitdaInputs.number($(id).value)]));
          input={method,note,components,value:EbitdaInputs.calculate(components.operating_profit,components.depreciation,components.amortization)};
        }
        store.save(row,group,column(),input);state.period=column().period_end;state.method=undefined;state.open=true;state.notice=store.storageNote();onChange();
      } catch(error) { status(error.message); }
    };
    $('ebitdaReset').onclick=()=>{store.remove(row,group,column());state.method=undefined;state.notice='이 기간의 수기값을 지웠습니다. '+store.storageNote();state.open=true;onChange();};
    element.querySelectorAll('[data-ebitda-period]').forEach(el=>el.onclick=()=>{
      state.period=el.dataset.ebitdaPeriod;state.method=undefined;state.open=true;state.notice='';onChange();element.querySelector('#ebitdaValue')?.focus();
    });
  }
  return {render,bind};
})();
if(typeof module!=='undefined')module.exports=EbitdaEditor;
