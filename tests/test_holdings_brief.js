'use strict';
const assert=require('assert');
const B=require('../src/holdings_brief_ui.js');

const tech=(as_of,close,rs,status='pass',ma=90)=>({as_of,close,short_rs:{'1m':{score:rs}},price_trend_status:status,sma:{'200':ma}});
const item=(over={})=>({code:'000001',name:'가상전자',opinion:'HOLD',label:'보유 검토',reasons:['논리 유지'],
 technical:tech('2026-10-07',100,80),common:{period:'2026-06-30',basis:'CFS',metrics:{revenue_growth_pct:12.3,operating_margin_pct:9.1}},
 health:{},verification:{status:'pass',label:'통과'},thesis:{action:'유지 점검',conditions:[]},...over});
const now={day:'2026-10-08',time:'08:30'};

// Rollover keeps the previous completed day as the comparison base, even after same-day reloads.
{
 let r=B.rollover(null,B.snapshot(item()));
 assert.equal(r.prior,null);
 const first=r.next;
 r=B.rollover(first,B.snapshot(item()));
 assert.equal(r.prior,null,'same day reload keeps no prior');
 const next=B.snapshot(item({technical:tech('2026-10-08',104,86)}));
 r=B.rollover(first,next);
 assert.equal(r.prior.day,'2026-10-07');
 const again=B.rollover(r.next,next);
 assert.equal(again.prior.day,'2026-10-07','same-day reload still compares to the prior day');
}

// First observation is labelled, never a fabricated change.
{
 const b=B.brief(item(),null,now);
 assert.deepEqual(b.changes,['첫 관측 · 다음 완료 종가부터 비교']);
 assert.equal(b.judgment.kind,'first');
 assert.equal(b.basis,'종가 2026-10-07 · 재무 2026-06-30 CFS · 확인 08:30');
}

// Quiet day collapses to one line.
{
 const prior=B.snapshot(item());
 const b=B.brief(item({technical:tech('2026-10-08',101,82)}),prior,now);
 assert.equal(b.quiet,true);
 assert.ok(B.render([b]).includes('변경 없음'));
}

// Important changes, impact, judgment change and risks.
{
 const prior=B.snapshot(item());
 const cur=item({opinion:'REVIEW',label:'재검토',reasons:['붕괴 조건 충족'],technical:tech('2026-10-08',94,70,'fail',95),
  common:{period:'2026-09-30',basis:'CFS',metrics:{revenue_growth_pct:-4,operating_margin_pct:6.5}},
  health:{decision:'material_revision',decision_on:'2026-10-08',material_changes:2},
  verification:{status:'review',label:'재검토 필요 · 자료 부족'},
  thesis:{action:'재검토 권고',conditions:[{label:'매출 2분기 연속 감소',status:'triggered'},{label:'고객 이탈',status:'manual'}]}});
 const b=B.brief(cur,prior,now);
 assert.ok(b.changes.includes('종가 -6.0% (2026-10-07 → 2026-10-08)'));
 assert.ok(b.changes.includes('1개월 RS 80 → 70'));
 assert.ok(b.changes.includes('가격 추세 이탈'));
 assert.ok(b.changes.includes('200일선 하향 이탈'));
 assert.ok(b.impact.includes('새 재무 2026-09-30 반영 · 매출 증가율 -4% · 영업이익률 6.5%'));
 assert.ok(b.impact.includes('중요 정정 2개 계정 반영 (2026-10-08)'));
 assert.deepEqual([b.judgment.kind,b.judgment.before,b.judgment.after],['changed','보유 검토','재검토']);
 assert.ok(b.risks.includes('붕괴 조건 충족: 매출 2분기 연속 감소'));
 assert.ok(b.risks.includes('분석 검증 재검토 필요 · 자료 부족'));
 assert.ok(b.risks.includes('200일선 아래'));
 assert.equal(b.quiet,false);
 const html=B.render([b]);
 assert.ok(html.includes('판단 변경')&&html.includes('보유 검토 → 재검토'));
}

// Small moves are not "important", and escaping holds.
{
 const prior=B.snapshot(item());
 const b=B.brief(item({name:'<b>x</b>',technical:tech('2026-10-08',102.9,83)}),prior,now);
 assert.deepEqual(b.changes,[]);
 const html=B.render([b]);
 assert.ok(html.includes('&lt;b&gt;x&lt;/b&gt;')&&!html.includes('<b>x</b>'));
 assert.ok(B.render([]).includes('보유종목이 없습니다'));
}
console.log('PASS holdings brief: rollover base, first observation, quiet collapse, change/impact/judgment/risk rules, escaping');
