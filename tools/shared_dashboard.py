"""Publish from the designated PC; home opens the last verified offline result."""
import argparse
import json
import sys
import webbrowser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('publish','open','status'))
    args=parser.parse_args()
    from investment.shared_dashboard import ResultRepository,export_company,open_home,cached
    if args.action=='publish':
        manifest,compressed=export_company(ROOT)
        tag=ResultRepository().publish(manifest,compressed)
        print(json.dumps(dict(status='published',tag=tag,market_as_of=manifest['market_as_of'],sha256=manifest['sha256']),ensure_ascii=False))
    elif args.action=='open':
        _,status=open_home(ROOT,browser=webbrowser.open)
        print('지정 PC 결과 수신 완료' if status=='received' else '수신 연결 대기 · 마지막 정상 결과 열기')
    else:
        manifest,_=cached(ROOT)
        print(json.dumps(manifest,ensure_ascii=False,indent=2))


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,TypeError) as error:
        print('저장 결과: '+str(error),file=sys.stderr)
        sys.exit(1)
