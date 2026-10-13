"""Prepare personal Desktop exports offline; requires this checkout's home profile."""
import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from investment.local_config import load_local, require_profile
from investment.telegram_export import KST, home, local_file, read_json, prepare_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--channels', required=True, help='Local channel mapping JSON')
    parser.add_argument('--channel', required=True)
    parser.add_argument('--input', required=True, help='Single-channel result.json under .local/')
    parser.add_argument('--start', required=True, help='Inclusive KST day YYYY-MM-DD')
    parser.add_argument('--end', required=True, help='Inclusive KST day YYYY-MM-DD')
    parser.add_argument('--output', required=True)
    parser.add_argument('--previous', help='Previous receipt for the same channel and window')
    args = parser.parse_args()
    profile = require_profile(load_local(ROOT))
    home(profile)
    settings = read_json(local_file(ROOT, args.channels))
    matches = [item for item in settings['channels'] if item.get('key') == args.channel]
    if len(matches) != 1:
        raise ValueError('Exactly one configured channel must match')
    result = prepare_file(ROOT, profile, args.input, matches[0], args.start, args.end,
                          datetime.now(KST).date().isoformat(), args.output, args.previous)
    print(f"Prepared {result['counts']['prepared']} references; DB import not executed; completeness unverified")
    print('Identity:', result['identity_status'], '| comparison:', result['comparison']['status'])


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, AttributeError):
        print('Preparation failed: check home profile, local paths, channel identity, dates and JSON format. Original input was preserved.', file=sys.stderr)
        sys.exit(1)
