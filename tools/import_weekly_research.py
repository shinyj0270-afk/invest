"""Import hash-bound Markdown plus reviewed structured records from .local/."""
import argparse
import json
import sqlite3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from investment.local_config import load_local, require_profile
from investment.research_library import Library
from investment.weekly_research import read_bundle, import_week


def local_file(value):
    path = (ROOT / value).resolve()
    if not path.is_relative_to((ROOT / '.local').resolve()) or not path.is_file():
        raise ValueError('Existing input under ignored .local required')
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--markdown', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--zip')
    parser.add_argument('--apply', action='store_true', help='Default is validation only')
    args = parser.parse_args()
    profile = require_profile(load_local(ROOT))
    bundle = read_bundle(local_file(args.markdown), local_file(args.manifest), local_file(args.zip) if args.zip else None)
    library = Library(ROOT / '.local/research-library', profile)
    print(json.dumps(import_week(library, bundle, apply=args.apply), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, sqlite3.Error) as exc:
        print('Weekly import: '+str(exc), file=sys.stderr)
        sys.exit(1)
