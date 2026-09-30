"""Verify saved market data using the existing portfolio engine; no network."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from investment.holdings_bridge import holdings_input


def verify(snapshot, holdings=None, policy=None, as_of=None, events=None):
    payload = dict(market=holdings_input(snapshot, as_of, events), holdings=holdings, policy=policy or {})
    run = subprocess.run(['node', str(ROOT/'tools/portfolio_check.js')],
                         input=json.dumps(payload, ensure_ascii=False, allow_nan=False),
                         capture_output=True, text=True, encoding='utf-8', timeout=30)
    if run.returncode:
        raise ValueError('입력 계약 또는 포트폴리오 제약 검사 실패')
    return json.loads(run.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True, type=Path)
    parser.add_argument('--holdings', type=Path, help='선택: 사용자가 작성한 보유·연구 JSON')
    parser.add_argument('--policy', type=Path, help='선택: 사용자가 정한 구성 설정 JSON')
    parser.add_argument('--as-of', help='생략 시 현재 한국 날짜; 과거일 지정 시 당시 이용 가능성 검증은 별도')
    parser.add_argument('--output', type=Path, help='선택: 새로운 로컬 결과 파일; 기존 파일 덮어쓰기 금지')
    parser.add_argument('--events-cache', action='store_true', help='현재 PC의 공시·뉴스 검토 상태 연결 (과거 검토 이력 아님)')
    args = parser.parse_args()
    def read(path):
        if path.stat().st_size > 30*1024*1024:
            raise ValueError('입력 파일 크기 제한 초과')
        return json.loads(path.read_text(encoding='utf-8-sig'))
    try:
        snapshot = read(args.snapshot)
        events = None
        if args.events_cache:
            from investment.local_config import load_local, require_profile
            from investment.market_events import EventStore
            from investment.store import Store
            local = load_local(ROOT)
            require_profile(local)
            events = EventStore(Store(local['data_dir'],local['profile'],'user_input')).pending(
                [r['code'] for r in snapshot['companies']],args.as_of)
        result = verify(snapshot, read(args.holdings) if args.holdings else None,
                        read(args.policy) if args.policy else None, args.as_of, events)
        result['event_cache_connected'] = args.events_cache
        encoded = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open('x', encoding='utf-8') as output:
                output.write(encoded+'\n')
        print(encoded)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, '검증 실행 실패 · '+type(error).__name__+'\n')


if __name__ == '__main__':
    main()
