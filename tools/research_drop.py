"""CLI: python tools/research_drop.py status | record --sha SHA --decision report|library|thesis|archive [--note TEXT]"""
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from investment.research_drop import status, record, DECISIONS

parser = argparse.ArgumentParser(description=__doc__)
sub = parser.add_subparsers(dest='command', required=True)
sub.add_parser('status')
rec = sub.add_parser('record')
rec.add_argument('--sha', required=True); rec.add_argument('--decision', required=True, choices=DECISIONS); rec.add_argument('--note', default='')
args = parser.parse_args()
try:
    result = status(ROOT) if args.command == 'status' else record(ROOT, args.sha, args.decision, note=args.note)
except ValueError as exc:
    print('중단:', exc); sys.exit(1)
print(json.dumps(result, ensure_ascii=False, indent=1))
