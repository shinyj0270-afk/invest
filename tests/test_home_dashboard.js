'use strict';
const assert=require('assert');
const H=require('../src/home_dashboard_ui.js');

const market=(name,dir,pct,extra={})=>({market:name,as_of:'2026-10-07',index:{status:'ready',label:dir,close:100},
 breadth:{label:pct>=50?'참여 양호':'참여 약화',above:{'200':{pct,count:1,eligible:4}},advancing:250,declining:452},
 volatility:{annual20_pct:29.7,prior20_pct:42.8,label:'직전 구간 대비 축소·동일'},explanation:'설명',...extra});
const sector=(industry,mkt,ret,score,count=10,cap=100)=>({industry,market:mkt,count,short_rs:{'1m':{return_pct:ret,score,count,cap_eok:cap}}});

// 오늘의 결론: 지수 방향과 기업 참여를 규칙으로만 요약한다.
{
 const v=H.verdict({as_of:'2026-10-07',markets:[market('KOSPI','상승 정렬',25.1),market('KOSDAQ','혼조 · 전환 관찰',24.8)]},{sectors:[sector('반도체','KOSDAQ',33.3,90),sector('통신장비','KOSDAQ',32.9,89.7)]});
 assert.equal(v.headline,'지수는 오르는데, 따라 오르는 기업은 적습니다');
 assert.equal(v.lines.length,3);
 assert.equal(v.lines[0],'KOSPI는 상승 정렬 · 200일선 위 기업 25.1% · 상승 250 / 하락 452');
 assert.equal(v.lines[1],'KOSDAQ은 혼조 · 전환 관찰 · 200일선 위 기업 24.8% · 상승 250 / 하락 452');
 assert.equal(v.lines[2],'변동성 KOSPI 29.7% · KOSDAQ 29.7% (직전 구간 대비 축소·동일) · 1개월 RS 최상위 업종 반도체(KOSDAQ)');
 assert.equal(v.as_of,'2026-10-07');
}
assert.equal(H.verdict({markets:[market('KOSPI','상승 정렬',62),market('KOSDAQ','상승 정렬',55)]},{}).headline,'지수와 기업 참여가 함께 강합니다');
assert.equal(H.verdict({markets:[market('KOSPI','하락 정렬',30),market('KOSDAQ','상승 정렬',55)]},{}).headline,'지수와 기업 참여가 함께 약합니다','weak outranks strong');
assert.equal(H.verdict({markets:[market('KOSPI','하락 정렬',60)]},{}).headline,'지수는 약하지만 기업 참여는 유지됩니다');
assert.equal(H.verdict({markets:[market('KOSPI','상승 정렬',60),market('KOSDAQ','혼조 · 전환 관찰',55)]},{}).headline,'지수 방향이 뚜렷하지 않은 혼조 구간입니다','strong requires every ready market');
{
 const pending=market('KOSDAQ','자료 대기',null);pending.index.status='pending';
 const v=H.verdict({markets:[market('KOSPI','상승 정렬',62),pending]},{});
 assert.equal(v.headline,'지수와 기업 참여가 함께 강합니다','pending markets do not decide the headline');
 assert.equal(v.lines[1],'KOSDAQ 판단 자료 대기');
}
{
 const v=H.verdict(undefined,undefined);
 assert.equal(v.headline,'시장 판단 자료 대기');
 assert.deepEqual(v.lines,['KOSPI 판단 자료 대기','KOSDAQ 판단 자료 대기','변동성 자료 대기']);
}

// 섹터 맵: 1개월 RS 상위 8개, 색은 표시 업종 안의 상대 수익률(낮음 틸 ↔ 높음 코랄).
{
 const insights={sectors:[sector('A','KOSPI',10,50),sector('B','KOSDAQ',30,95,30),sector('C','KOSPI',20,80),sector('X','KOSPI',99,null),
  ...Array.from({length:8},(_,i)=>sector('F'+i,'KOSDAQ',-5+i,10+i))]};
 const tiles=H.sectorTiles(insights);
 assert.equal(tiles.length,8);
 assert.deepEqual(tiles.slice(0,3).map(t=>t.industry),['B','C','A']);
 assert.ok(!tiles.some(t=>t.industry==='X'),'missing RS score is not ranked');
 assert.equal(tiles[0].count,30);
 const hi=tiles.find(t=>t.industry==='B'),lo=tiles.reduce((a,b)=>a.ret<b.ret?a:b);
 assert.equal(hi.t,1);assert.equal(lo.t,0);
 assert.equal(hi.bg,'hsl(352,85%,82%)','strongest tile is the deepest coral');
 assert.equal(lo.bg,'hsl(188,65%,87%)','weakest tile is the deepest teal');
 assert.ok(tiles.every(t=>t.fg==='#2a2f3a'));
 assert.equal(H.sectorTiles({sectors:[sector('only','KOSPI',5,60)]})[0].t,0.5,'single tile stays neutral');
 assert.deepEqual(H.sectorTiles(null),[]);
}
assert.equal(H.tileColor(0.5),'hsl(188,20%,95%)');

// 업종 후보: 같은 시장·산업, 발굴 허용, RS 점수 내림차순 최대 5개.
{
 const rows=[['1','가','KOSDAQ','반도체'],['2','나','KOSDAQ','반도체'],['3','다','KOSPI','반도체'],['4','라','KOSDAQ','반도체'],['5','마','KOSDAQ','반도체'],['6','바','KOSDAQ','반도체'],['7','사','KOSDAQ','반도체'],['8','아','KOSDAQ','반도체']]
  .map(([code,name,m,industry])=>({code,name,market:m,industry,discovery_allowed:code!=='7'}));
 const tech=(score,ret,status)=>({technical:{short_rs:{'1m':{score,return_pct:ret}},price_trend_status:status}});
 const research={rows:{'1':tech(70,5,'pass'),'2':tech(90,9,'fail'),'3':tech(99,20,'pass'),'4':tech(80,7),'5':tech(60,3),'6':tech(75,4),'7':tech(100,30,'pass'),'8':tech(null,1)}};
 const list=H.candidates(rows,research,{market:'KOSDAQ',industry:'반도체'});
 assert.deepEqual(list.map(c=>c.code),['2','4','6','1','5']);
 assert.equal(list[0].trend,'추세 미충족');assert.equal(list[3].trend,'가격 추세 충족');assert.equal(list[1].trend,'추세 판정 대기');
 assert.equal(list[0].ret,9);
}

// HTML 조각: 이스케이프와 자료 대기 문구.
{
 const html=H.sectorMap([{industry:'<b>',market:'KOSPI',count:3,ret:1,rs:50,share:2,t:.5,bg:'x',fg:'y'}],0);
 assert.ok(html.includes('&lt;b&gt;')&&!html.includes('<b><'),'industry names are escaped');
 assert.ok(H.sectorMap([],0).includes('자료 대기'));
 assert.ok(H.candidatesPanel(null,[]).includes('업종을 선택'));
}
{
 const record={month:'2026-10',review_status:'검토 완료',cash_pct:5,targets:[1,2,3,4,5].map(i=>({code:'00000'+i,name:'가상'+i,weight_pct:19}))};
 const html=H.recommendation(record);
 assert.equal((html.match(/data-home-rec-code=/g)||[]).length,5);
 assert.ok(html.includes('현금 <b>5%</b>'));
 assert.ok(html.includes('<svg'),'donut chart is drawn');
 assert.equal(H.recommendation(null),'이번 달 추천안 작성 대기');
}
{
 const html=H.kpis({universe:1369,cash:null,watched:3,pending:312});
 assert.ok(html.includes('1,369')&&html.includes('312'));
 assert.ok(html.includes('추천 현금 <b>—</b>'),'unknown cash is not invented');
}
console.log('PASS home dashboard verdict rules, sector map scale, candidate selection, escaping and pending states');
