"""Prepare/import existing-session research; no network or model subprocess."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from investment.local_config import load_local, require_profile
from investment.research_library import Library
from investment.research_agents import approve
from investment.research_sessions import SessionRunner
from tools.research_agents import local_file, read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'packet', 'draft', 'review', 'revise', 'show', 'approve'))
    parser.add_argument('--input')
    parser.add_argument('--run-id')
    args = parser.parse_args()
    profile = require_profile(load_local(ROOT))
    lib = Library(local_file('.local/research-library'), profile)
    runner = SessionRunner(lib, local_file('.local/agents/session-runs'))
    if args.action == 'prepare':
        if not args.input: raise ValueError('Input required')
        job = runner.create(read(local_file(args.input)))
        runner.save(job)
    else:
        if not args.run_id or not re.fullmatch('[a-f0-9]{32}', args.run_id): raise ValueError('Run ID required')
        job = read(local_file(f'.local/agents/session-runs/{profile}/user_input/{args.run_id}/run.json'))
        if job['id'] != args.run_id: raise ValueError('Run identity mismatch')
        if args.action == 'packet':
            print(runner.packet(job)); return
        if args.action in ('draft', 'review', 'revise'):
            if not args.input: raise ValueError('Session result required')
            previous = job['state']
            job = runner.accept(job, {'draft':'research','review':'review','revise':'revision'}[args.action], read(local_file(args.input)))
            runner.save(job, previous)
        if args.action == 'approve':
            if not args.input: raise ValueError('Human approval required')
            revision = approve(lib, job, read(local_file(args.input)))
            print(json.dumps(dict(id=job['id'], kind='agent_note', revision=revision))); return
    print(json.dumps(job, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    try: main()
    except (ValueError, KeyError, TypeError, OSError):
        print('Research sessions: invalid input, state or review; existing results preserved.', file=sys.stderr)
        sys.exit(1)
