"""Create, list, or verify local data backups."""
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0, str(ROOT))
from investment import data_backup


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('backup');create.add_argument('--root', type=Path, default=ROOT)
    create.add_argument('--keep', type=int, default=10)
    listing = commands.add_parser('list');listing.add_argument('--root', type=Path, default=ROOT)
    verify = commands.add_parser('verify');verify.add_argument('backup_path', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'backup':result = data_backup.backup(args.root, keep=args.keep)
        elif args.command == 'list':result = data_backup.list_backups(args.root)
        else:result = data_backup.verify_backup(args.backup_path)
    except Exception as exc:
        print(f'오류: {exc}', file=sys.stderr);return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if args.command == 'verify' and not result['ok'] else 0


if __name__ == '__main__':
    sys.exit(main())
