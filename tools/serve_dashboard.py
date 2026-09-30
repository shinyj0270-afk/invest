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
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    serve(ROOT, port=args.port)


if __name__ == '__main__':
    main()
