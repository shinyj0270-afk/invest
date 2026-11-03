"""Record or summarize rule/threshold experiments (Q06). Writes only to <root>/.local/trial-log/<profile>.jsonl.

  python tools/trial_log.py record --profile work --entry-file entry.json
  python tools/trial_log.py summary --profile work

Every attempt, including rejected ones, is a trial. Keep `head_digest` from `summary` in the handoff as an external anchor.
"""
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0, str(ROOT))
from investment.trial_log import record, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--root', type=Path, default=ROOT)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('record', 'summary'):
        item = sub.add_parser(name);item.add_argument('--profile', required=True, choices=('work', 'home'))
        if name == 'record':item.add_argument('--entry-file', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'record':
            result = record(args.root, args.profile, json.loads(args.entry_file.read_text(encoding='utf-8')))
        else:
            result = summary(args.root, args.profile)
    except (ValueError, OSError) as exc:
        print(f'오류: {exc}', file=sys.stderr);return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
