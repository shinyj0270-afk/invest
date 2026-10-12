"""Local Research Library CLI. Inputs/outputs stay under ignored .local/ only."""
import argparse
import json
import sys
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from investment.local_config import load_local, require_profile
from investment.research_library import Library, MASTERS
from investment.core import digest
from investment.research_catalog import annotate, search, source_unique
from investment.telegram_research import channels, batch


def local_path(value):
    base = (ROOT / '.local').resolve()
    path = (ROOT / value).resolve()
    if not path.is_relative_to(base) or path == base:
        raise ValueError('Use a file under ignored .local/; never a tracked input/output')
    return path


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'): stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('masters', 'source', 'master', 'thesis', 'evidence', 'propose', 'channels', 'telegram', 'history', 'draft', 'approved-result', 'annotate', 'search'))
    parser.add_argument('--id')
    parser.add_argument('--kind', choices=('source', 'master', 'thesis', 'evidence', 'channel', 'coverage', 'telegram'))
    parser.add_argument('--input')
    parser.add_argument('--output')
    parser.add_argument('--query', default='')
    parser.add_argument('--person')
    parser.add_argument('--topic')
    parser.add_argument('--sector')
    parser.add_argument('--company')
    parser.add_argument('--stage')
    parser.add_argument('--event-id')
    parser.add_argument('--draft', help='Previously inspected local draft; required for approved-result')
    parser.add_argument('--expected-revision', type=int, default=0)
    args = parser.parse_args()
    if args.action == 'masters':
        print(json.dumps({k:dict(name=v[0], default_strategy=v[1], status='source_research_pending') for k,v in MASTERS.items()}, ensure_ascii=False, indent=2))
        return
    local = load_local(ROOT); profile = require_profile(local)
    # Gate Telegram before opening any supplied input file or creating a DB.
    if (args.action in ('channels', 'telegram') or args.kind in ('channel', 'coverage', 'telegram')) and profile != 'home':
        raise ValueError('Telegram processing requires configured home PC')
    if args.action not in ('channels', 'propose', 'search') and not args.id: raise ValueError('--id required')
    if args.action in ('source', 'master', 'thesis', 'evidence', 'propose', 'channels', 'telegram', 'approved-result', 'annotate') and not args.input:
        raise ValueError('--input required')
    output = local_path(args.output) if args.output else None
    if output and output.exists(): raise ValueError('Output exists; choose a new filename')
    value = json.loads(local_path(args.input).read_text(encoding='utf-8-sig')) if args.input else None
    lib = Library(local_path('.local/research-library'), profile)
    if args.action == 'search':
        result = search(lib, args.query, person=args.person, topic=args.topic, sector=args.sector, company=args.company, stage=args.stage, event_id=args.event_id)
    elif args.action == 'annotate':
        result = dict(revision=annotate(lib, args.kind, args.id, value, args.expected_revision))
    elif args.action == 'source' and args.expected_revision == 0:
        result = source_unique(lib, args.id, value)
    elif args.action in ('source', 'master', 'thesis', 'evidence'):
        result = dict(revision=getattr(lib, args.action)(args.id, value, args.expected_revision))
    elif args.action == 'channels': result = dict(revision=channels(lib, value, args.expected_revision))
    elif args.action == 'telegram': result = batch(lib, args.id, value)
    elif args.action == 'history':
        if not args.kind: raise ValueError('--kind required')
        result = lib.history(args.kind, args.id)
    elif args.action == 'draft': result = lib.draft(args.id)
    elif args.action == 'propose': result = lib.propose(value)
    else:
        if not args.draft: raise ValueError('--draft required for result approval')
        if local_path(args.draft).read_text(encoding='utf-8') != lib.draft(args.id):
            raise ValueError('Inspected draft differs from current draft; rereview required')
        result = lib.approved_result(args.id, value)
    encoded = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=2)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf-8', newline='') as f: f.write(encoded)
        print('Saved reviewed local output' if args.action == 'approved-result' else 'Saved local output')
        if args.action == 'draft': print('Draft content digest: '+digest(encoded))
    else: print(encoded)


if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, TypeError, KeyError, sqlite3.Error) as exc:
        print('Research Library: '+str(exc), file=sys.stderr)
        sys.exit(1)
