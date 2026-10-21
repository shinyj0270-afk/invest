"""Manually start foreground reception. Ctrl+C stops; no token persistence."""
import argparse
import getpass
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from investment.local_config import load_local, require_profile
from investment.telegram_export import home, local_file
from investment.telegram_watch import watch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--channel', required=True)
    parser.add_argument('--interval', type=int, default=60)
    parser.add_argument('--cycles', type=int)
    args = parser.parse_args()
    profile = require_profile(load_local(ROOT))
    home(profile)
    settings = json.loads(local_file(ROOT, '.local/telegram-research/channels.json').read_text(encoding='utf-8'))
    matches = [c for c in settings['channels'] if c.get('key') == args.channel]
    if len(matches) != 1:
        raise ValueError('Exactly one confirmed channel required')
    token = os.environ.get('TELEGRAM_BOT_TOKEN') or getpass.getpass('Telegram bot token (hidden; not saved): ')
    if not token.strip():
        raise ValueError('Token missing')
    print('Foreground receiver running. Ctrl+C stops. No Library writes or AI calls.')
    try:
        watch(ROOT, profile, token.strip(), matches[0], interval=args.interval, cycles=args.cycles,
              report=lambda value: print(json.dumps(value), flush=True))
    finally:
        token = None


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('Receiver stopped; prior receipts preserved.')
    except Exception as error:
        # requests exception text includes the token-bearing URL: never print it.
        status = getattr(getattr(error, 'response', None), 'status_code', None)
        print('Receiver stopped: ' + type(error).__name__ + (f' HTTP {status}' if status else '') +
              '. Check channel lock, network, token and competing receivers. Prior receipts preserved.', file=sys.stderr)
        sys.exit(1)
