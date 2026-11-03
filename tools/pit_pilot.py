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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('command', choices=('project', 'verify'))
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--live', action='store_true', help='not implemented; refused')
    args = parser.parse_args(argv)
    if args.live:
        print('오류: 실제 호출은 구현되지 않았습니다. 약관 확인과 첫 호출 승인 이후 단계입니다.', file=sys.stderr);return 2
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
