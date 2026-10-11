'use strict';
const ResearchLibraryUI=(()=>{
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names=['워런 버핏','찰리 멍거','하워드 막스','피터 린치','스탠리 드러켄밀러','마이클 모부신','마크 미너비니','윌리엄 오닐'];
function create(element,live){
let loaded=false;
function paint(data){
element.innerHTML='<div class="section-title"><h2>Research Library</h2><p>장기 투자 관점과 산업 가설 · 저장된 연구 열람</p></div><article class="panel"><h3>Investment Masters</h3><p class="psub">원문 기반 연구카드는 작성·검토 후 연결됩니다.</p><div class="grid2">'+(data?.masters||names.map(name=>({name}))).map(m=>'<p>'+esc(m.name)+'</p>').join('')+'</div></article><article class="panel below"><h3>연구카드</h3>'+((data?.cards||[]).map(r=>'<p>'+esc(r.value.principle)+' · '+esc(r.value.master)+'</p>').join('')||'<p class="psub">저장된 연구카드가 없습니다.</p>')+'</article><article class="panel below"><h3>산업 가설</h3>'+((data?.theses||[]).map(r=>'<details><summary>'+esc(r.value.title)+' · r'+esc(r.revision)+'</summary><p>'+esc(r.value.claim)+'</p><p>기준일 '+esc(r.value.as_of)+' · '+esc(r.value.status)+'</p><p>반증 조건: '+esc((r.value.invalidation||[]).join('; '))+'</p><p>연결 종목: '+esc((r.value.instruments||[]).map(x=>x.code+' ('+x.kind+')').join(', '))+'</p><p class="psub">기존 종목 판단과 독립된 연구 가설입니다.</p></details>').join('')||'<p class="psub">저장된 산업 가설이 없습니다.</p>')+'</article><article class="panel below"><h3>작성과 출처 관리</h3><p>이번 화면은 열람용입니다. 입력은 기존 Research Library CLI에서 출처·반례·revision을 함께 기록합니다.</p><p class="psub">회사에서는 Telegram 입력이 비활성입니다. ETF 분석 공급자는 연결 대기입니다. 정적 내보내기에는 연구 DB를 포함하지 않습니다.</p><p id="libraryStatus" role="status">'+esc(data?'저장된 '+data.profile+' 연구 · '+data.status:'로컬 연구 연결 대기')+'</p><button id="libraryReload">연구 목록 다시 확인</button></article>';
element.querySelector('#libraryReload').onclick=()=>{loaded=false;render();};
}
async function render(){
if(loaded)return;loaded=true;paint(null);
if(!live?.token){element.querySelector('#libraryStatus').textContent='정적 화면 · 로컬 연구 목록은 실행 중인 앱에서 확인하세요.';return;}
try{const response=await fetch('/research-library',{headers:{'X-Dashboard-Token':live.token},cache:'no-store'});if(!response.ok)throw Error();paint(await response.json());}
catch{loaded=false;element.querySelector('#libraryStatus').textContent='연구 목록 연결 대기 · 기존 입력은 보존됩니다.';}
}
return {render};
}
return {create};
})();
