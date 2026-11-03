"""PIT pilot, OFFLINE commands only (design: docs/review/design_PIT_collection_adapter_2026-11-03.md).

  python tools/pit_pilot.py project --input projection_input.json
  python tools/pit_pilot.py verify  --input projection_input.json

The input file is {"receipts": [...pit_annual receipts...], "sessions": [...ISO dates...], "inventory": [...optional...]}.
Nothing here touches the network or the real data folders. Live collection is NOT implemented: `--live` is refused until the
OpenDART/viewer terms are checked by the user and the first live call is approved.
"""
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0, str(ROOT))
from investment.pit_annual import project, project_all
from investment.pit_verify import verify


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
        receipts, sessions = data['receipts'], data['sessions']
        if args.command == 'project':
            result = {f'{c}|{b}': v for (c, b), v in project_all(receipts, sessions).items()}
        else:
            result = verify(receipts, sessions, data.get('inventory'))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'오류: {exc}', file=sys.stderr);return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if args.command == 'project' or result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
