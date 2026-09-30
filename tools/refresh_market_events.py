"""Refresh public event metadata in this PC's user_input cache."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from investment.local_config import load_local, require_profile
from investment.market_events import EventStore, import_events, refresh_events
from investment.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codes', nargs='+', required=True, help='확인할 6자리 종목코드')
    parser.add_argument('--input', type=Path, help='선택: 수동 이벤트 JSON; 지정 시 네트워크 호출 없음')
    args = parser.parse_args()
    try:
        if len(args.codes)>100 or any(not re.fullmatch(r'\d{6}', code) for code in args.codes):
            raise ValueError('종목코드 형식/개수 오류')
        local = load_local(ROOT)
        require_profile(local)
        store = Store(local['data_dir'], local['profile'], 'user_input')
        if args.input:
            if args.input.stat().st_size > 5*1024*1024:
                raise ValueError('입력 크기 제한')
            added = import_events(json.loads(args.input.read_text(encoding='utf-8-sig')),
                                  EventStore(store), args.codes)
            result = dict(status='imported', added=added, coverage='사용자 제공 파일만 확인')
        else:
            result = refresh_events(ROOT, store, list(dict.fromkeys(args.codes)))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['status'] in ('complete','imported') else 2
    except Exception as error:
        parser.exit(1, '공시·뉴스 처리 실패 · '+type(error).__name__+'\n')


if __name__ == '__main__':
    sys.exit(main())
