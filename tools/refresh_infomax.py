"""One command for the same saved-file refresh offered in the app."""
import json
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from investment.auto_refresh import ensure_data

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--if-stale', action='store_true', help='시작 시 자동 갱신 정책 적용')
    args = parser.parse_args()
    result = ensure_data(ROOT, force=not args.if_stale)
    print(json.dumps(result['receipt'], ensure_ascii=False, indent=2))
    sys.exit(0 if result['receipt']['success'] else 1)
