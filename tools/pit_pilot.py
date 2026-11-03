"""PIT pilot, OFFLINE commands only (design: docs/review/design_PIT_collection_adapter_2026-11-03.md).

  python tools/pit_pilot.py project --input projection_input.json
  python tools/pit_pilot.py verify  --input projection_input.json

The input file is {"receipts": [...pit_annual receipts...], "sessions": [...ISO dates...], "inventory": [...optional...]}.
Nothing here touches the network or the real data folders. Live collection is NOT implemented: `--live` is refused until the
OpenDART/viewer terms are checked by the user and the first live call is approved.
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0, str(ROOT))
from investment.pit_annual import project, project_all
from investment.pit_verify import verify


def _inventory_item_ok(item):
    if not isinstance(item, dict) or not isinstance(item.get('rcept_no'), str) or not re.fullmatch(r'\d{14}', item['rcept_no']):return False
    try:date.fromisoformat(item.get('rcept_dt'))
    except (TypeError, ValueError):return False
    return all(item.get(k) is None or isinstance(item[k], str) for k in ('company', 'stock_code', 'title_period'))


def check_shapes(data):
    """Fail with a ValueError (exit code 2) instead of an AttributeError/TypeError deep inside the checks."""
    if not isinstance(data, dict):raise ValueError('입력은 JSON 객체여야 합니다')
    receipts, sessions, inventory = data.get('receipts'), data.get('sessions'), data.get('inventory')
    if not isinstance(receipts, list) or not all(isinstance(r, dict) for r in receipts):raise ValueError('receipts는 객체 목록이어야 합니다')
    if not isinstance(sessions, list) or not all(isinstance(d, str) for d in sessions):raise ValueError('sessions는 날짜 문자열 목록이어야 합니다')
    if inventory is not None:
        if not isinstance(inventory, list) or not all(_inventory_item_ok(i) for i in inventory):
            raise ValueError('inventory는 형식이 맞는 rcept_no·rcept_dt(ISO 날짜)와 문자열 company·title_period를 가진 객체 목록이어야 합니다')
    return receipts, sessions, inventory


def run_first(args):
    """The only command that touches the network. Needs --confirm-first-call, --root and the OPENDART_API_KEY environment variable."""
    if not args.confirm_first_call or args.root is None:
        print('오류: 실제 호출에는 --root와 --confirm-first-call이 필요합니다(호출 계획은 plan-first로 확인).', file=sys.stderr);return 2
    import time
    import requests
    from investment.market_history import fetch_history
    from investment.pit_acquire import Budget
    from investment.pit_artifacts import ArtifactStore
    from investment.pit_first_call import run_first_call
    from investment.pit_live import OpenDart, key_from_env
    try:key = key_from_env()
    except ValueError as exc:
        print(f'오류: {exc}', file=sys.stderr);return 2
    budget = Budget(max_requests=12, min_interval=1.0, clock=time.monotonic, sleep=time.sleep)
    with requests.Session() as session:
        client = OpenDart(key, session=session, budget=budget)
        summary = run_first_call(client=client, store=ArtifactStore(Path(args.root) / '.local/pit-pilot/artifacts'), budget=budget, root=Path(args.root),
            today=date.today().isoformat(), calendar_fetch=lambda symbol, **kw: fetch_history(symbol, session=session, **kw))
    brief = dict(status=summary['status'], stop_reason=summary['stop_reason'], requests_used=summary['requests_used'],
        companies={k: dict(status=v['status'], receipts=len(v.get('receipts', [])), document=bool(v.get('document'))) for k, v in summary['companies'].items()})
    print(json.dumps(brief, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary['status'] == 'completed' else 3


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('command', choices=('project', 'verify', 'plan-first', 'run-first'))
    parser.add_argument('--input', type=Path)
    parser.add_argument('--root', type=Path, help='run-first: INVESTMENT 작업 폴더(.local/pit-pilot에 저장)')
    parser.add_argument('--confirm-first-call', action='store_true', help='run-first: 실제 호출을 하겠다는 명시적 확인')
    parser.add_argument('--live', action='store_true', help='refused: use run-first --confirm-first-call')
    args = parser.parse_args(argv)
    if args.live:
        print('오류: --live는 쓰지 않습니다. 첫 호출은 run-first --confirm-first-call로만 실행하며, 이 옵션은 구현되지 않았습니다.', file=sys.stderr);return 2
    if args.command == 'plan-first':
        from investment.pit_live import plan_first_call
        print(json.dumps(plan_first_call(today=date.today().isoformat()), ensure_ascii=False, indent=2));return 0
    if args.command == 'run-first':
        return run_first(args)
    if args.input is None:
        print('오류: --input이 필요합니다', file=sys.stderr);return 2
    try:
        data = json.loads(args.input.read_text(encoding='utf-8'))
        receipts, sessions, inventory = check_shapes(data)
        if args.command == 'project':
            result = {f'{c}|{b}': v for (c, b), v in project_all(receipts, sessions).items()}
        else:
            result = verify(receipts, sessions, inventory)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as exc:
        print(f'오류: {exc}', file=sys.stderr);return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if args.command == 'project' or result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
