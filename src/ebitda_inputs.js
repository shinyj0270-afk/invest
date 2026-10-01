'use strict';
const EbitdaInputs = (() => {
  const numeric = value => typeof value === 'number' && Number.isFinite(value);
  const key = entry => JSON.stringify([entry.code, entry.basis, entry.cadence, entry.period_end]);
  function number(text) {
    const raw = String(text ?? '').trim();
    if (!/^[-+]?(?:\d{1,3}(?:,\d{3})+(?:\.\d*)?|\d+(?:\.\d*)?|\.\d+)$/.test(raw)) {
      throw Error('금액을 숫자로 입력하세요. 미확보와 0을 구분해 주세요.');
    }
    const value = Number(raw.replaceAll(',', ''));
    if (!numeric(value)) throw Error('유효한 금액을 입력하세요.');
    return value;
  }
  function calculate(operatingProfit, depreciation, amortization) {
    if (![operatingProfit, depreciation, amortization].every(numeric)) throw Error('계산에 필요한 세 금액을 모두 입력하세요.');
    if (depreciation < 0 || amortization < 0) throw Error('상각비는 0 이상으로 입력하세요.');
    const value = operatingProfit + depreciation + amortization;
    if (!numeric(value)) throw Error('계산 결과가 유효하지 않습니다.');
    return value;
  }
  function create({dataMode, rows, tables, initial}) {
    let entries = [], storageNote = '';
    const storageKey = 'investment-ebitda-v1-' + dataMode;
    function pack() { return {version:1, kind:'investment-ebitda', data_mode:dataMode, unit:'억원', entries:entries.map(e => ({...e, components:e.components ? {...e.components} : undefined}))}; }
    function context(row, group, column) {
      return {code:row.code, name:row.name, market:row.market, basis:group.basis, cadence:group.cadence, period_end:column.period_end};
    }
    function validate(entry) {
      if (!entry || !/^\d{6}$/.test(entry.code) || typeof entry.name !== 'string' || !entry.name || entry.name.length > 100 ||
          typeof entry.market !== 'string' || !['CFS','OFS'].includes(entry.basis) || !['annual','quarter','cumulative'].includes(entry.cadence) ||
          !/^\d{4}-\d{2}-\d{2}$/.test(entry.period_end) || !numeric(entry.value) || !['direct','operating'].includes(entry.method) ||
          typeof entry.note !== 'string' || entry.note.length > 500) throw Error('EBITDA 입력 파일의 항목 형식을 확인하세요.');
      let components;
      if (entry.method === 'operating') {
        const c = entry.components || {};
        const value = calculate(c.operating_profit, c.depreciation, c.amortization);
        if (Math.abs(value - entry.value) > Math.max(1e-8, Math.abs(value)*1e-12)) throw Error('계산 내역과 EBITDA 금액이 일치하지 않습니다.');
        components = {operating_profit:c.operating_profit, depreciation:c.depreciation, amortization:c.amortization};
      }
      return {code:entry.code, name:entry.name, market:entry.market, basis:entry.basis, cadence:entry.cadence,
              period_end:entry.period_end, value:entry.value, method:entry.method, note:entry.note, ...(components ? {components} : {})};
    }
    function compatible(entry) {
      const row = rows.find(r => r.code === entry.code && r.name === entry.name && r.market === entry.market);
      const group = tables[entry.code]?.groups?.find(g => g.basis === entry.basis && g.cadence === entry.cadence);
      return !!row && !!group?.columns.some(c => c.period_end === entry.period_end);
    }
    function restore(payload) {
      if (!payload || payload.version !== 1 || payload.kind !== 'investment-ebitda' || payload.data_mode !== dataMode ||
          payload.unit !== '억원' || !Array.isArray(payload.entries) || payload.entries.length > 10000) {
        throw Error('현재 자료 모드와 같은 억원 단위 EBITDA 입력 파일을 선택하세요.');
      }
      const accepted = [], seen = new Set();
      for (const raw of payload.entries) {
        const entry = validate(raw), id = key(entry);
        if (seen.has(id)) throw Error('같은 기업·기간·회계기준의 EBITDA 입력이 중복되었습니다.');
        seen.add(id);
        if (compatible(entry)) accepted.push(entry);
      }
      entries = accepted;
      return {accepted:accepted.length, skipped:payload.entries.length - accepted.length};
    }
    function persist() {
      try { localStorage.setItem(storageKey, JSON.stringify(pack())); storageNote = '입력값이 이 브라우저에 저장되었습니다.'; }
      catch { storageNote = '이 브라우저에 저장할 수 없습니다. 입력값 파일 저장으로 보관하세요.'; }
    }
    try {
      const saved = initial || JSON.parse(localStorage.getItem(storageKey) || 'null');
      if (saved) {
        const result = restore(saved);
        storageNote = `EBITDA 입력 ${result.accepted}개 복원` + (result.skipped ? ` · 현재 기업·기간과 다른 ${result.skipped}개 제외` : '');
      }
    } catch { storageNote = '이전 EBITDA 입력을 복원하지 못했습니다. 보관한 입력 파일을 불러오세요.'; }
    function find(row, group, column) { return entries.find(e => key(e) === key(context(row, group, column))); }
    function save(row, group, column, input) {
      const entry = validate({...context(row, group, column), ...input});
      if (!compatible(entry)) throw Error('확인된 기업·기간·회계기준의 재무표에만 입력할 수 있습니다.');
      entries = entries.filter(e => key(e) !== key(entry)); entries.push(entry); persist();
    }
    function remove(row, group, column) {
      const id = key(context(row, group, column)); entries = entries.filter(e => key(e) !== id); persist();
    }
    function apply(row, table) {
      if (!table?.groups?.length) return table;
      const copy = {...table, groups:table.groups.map(group => ({...group, columns:group.columns.map(column => {
        const entry = find(row, group, column); if (!entry) return column;
        const source = entry.method === 'direct' ? '사용자 직접 입력' : '사용자 계산 · 영업이익 기준';
        const formula = entry.components ? ` · ${entry.components.operating_profit} + ${entry.components.depreciation} + ${entry.components.amortization} 억원` : '';
        const note = source + formula + (entry.note ? ' · '+entry.note : '') + ' · 공시값 검증 전';
        const values = {...column.values, ebitda:entry.value,
          ebitda_interest:numeric(column.interest_expense_eok) && column.interest_expense_eok > 0 ? entry.value/column.interest_expense_eok : null,
          debt_ebitda:group.cadence === 'annual' && entry.value > 0 && numeric(column.values.total_borrowings) ? column.values.total_borrowings/entry.value : null};
        const cell_notes = {...column.cell_notes, ebitda:note, ebitda_interest:note};
        if (group.cadence === 'annual') cell_notes.debt_ebitda = [column.cell_notes?.total_borrowings, note].filter(Boolean).join(' · ');
        return {...column, values, cell_notes};
      })}))};
      return copy;
    }
    return {pack, find, save, remove, apply, storageNote:()=>storageNote,
      import:payload=>{const result = restore(payload); persist(); return result;}};
  }
  return {numeric, number, calculate, create};
})();
if (typeof module !== 'undefined') module.exports = EbitdaInputs;
