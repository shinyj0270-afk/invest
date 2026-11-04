"""Run UI tests against a backed-up, isolated sandbox."""
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0, str(ROOT))
from investment.isolated_run import run_isolated


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--keep', action='store_true')
    parser.add_argument('--test', nargs='+', dest='tests')
    args = parser.parse_args(argv)
    try:result = run_isolated(args.root, tests=args.tests, keep=args.keep)
    except Exception as exc:
        print(f'오류: {exc}', file=sys.stderr);return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
