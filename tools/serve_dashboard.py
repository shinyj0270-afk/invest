"""Launch the source-backed dashboard on this PC only."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from investment.live_dashboard import serve


def main():
    parser = argparse.ArgumentParser(description='INVESTMENT live dashboard')
    parser.add_argument('--port', type=int, default=8767)
    parser.add_argument('--saved-only',action='store_true',help='저장 시장자료만 열고 보유 동기화 실행')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    serve(ROOT, port=args.port,saved_only=args.saved_only)


if __name__ == '__main__':
    main()
