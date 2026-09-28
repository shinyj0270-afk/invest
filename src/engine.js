'use strict';
const METRICS = Object.freeze({
  market_cap_eok: {label:'시가총액', unit:'억원', category:'규모', definition:'가격 기준일의 시가총액. 보통주·우선주 범위를 수집 단계에서 통일합니다.'},
  revenue_growth_pct: {label:'매출 증가율', unit:'%', category:'수익성', definition:'동일 길이의 비교 기간 대비 매출 증가율. 전기 매출이 0 이하인 경우 수집 단계에서 null 처리합니다.'},
  operating_margin_pct: {label:'영업이익률', unit:'%', category:'수익성', definition:'동일 보고기간 영업이익 ÷ 매출액 × 100. 매출액 0 이하이면 null 처리합니다.'},
  roe_pct: {label:'ROE', unit:'%', category:'수익성', definition:'최근 12개월 지배주주 순이익 ÷ 기초·기말 평균 지배주주 지분 × 100. 비교 기간과 연결 범위를 통일하고, 평균 지분 0 이하이면 null 처리합니다.'},
  debt_ratio_pct: {label:'부채비율', unit:'%', category:'재무안정성', definition:'부채총계 ÷ 자본총계 × 100. 자본총계 0 이하이면 null 처리하고 자본잠식 여부를 별도 확인합니다.'},
  net_debt_equity_pct: {label:'순차입금 / 자본', unit:'%', category:'재무안정성', definition:'(이자부 차입금 − 현금및현금성자산) ÷ 자본총계 × 100. 차입금 포함 계정은 수집 단계에서 통일합니다. 자본 0 이하이면 null입니다.'},
  interest_coverage_x: {label:'이자보상배율', unit:'배', category:'재무안정성', definition:'동일 기간 영업이익 ÷ 이자비용. 금융원가 전체로 대체하지 않습니다. 이자비용 0 이하 또는 구분 불가이면 null입니다.'},
  foreign_net_20d_eok: {label:'외국인 20일 순매수', unit:'억원', category:'수급', definition:'동일한 최근 20거래일의 외국인 순매수대금 합계. 장중 추정치가 아닌 확정치만 사용합니다.'},
  institution_net_20d_eok: {label:'기관 20일 순매수', unit:'억원', category:'수급', definition:'동일한 최근 20거래일의 기관합계 순매수대금 합계. 기관 분류는 공급자 기준을 기록합니다.'},
  foreign_net_turnover_20d_pct: {label:'외국인 순매수 / 거래대금', unit:'%', category:'수급', definition:'20거래일 외국인 순매수대금 합계 ÷ 같은 20거래일 전체 거래대금 합계 × 100. 거래소 범위를 통일합니다.'},
  institution_net_turnover_20d_pct: {label:'기관 순매수 / 거래대금', unit:'%', category:'수급', definition:'20거래일 기관 순매수대금 합계 ÷ 같은 20거래일 전체 거래대금 합계 × 100. 거래소 범위를 통일합니다.'},
  avg_trading_value_20d_eok: {label:'20일 일평균 거래대금', unit:'억원', category:'거래 유동성', definition:'최근 20거래일 거래대금 합계 ÷ 20. 기간 중 일부 자료가 없으면 null. 신규상장 등 관측일 부족을 20일 평균으로 표시하지 않습니다.'},
  current_ratio_pct: {label:'유동비율', unit:'%', category:'재무 유동성', definition:'유동자산 ÷ 유동부채 × 100. 유동부채 0 이하 또는 유동·비유동 구분이 없으면 null입니다.'}
});
const isNum = v => typeof v === 'number' && Number.isFinite(v);
const hasOwn = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
const val = (row, key) => isNum(row.metrics?.[key]) ? row.metrics[key] : null;
function median(values) { const a=values.filter(isNum).sort((a,b)=>a-b); if(!a.length)return null; const n=a.length;return n%2?a[(n-1)/2]:(a[n/2-1]+a[n/2])/2; }
function evaluateRule(row, rule) {
  const n=val(row,rule.metric); if(n===null)return 'unknown';
  if(!hasOwn(METRICS,rule.metric) || !isNum(rule.value))throw new Error('유효하지 않은 조건입니다.');
  const ops={gte:(a,b)=>a>=b,lte:(a,b)=>a<=b,gt:(a,b)=>a>b,lt:(a,b)=>a<b,eq:(a,b)=>a===b};
  if(!hasOwn(ops,rule.op))throw new Error('알 수 없는 비교 연산입니다.');
  return ops[rule.op](n,rule.value)?'pass':'fail';
}
function evaluate(row,rules,logic='AND') {
  if(!rules.length)return 'pass';
  const a=rules.map(r=>evaluateRule(row,r));
  if(logic==='AND')return a.includes('fail')?'fail':a.includes('unknown')?'unknown':'pass';
  if(logic==='OR')return a.includes('pass')?'pass':a.includes('unknown')?'unknown':'fail';
  throw new Error('AND 또는 OR만 지원합니다.');
}
function percentile(value,values){const a=values.filter(isNum);if(!isNum(value)||a.length<5)return null;return (a.filter(x=>x<value).length+0.5*a.filter(x=>x===value).length)/a.length*100;}
function eligible(rows){return rows.filter(r=>['KOSPI','KOSDAQ'].includes(r.market)&&r.security_type==='ordinary'&&r.analysis_profile==='nonfinancial');}
function peerRows(rows,industry){return eligible(rows).filter(r=>r.industry===industry);}
function validateSnapshot(data){
  if(!data||data.schema_version!=='0.1'||!Array.isArray(data.companies))throw new Error('schema_version 0.1 및 companies 배열이 필요합니다.');
  if(data.companies.length>10000)throw new Error('한 번에 10,000개 이하의 종목만 불러올 수 있습니다.');
  if(!data.meta||typeof data.meta!=='object')throw new Error('meta가 필요합니다.');
  if(data.meta.data_mode!=null&&!['fixture','user_input'].includes(data.meta.data_mode))throw new Error('data_mode는 fixture 또는 user_input입니다.');
  const required=['price_date','flow_start','flow_end','financial_period','financial_basis','venue','universe_label'];
  if(data.companies.length)for(const k of required)if(typeof data.meta[k]!=='string'||!data.meta[k].trim())throw new Error(`meta.${k} 기준값이 필요합니다.`);
  for(const k of ['price_date','flow_start','flow_end'])if(data.meta[k]&&!/^\d{4}-\d{2}-\d{2}$/.test(data.meta[k]))throw new Error(`${k} 날짜 형식은 YYYY-MM-DD입니다.`);
  if(data.meta.flow_start&&data.meta.flow_end&&data.meta.flow_start>data.meta.flow_end)throw new Error('수급 시작일은 종료일보다 늦을 수 없습니다.');
  if(data.companies.length&&!['CFS','OFS'].includes(data.meta.financial_basis))throw new Error('연결(CFS)과 별도(OFS)를 혼합하지 마세요.');
  if(data.meta.universe_total!=null&&(!Number.isInteger(data.meta.universe_total)||data.meta.universe_total<data.companies.length))throw new Error('전체 모집단 수가 적재 종목 수보다 작거나 유효하지 않습니다.');
  const codes=new Set();
  for(const row of data.companies){
    if(typeof row.code!=='string'||!/^\d{6}$/.test(row.code)||codes.has(row.code))throw new Error('종목코드는 중복 없는 6자리 문자열이어야 합니다.');
    codes.add(row.code);
    for(const k of ['name','market','industry','security_type','analysis_profile'])if(typeof row[k]!=='string'||!row[k].trim())throw new Error(`${row.code}: ${k}가 필요합니다.`);
    if(!row.metrics||typeof row.metrics!=='object'||Array.isArray(row.metrics))throw new Error(`${row.code}: metrics가 필요합니다.`);
    if(row.data_quality!=null&&(!Array.isArray(row.data_quality)||row.data_quality.length>30||row.data_quality.some(s=>typeof s!=='string'||s.length>1000)))throw new Error('data_quality는 최대 30개 설명 배열입니다.');
    if(row.metric_missing_reasons!=null){
      if(typeof row.metric_missing_reasons!=='object'||Array.isArray(row.metric_missing_reasons))throw new Error('metric_missing_reasons는 객체입니다.');
      for(const [k,v] of Object.entries(row.metric_missing_reasons))if(!hasOwn(METRICS,k)||typeof v!=='string'||v.length>1000)throw new Error('지표의 결측 사유 형식이 올바르지 않습니다.');
    }
    for(const [k,v]of Object.entries(row.metrics)){if(!hasOwn(METRICS,k))throw new Error(`${row.code}: 알 수 없는 지표 ${k}`);if(v!==null&&!isNum(v))throw new Error(`${row.code}: ${k}는 숫자 또는 null이어야 합니다.`);}
    for(const k of required){if(row[k]!=null&&row[k]!==data.meta[k])throw new Error(`${row.code}: ${k}가 스냅샷 공통 기준과 다릅니다.`);}
    if(row.history!=null){
      if(!Array.isArray(row.history)||row.history.length>20)throw new Error('history는 최대 20개 연도 배열입니다.');
      const ys=new Set();
      for(const h of row.history){if(!Number.isInteger(h.year)||h.year<2000||h.year>2100||ys.has(h.year))throw new Error('history 연도는 중복 없는 정수여야 합니다.');ys.add(h.year);for(const k of ['revenue_eok','operating_profit_eok'])if(h[k]!=null&&!isNum(h[k]))throw new Error(`history.${k}는 숫자 또는 null입니다.`);}
    }
    if(row.sources!=null&&!Array.isArray(row.sources))throw new Error('sources는 배열입니다.');
    if(row.sources?.length>50)throw new Error('종목당 출처는 50개까지 가능합니다.');
    for(const s of row.sources||[])if(typeof s.label!=='string'||typeof s.url!=='string'||!/^https?:\/\//i.test(s.url))throw new Error('출처에는 label과 http(s) URL이 필요합니다.');
  }
  return data;
}
if(typeof module!=='undefined')module.exports={METRICS,isNum,val,median,evaluateRule,evaluate,percentile,eligible,peerRows,validateSnapshot};
