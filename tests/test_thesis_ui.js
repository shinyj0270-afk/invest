'use strict';
const assert=require('assert');
global.WORKSPACE_DATA={thesis_monitor:{'000001':{action:'재검토 권고',note:'판단을 자동으로 바꾸지 않습니다.',
 scenarios:[{title:'<수요>',description:'d1',status:'warning'},{title:'현금',description:'d2',status:'watch'},{title:'경쟁',description:'d3',status:'insufficient'}],
 conditions:[{id:'a',label:'매출 감소',status:'triggered',observed:2,basis:'재무 2026-06-30 CFS'},{id:'b',label:'200일선',status:'clear',observed:false,basis:'종가 2026-10-07'},{id:'c',label:'고객 이탈',status:'manual',basis:'수동 확인 필요'}]}}};
const U=require('../src/dashboard_upgrade_ui.js');
const v={status:'draft',drafted_by:'Claude 초안',scenarios:[{},{},{}],invalidation:[]};
const html=U.thesisBlock(v,'000001');
assert.ok(html.includes('&lt;수요&gt;')&&!html.includes('<수요>'),'escaped');
assert.ok(html.includes('재검토 권고')&&html.includes('초안 · 확인 대기'));
assert.ok(html.includes('충족')&&html.includes('미충족')&&html.includes('수동 확인'));
assert.ok(html.includes('관측 2')&&html.includes('관측 아니오'));
assert.equal((html.match(/<li><b>/g)||[]).length,3,'three scenarios');
assert.equal(U.thesisBlock({fact:'v1 only'},'000001'),'','v1 entries render nothing extra');
const pending=U.thesisBlock({scenarios:[{title:'a',description:'x'},{title:'b',description:'y'},{title:'c',description:'z'}],invalidation:[{id:'m',label:'수동',kind:'manual'}]},'999999');
assert.ok(pending.includes('점검 결과 대기')&&pending.includes('수동 확인'),'no monitor yet');
console.log('PASS thesis v2 block: three scenarios, condition states, draft label, escaping, v1 compatibility, pending monitor');
