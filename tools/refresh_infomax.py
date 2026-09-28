"""One command for the same saved-file refresh offered in the app."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from investment.refresh import refresh

if __name__ == '__main__':
    try:
        result = refresh(ROOT)
        print(json.dumps(result['receipt'], ensure_ascii=False, indent=2))
        sys.exit(1 if result['receipt']['status'] == 'partial' else 0)
    except Exception as exc:
        print('갱신 실패: ' + str(exc), file=sys.stderr)
        sys.exit(1)
