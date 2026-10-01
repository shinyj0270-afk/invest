'use strict';
const FinancialTableUI = (() => {
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const numeric = v => typeof v === 'number' && Number.isFinite(v);
  const fmt = (v, unit) => numeric(v) ? v.toLocaleString('ko-KR', {minimumFractionDigits:unit === '억원' ? 0 : 1,maximumFractionDigits:unit === '억원' ? 0 : 1}) : '—';
  const names = {annual:'연간 실적',quarter:'분기 실적',cumulative:'누적 실적',reference:'공개 참고값'};
  const rows = [
    ['revenue','매출액','억원','amount'],['operating_profit','영업이익','억원','amount'],
    ['net_income','당기순이익','억원','amount'],['ebitda','EBITDA','억원','amount'],
    ['borrowings','차입금','억원','amount'],['total_borrowings','총차입금','억원','amount'],
    ['operating_margin','영업이익률','%','ratio'],
    ['ebitda_interest','EBITDA/이자비용','배','ratio'],['debt_ebitda','총차입금/EBITDA','배','ratio'],
    ['debt_ratio','부채비율','%','ratio'],['borrowing_dependence','차입금의존도','%','ratio']
  ];
  function reference(row,research) {
    const fields={operating_margin:'operating_margin_pct',debt_ratio:'debt_ratio_pct'};
    const values=Object.fromEntries(Object.entries(fields).map(([key,metric])=>[key,DiscoveryEngine.metric(row,metric)]));
    const notes=Object.fromEntries(Object.entries(fields).map(([key,metric])=>{
      const d=DiscoveryEngine.detail(row,research,metric);
      return [key,`출처 ${d.source||'미확보'} · 기간 ${d.period||'미확인'} · 기준 ${d.basis||'미확인'} · 관측 ${d.observed_on||'미확인'}`];
    }));
    return {groups:[{id:'reference',basis:'unknown',cadence:'reference',columns:[{
      period_end:'기간 미확인',source:'공개 참고자료 · 지표별 출처 확인',values,cell_notes:notes
    }]}],rows,notes:['기간별 재무 이력이 연결되지 않았습니다. 확보된 참고 비율만 표시합니다. 금액을 추정하지 않습니다.']};
  }
  function bars(columns,key,label,unit) {
    const valid=columns.filter(c=>numeric(c.values[key]));
    if(!valid.length)return '<p class="financial-empty">비교할 '+esc(label)+' 자료가 없습니다.</p>';
    const low=Math.min(0,...valid.map(c=>c.values[key])),high=Math.max(0,...valid.map(c=>c.values[key]));
    const span=high-low||1,zero=-low/span*100;
    return `<div class="financial-bars" aria-label="${esc(label)} 기간별 비교">${columns.map(c=>{
      const value=c.values[key],x=numeric(value)?(value-low)/span*100:zero;
      return `<div class="financial-bar-row"><span>${esc(c.period_end.slice(0,7).replace('-','.'))}</span><div class="financial-bar-track"><i style="left:${Math.min(x,zero)}%;width:${Math.abs(x-zero)}%" class="${value<0?'negative':''}"></i><em style="left:${zero}%"></em></div><b>${fmt(value,unit)} <small>${unit}</small></b></div>`;
    }).join('')}</div><p class="psub">${esc(label)} · ${unit} · 공통 0 기준 · 금액은 억원 단위 반올림</p>`;
  }
  function render(row,research,table,selected,store,state={}) {
    if(!table?.groups?.length){const pending=table?.notes||[];table=reference(row,research);table.notes=[...pending,...table.notes];}
    const groups=table.groups,group=groups.find(g=>g.id===selected)||groups.find(g=>g.cadence==='quarter')||groups[0];
    const columns=group.columns,last=columns.at(-1),defs=(table.rows||rows).filter(r=>r[0]!=='ebitda_margin');
    const basis=group.basis==='CFS'?'연결 재무(CFS)':group.basis==='OFS'?'별도 재무(OFS)':'회계 기준 미확인';
    const cards=group.cadence==='reference'
      ? [['roe_pct','ROE','%'],['operating_margin_pct','영업이익률','%'],['debt_ratio_pct','부채비율','%'],['per','참고 PER','배']].map(([key,label,unit])=>[label,DiscoveryEngine.metric(row,key),unit])
      : ['revenue','operating_profit','net_income','total_borrowings'].map(key=>{const d=defs.find(r=>r[0]===key);return [d[1],last.values[key],d[2],last.cell_notes?.[key]];});
    const controls=groups.length>1?`<label>표시 기간<select id="financialPeriodSelect">${groups.map(g=>`<option value="${esc(g.id)}" ${g.id===group.id?'selected':''}>${esc(g.basis)} · ${names[g.cadence]}</option>`).join('')}</select></label>`:'';
    const caption=basis+' · '+names[group.cadence];
    return `<article class="panel financial-panel" id="financialSummary"><div class="panel-heading"><h3>주요 재무지표</h3>${controls}</div><p class="psub">${esc(caption)} · 최신 표시 기간 ${esc(last.period_end)}${group.cadence==='quarter'?' · 손익: 단독 3개월':''}</p><div class="financial-cards">${cards.map(([label,value,unit,note])=>`<div class="financial-card" title="${esc(note||'')}"><span>${esc(label)}</span><strong>${fmt(value,unit)}${note&&numeric(value)?'<sup aria-label="산출 범위 확인">*</sup>':''} <small>${unit}</small></strong><small>${esc(last.period_end)}${numeric(value)?'':' · 미확보'}${note&&numeric(value)?' · 산출 범위 확인':''}</small></div>`).join('')}</div>${store?EbitdaEditor.render(row,group,store,state):''}<div class="financial-scroll" tabindex="0" role="region" aria-label="주요 재무지표 표. 좁은 화면에서는 좌우로 스크롤하세요."><table class="financial-table"><caption class="sr-only">${esc(row.name)} 주요 재무지표 · ${esc(caption)}</caption><thead><tr><th rowspan="2" scope="col">구분</th><th colspan="${columns.length}" scope="colgroup">${esc(caption)}</th></tr><tr>${columns.map(c=>`<th scope="col" title="${esc(c.period_end)}">${esc(c.period_end.slice(0,7).replace('-','.'))}${group.cadence==='quarter'?'<small>단독분기</small>':''}</th>`).join('')}</tr></thead><tbody>${defs.map(([key,label,unit,kind])=>`<tr class="${kind==='ratio'?'financial-ratio':''}" data-financial-key="${key}"><th scope="row">${esc(label)}(${unit})</th>${columns.map(c=>{const v=c.values[key],note=c.cell_notes?.[key];return `<td title="${esc((numeric(v)?v+' '+unit:'미확보')+' · '+c.source+(note?' · '+note:''))}">${key==='ebitda'&&store&&group.cadence!=='reference'?`<button class="ebitda-cell" type="button" data-ebitda-period="${esc(c.period_end)}" aria-label="${esc(c.period_end)} EBITDA 입력">${fmt(v,unit)}</button>`:fmt(v,unit)}${note&&numeric(v)?'<sup aria-label="산출 범위 확인">*</sup>':''}</td>`;}).join('')}</tr>`).join('')}</tbody></table></div>${group.cadence==='reference'?'<p class="financial-empty">기간별 매출·이익 비교는 재무 이력 연결 후 표시됩니다.</p>':`<div class="financial-comparison"><section><h4>매출액 비교</h4>${bars(columns,'revenue','매출액','억원')}</section><section><h4>영업이익 비교</h4>${bars(columns,'operating_profit','영업이익','억원')}</section></div>`}<div class="financial-notes"><p>— 미확보 · * 산출 범위 확인 · 모바일에서는 표를 좌우로 움직여 볼 수 있습니다.</p>${(table.notes||[]).map(n=>`<p>${esc(n)}</p>`).join('')}<details><summary>출처와 산출 범위</summary>${columns.map(c=>`<p>${esc(c.period_end)} · ${esc(c.source)} · 공개일 ${esc(c.available_at||'미확인')}</p>`).join('')}${[...new Set(columns.flatMap(c=>Object.values(c.cell_notes||{})))].map(n=>`<p>${esc(n)}</p>`).join('')}</details></div></article>`;
  }
  return {render};
})();
if(typeof module!=='undefined')module.exports=FinancialTableUI;
