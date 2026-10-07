"""One-click loopback dashboard; no scheduled task or startup registration."""
import argparse,hashlib,json,os,subprocess,sys,time,webbrowser
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from investment.dashboard_build import build_identity
def server_identity(port):
    try:
        with urlopen(f'http://127.0.0.1:{port}/health',timeout=2) as r:
            data=json.load(r)
        return data if isinstance(data,dict) else None
    except (OSError,ValueError,URLError):return None

def health(port):
    data=server_identity(port)
    return bool(data and all(data.get(k)==v for k,v in build_identity(ROOT).items()) and not data.get('restart_required'))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8767);parser.add_argument('--no-browser',action='store_true');args=parser.parse_args()
    if not 1<=args.port<=65535:parser.error('올바른 포트 번호를 입력하세요.')
    if not health(args.port):
        import socket
        with socket.socket() as s:
            if s.connect_ex(('127.0.0.1',args.port))==0:
                existing=server_identity(args.port);expected=build_identity(ROOT)
                if existing and existing.get('app')==expected['app'] and existing.get('root_id')==expected['root_id']:
                    raise RuntimeError('이 작업본의 이전 INVESTMENT 서버가 실행 중입니다. 보유 입력·작성 중인 내용을 보관하고 기존 서버를 종료한 뒤 scripts/open-investment.cmd를 다시 실행하세요. 새 코드가 실행되기 전에는 기존 서버를 재사용하지 않습니다.')
                raise RuntimeError('이 포트를 기존 프로그램이 사용 중입니다. 이전 서버를 종료하거나 다른 포트를 지정하세요.')
        log=ROOT/'.local/holdings-sync/server.log';log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('ab') as f:
            proc=subprocess.Popen([sys.executable,str(ROOT/'tools/serve_dashboard.py'),'--saved-only','--port',str(args.port)],cwd=ROOT,
                stdout=f,stderr=f,stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        for _ in range(30):
            if health(args.port):break
            if proc.poll() is not None:raise RuntimeError('동기화 앱 실행 환경을 확인하세요. 이 PC의 실행 기록에 원인이 표시됩니다.')
            time.sleep(.3)
        else:raise RuntimeError('동기화 앱을 열지 못했습니다. 잠시 후 다시 실행하세요.')
    if not args.no_browser:webbrowser.open(f'http://127.0.0.1:{args.port}/')
    print(f'INVESTMENT 동기화 앱 준비 완료: http://127.0.0.1:{args.port}/')

if __name__=='__main__':
    try:main()
    except (RuntimeError,OSError) as e:print(str(e),file=sys.stderr);sys.exit(1)
