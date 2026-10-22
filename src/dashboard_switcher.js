/* Switch visible workspaces without recreating either dashboard or losing drafts. */
const InvestmentDashboardSwitcher = (() => {
  function create(live, resultView) {
    const $ = id => document.getElementById(id);
    const toggle=$('dashboardSwitch'), menu=$('dashboardChoices'), stock=document.querySelector('.app-layout');
    const panel=$('creditDashboard'), frame=$('creditDashboardFrame'), message=$('creditConnectionStatus');
    const local=!!live&&!resultView&&['127.0.0.1','localhost'].includes(location.hostname);
    let connected=false, busy=false;
    function close(focus=false){menu.hidden=true;toggle.setAttribute('aria-expanded','false');if(focus)toggle.focus();}
    function select(kind){
      const credit=kind==='credit';stock.hidden=credit;panel.hidden=!credit;
      document.body.dataset.dashboard=kind;
      $('dashboardCurrent').textContent=credit?'크레딧':'주식';
      for(const button of menu.querySelectorAll('[data-dashboard-choice]'))button.setAttribute('aria-pressed',String(button.dataset.dashboardChoice===kind));
      close();
    }
    async function connect(){
      if(!local||busy)return;
      busy=true;$('creditRetry').disabled=true;message.textContent='크레딧 대시보드 연결을 확인하고 있습니다.';
      const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),5000);
      try{
        const response=await fetch('/credit-status',{headers:{'X-Dashboard-Token':live.token},cache:'no-store',signal:controller.signal});
        if(!response.ok)throw Error();
        const data=await response.json();
        if(!data.available||data.url!=='http://127.0.0.1:4580/index.html')throw Error();
        if(!connected){frame.src=data.url;connected=true;}
        frame.hidden=false;$('creditConnection').hidden=true;
      }catch{message.textContent='CREDIT 대시보드를 실행한 뒤 다시 연결해 주세요. 주식 화면의 입력은 그대로 유지됩니다.';$('creditConnection').hidden=false;}
      finally{clearTimeout(timer);busy=false;$('creditRetry').disabled=false;}
    }
    toggle.onclick=()=>{const open=menu.hidden;menu.hidden=!open;toggle.setAttribute('aria-expanded',String(open));};
    document.addEventListener('click',event=>{if(!event.target.closest('.dashboard-switcher'))close();});
    document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!menu.hidden)close(true);});
    for(const button of menu.querySelectorAll('[data-dashboard-choice]'))button.onclick=()=>{
      const kind=button.dataset.dashboardChoice;select(kind);if(kind==='credit'&&!connected)connect();
    };
    $('creditRetry').onclick=connect;
    $('creditChoice').disabled=!local;$('creditLocalHint').hidden=local;
  }
  return {create};
})();
