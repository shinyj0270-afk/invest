'use strict';
const assert=require('assert');
global.WORKSPACE_DATA={thesis_monitor:{'000001':{action:'재검토 권고',type:'fast',type_label:'고성장',note:'판단을 자동으로 바꾸지 않습니다.',
 scenarios:[{title:'<수요>',description:'d1',status:'warning'},{title:'현금',description:'d2',status:'watch'},{title:'경쟁',description:'d3',status:'insufficient'}],
 conditions:[
  {id:'a',guideline:7,role:'invalidation',text:'분기 영업이익 전년 동기 대비 25% 미만 증가',label:'x',status:'triggered',observed:17.6,basis:'재무 2026-06-30 CFS'},
  {id:'b',guideline:3,role:'invalidation',text:'자체 RS 70점 미만',label:'y',status:'clear',observed:82,basis:'종가 2026-10-07'},
  {id:'c',guideline:null,role:'invalidation',text:'고객 이탈',label:'z',status:'manual',basis:'수동 확인 필요'},
  {id:'d',guideline:4,role:'context',text:'소속 시장 지수가 상승 정렬이 아님',label:'m',status:'triggered',observed:false,basis:'종가 2026-10-07'},
  {id:'e',guideline:9,role:'invalidation',text:'연간 영업이익 3년 연평균 25% 미만',label:'n',status:'insufficient',basis:'자료 부족'}]}}};
const U=require('../src/dashboard_upgrade_ui.js');
const v={status:'draft',drafted_by:'Claude 초안',scenarios:[{},{},{}],invalidation:[],type:'fast'};
const html=U.thesisBlock(v,'000001');
assert.ok(html.includes('&lt;수요&gt;')&&!html.includes('<수요>'),'escaped');
assert.ok(html.includes('재검토 권고')&&html.includes('초안 · 확인 대기'));
const confirmed=U.thesisBlock({...v,status:'confirmed',confirmed_on:'2026-10-08'},'000001');
assert.ok(confirmed.includes('확정 2026-10-08')&&!confirmed.includes('초안 · 확인 대기'),'confirmed label replaces the draft label');
assert.ok(html.includes('유형 고성장'),'stock type label');
assert.ok(html.includes('G7')&&html.includes('G3')&&html.includes('G9'),'guideline numbers shown');
assert.ok(html.includes('충족')&&html.includes('미충족')&&html.includes('수동 확인')&&html.includes('자료 부족'));
assert.ok(html.includes('관측 17.6'));
assert.equal((html.match(/<li><b>/g)||[]).length,3,'three scenarios');
const ctx=html.slice(html.indexOf('시장 환경'));
assert.ok(html.includes('시장 환경 (참고)')&&ctx.includes('G4')&&ctx.includes('소속 시장'),'market context listed separately');
assert.ok(!html.slice(0,html.indexOf('시장 환경 (참고)')).includes('소속 시장 지수'),'context not mixed into invalidation list');
assert.equal(U.thesisBlock({fact:'v1 only'},'000001'),'','v1 entries render nothing extra');
const pending=U.thesisBlock({type:'cyclical',scenarios:[{title:'a',description:'x'},{title:'b',description:'y'},{title:'c',description:'z'}],invalidation:[{id:'m',label:'수동',kind:'manual'}]},'999999');
assert.ok(pending.includes('점검 결과 대기')&&pending.includes('수동 확인'),'no monitor yet');
console.log('PASS thesis v2.1 block: type, guideline numbers, three scenarios, condition states, separate market context, draft label, escaping, v1 compatibility');
