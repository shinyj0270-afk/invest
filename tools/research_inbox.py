"""Local batch ledger for '투자연구함 정리해'. Research happens in the current AI session."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from investment.research_inbox import prepare, finish, search, read, reopen, status
from investment.telegram_export import local_file


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('status')
    p = sub.add_parser('prepare')
    p.add_argument('--limit', type=int, default=20)
    p = sub.add_parser('finish')
    p.add_argument('--batch', required=True)
    p.add_argument('--input', required=True)
    p = sub.add_parser('search')
    p.add_argument('query', nargs='?', default='')
    p = sub.add_parser('reopen')
    p.add_argument('--id', required=True)
    p.add_argument('--reason', required=True)
    args = parser.parse_args()
    if args.action == 'status':
        result = status(ROOT)
    elif args.action == 'prepare':
        result = prepare(ROOT, args.limit)
    elif args.action == 'finish':
        result = finish(ROOT, args.batch, read(local_file(ROOT, args.input)))
    elif args.action == 'reopen':
        result = reopen(ROOT, args.id, args.reason)
    else:
        result = search(ROOT, args.query)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, TypeError, KeyError):
        print('연구함 처리 중단: 프로필·로컬 입력·원자료 변경·동시 실행을 확인하세요. 기존 자료는 보존합니다.', file=sys.stderr)
        sys.exit(1)
