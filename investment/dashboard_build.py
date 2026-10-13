"""Runtime identity from public source bytes, independent of Git and local data."""
import hashlib
from pathlib import Path

APP = 'investment-holdings-sync'
PROTOCOL_VERSION = 2


def source_fingerprint(root):
    root = Path(root).resolve()
    digest = hashlib.sha256()
    for folder, suffixes in (('investment', {'.py'}), ('tools', {'.py'}),
                             ('src', {'.js', '.html', '.css'})):
        for path in sorted((root / folder).rglob('*')):
            if path.is_file() and path.suffix in suffixes:
                digest.update(path.relative_to(root).as_posix().encode())
                digest.update(b'\0')
                digest.update(path.read_bytes())
                digest.update(b'\0')
    return digest.hexdigest()


def build_identity(root, build_id=None):
    return dict(app=APP, version=PROTOCOL_VERSION,
                root_id=hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest(),
                build_id=build_id or source_fingerprint(root))


def restart_page(token=None):
    import json
    action=''
    if token:
        action='''<p><label><input id="draftsSaved" type="checkbox">모든 열린 탭의 작성 내용을 보관했습니다.</label></p>
<button id="safeRestart">안전하게 서버 다시 실행</button><p id="restartStatus" role="status"></p>
<script>document.getElementById('safeRestart').onclick=async()=>{
const status=document.getElementById('restartStatus');
if(!document.getElementById('draftsSaved').checked){status.textContent='열린 탭의 입력을 먼저 보관하고 확인해 주세요.';return;}
try{const response=await fetch('/restart',{method:'POST',headers:{'Content-Type':'application/json','X-Dashboard-Token':TOKEN},body:JSON.stringify({drafts_saved:true})});const data=await response.json();status.textContent=data.message||data.error;if(response.ok){document.getElementById('safeRestart').disabled=true;status.textContent+=' 잠시 후 화면 확인 버튼을 눌러 주세요.';}}catch{status.textContent='서버 연결을 확인하고 open-investment.cmd를 실행하세요.';}};</script>'''.replace('TOKEN',json.dumps(token))
    return ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>INVESTMENT · 서버 다시 실행</title></head><body><main style="font:16px sans-serif;'
            'max-width:680px;margin:12vh auto;padding:24px"><h1>새 코드가 저장되었습니다</h1>'
            '<p>기존 서버와 화면의 버전이 달라 자료 연결을 잠시 멈췄습니다.</p>'
            '<p>모든 열린 탭의 보유 입력과 작성 중인 내용을 먼저 보관하세요. '
            '수집·동기화가 끝나면 아래에서 안전하게 다시 실행할 수 있습니다. '
            '연결이 끊겼다면 scripts/open-investment.cmd를 다시 실행하세요.</p>'
            +action+'<button onclick="location.href=\'/\'">서버 다시 실행 후 화면 확인</button></main></body></html>')


def loading_page():
    """Show a visible shell before the saved-data dashboard is assembled."""
    return '''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>통합 투자 대시보드 · 자료 준비</title></head>
<body style="margin:0;background:#e9ecf1;color:#2a2f3a;font:16px sans-serif">
<main style="max-width:680px;margin:12vh auto;padding:30px;background:#e9ecf1;border-radius:26px;box-shadow:9px 9px 20px #c8ced8,-9px -9px 20px #ffffff">
<h1>통합 투자 대시보드</h1><p id="loadingStatus" role="status" aria-live="polite">저장된 자료를 준비하고 있습니다.</p>
<p>기업과 주가 자료가 많으면 잠시 걸릴 수 있습니다. 준비가 끝나면 화면이 열립니다.</p>
<button id="loadingRetry" hidden onclick="location.reload()">다시 열기</button>
<p id="loadingHelp" hidden>서버 연결을 확인하세요. 서버가 종료되었다면 open-investment.cmd로 다시 실행하세요.</p>
</main><script>
(async()=>{
  try{
    const response=await fetch('/dashboard',{cache:'no-store'});
    const html=await response.text();
    if(!response.ok&&response.status!==503)throw new Error('dashboard unavailable');
    if(!html.trim().startsWith('<')||!response.headers.get('Content-Type')?.includes('text/html'))throw new Error('invalid dashboard');
    document.open();document.write(html);document.close();
  }catch(error){
    document.getElementById('loadingStatus').textContent='화면을 준비하지 못했습니다. 연결을 확인하고 다시 열어 주세요.';
    document.getElementById('loadingRetry').hidden=false;
    document.getElementById('loadingHelp').hidden=false;
  }
})();
</script></body></html>'''
