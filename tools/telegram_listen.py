"""Minimal live receiver for one locked personal Telegram channel; no scheduling."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from investment.local_config import load_local, require_profile
from investment.telegram_export import local_file, read_json
from investment.telegram_listen import discover_checked, poll_file, token_from_env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    discover_p = sub.add_parser('discover', help='List chat IDs seen in pending updates; does not lock or write files')
    discover_p.add_argument('--limit', type=int, default=20)
    poll_p = sub.add_parser('poll', help='One poll cycle for a locked channel; run manually, not scheduled')
    poll_p.add_argument('--channels', required=True, help='Local channel mapping JSON (expected_id must be a locked number)')
    poll_p.add_argument('--channel', required=True)
    poll_p.add_argument('--state', required=True, help='Local offset/dedupe state file under .local/')
    poll_p.add_argument('--output-dir', required=True, help='Local receipt output directory under .local/')
    args = parser.parse_args()
    profile = require_profile(load_local(ROOT))
    token = token_from_env()
    if args.command == 'discover':
        result = discover_checked(profile, token, limit=args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    settings = read_json(local_file(ROOT, args.channels))
    matches = [item for item in settings['channels'] if item.get('key') == args.channel]
    if len(matches) != 1:
        raise ValueError('Exactly one configured channel must match')
    receipt = poll_file(ROOT, profile, token, matches[0], args.state, args.output_dir)
    print(f"Poll complete: accepted={receipt['counts']['accepted']} "
          f"rejected_wrong_chat={receipt['counts']['rejected_wrong_chat']} duplicate={receipt['counts']['duplicate']}")


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        print('Receiver failed: check home profile, TELEGRAM_BOT_TOKEN, channel lock and local paths. '
              'State and prior receipts were preserved.', file=sys.stderr)
        sys.exit(1)
