'use strict';
// 아래 값은 오직 단위 테스트용입니다. 실제 기업·실제 시장 자료가 아닙니다.
const assert=require('node:assert/strict');
const E=require('../src/engine.js');let n=0;
function test(name,fn){fn();n++;console.log('PASS '+name)}
const r={metrics:{operating_margin_pct:10,foreign_net_20d_eok:0,debt_ratio_pct:null}};
const margin={metric:'operating_margin_pct',op:'gte',value:10};
const debt={metric:'debt_ratio_pct',op:'lte',value:100};
test('경계값 포함',()=>assert.equal(E.evaluate(r,[margin]),'pass'));
test('결측치는 0이 아님',()=>assert.equal(E.evaluate(r,[debt]),'unknown'));
test('실제 0은 유효한 값',()=>assert.equal(E.evaluate(r,[{metric:'foreign_net_20d_eok',op:'eq',value:0}]),'pass'));
test('AND의 실패와 결측',()=>assert.equal(E.evaluate(r,[{...margin,value:11},debt]),'fail'));
test('OR의 통과와 결측',()=>assert.equal(E.evaluate(r,[margin,debt],'OR'),'pass'));
test('OR의 실패와 결측',()=>assert.equal(E.evaluate(r,[{...margin,value:11},debt],'OR'),'unknown'));
test('빈 조건은 통과',()=>assert.equal(E.evaluate(r,[]),'pass'));
test('중앙값은 결측 제외',()=>assert.equal(E.median([null,1,3,5,7]),4));
test('전부 결측 중앙값',()=>assert.equal(E.median([null]),null));
test('작은 업종 집단은 백분위 숨김',()=>assert.equal(E.percentile(1,[1,2,3,4]),null));
test('동률 중간 백분위',()=>assert.equal(E.percentile(2,[1,2,2,2,3]),50));
const base={schema_version:'0.1',meta:{price_date:'2025-12-30',flow_start:'2025-12-01',flow_end:'2025-12-30',financial_period:'FY2025',financial_basis:'CFS',venue:'KRX',universe_label:'테스트 전용'},companies:[{code:'000001',name:'테스트 전용',market:'KOSPI',industry:'테스트 업종',security_type:'ordinary',analysis_profile:'nonfinancial',metrics:{operating_margin_pct:10}}]};
test('정상 형식 검사',()=>assert.equal(E.validateSnapshot(base).companies.length,1));
const bar=(date,close)=>({date,close,volume:100,turnover:1000,venue:null,final:false,adjustment_basis:'unverified'});
const withPrices=prices=>({...base,companies:[{...base.companies[0],prices}]});
test('선택적 관측 종가 이력',()=>assert.equal(E.validateSnapshot(withPrices([bar('2025-12-29',10),bar('2025-12-30',11)])).companies[0].prices.length,2));
test('과거 스냅샷에 prices 없어도 통과',()=>assert.equal(E.validateSnapshot(base).companies[0].prices,undefined));
test('가격 날짜 중복·역순·기준일 이후 차단',()=>{
  for(const bars of [[bar('2025-12-30',10),bar('2025-12-30',11)],
                     [bar('2025-12-30',10),bar('2025-12-29',11)],
                     [bar('2025-12-31',10)]])assert.throws(()=>E.validateSnapshot(withPrices(bars)));
});
test('비정상 가격과 상태 차단',()=>{
  for(const bad of [{...bar('2025-12-30',10),close:0},
                    {...bar('2025-12-30',10),close:'10'},
                    {...bar('2025-12-30',10),date:'2025-02-30'},
                    {...bar('2025-12-30',10),final:null}])
    assert.throws(()=>E.validateSnapshot(withPrices([bad])));
});
test('기준 혼합 차단',()=>assert.throws(()=>E.validateSnapshot({...base,companies:[{...base.companies[0],financial_basis:'OFS'}]})));
test('중복 코드 차단',()=>assert.throws(()=>E.validateSnapshot({...base,companies:[base.companies[0],base.companies[0]]})));
test('수치 문자열 차단',()=>assert.throws(()=>E.validateSnapshot({...base,companies:[{...base.companies[0],metrics:{operating_margin_pct:'10'}}]})));
test('금융업 일반 스크리너 제외',()=>assert.equal(E.eligible([{...base.companies[0],analysis_profile:'financial'}]).length,0));
test('업종 비교는 전체 입력 모집단 기준',()=>assert.equal(E.peerRows([...base.companies,{...base.companies[0],code:'000002',metrics:{operating_margin_pct:-3}}],'테스트 업종').length,2));
test('악성 출처 URL 차단',()=>assert.throws(()=>E.validateSnapshot({...base,companies:[{...base.companies[0],sources:[{label:'x',url:'javascript:alert(1)'}]}]})));
test('모집단 수 역전 차단',()=>assert.throws(()=>E.validateSnapshot({...base,meta:{...base.meta,universe_total:0}})));
console.log(`${n} tests passed.`);
