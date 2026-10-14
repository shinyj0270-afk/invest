"""Run bounded research agents or approve a reviewed local note."""
import argparse
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from investment.local_config import load_local, require_profile
from investment.research_library import Library
from investment.research_agents import Runner, approve
from investment.agent_providers import credential_name


def local_file(value):
    base = (ROOT / '.local').resolve()
    path = (ROOT / value).resolve()
    if path == base or not path.is_relative_to(base): raise ValueError('Files must remain under .local')
    return path


def read(path):
    if path.stat().st_size > 200_000: raise ValueError('Input file too large')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('doctor', 'run', 'show', 'approve'))
    parser.add_argument('--input')
    parser.add_argument('--config', default='.local/agents/config.json')
    parser.add_argument('--run-id')
    args = parser.parse_args()
    profile = require_profile(load_local(ROOT))
    if args.action == 'doctor':
        result = dict(profile=profile, config_present=local_file(args.config).is_file(),
                      credentials={p: bool(os.environ.get(credential_name(p), '').strip()) for p in ('openai', 'anthropic')},
                      api_connection='not_tested')
    elif args.action == 'run':
        raise ValueError('API disabled by user policy; use tools/research_sessions.py')
        if not args.input: raise ValueError('--input required')
        config = read(local_file(args.config))
        # Missing credentials fail before opening the library or creating a run.
        for role in ('research', 'review'):
            if not os.environ.get(credential_name(config[role]['provider']), '').strip():
                raise ValueError('Required provider credential missing')
        lib = Library(local_file('.local/research-library'), profile)
        runner = Runner(lib, local_file('.local/agents/runs'), config)
        job = runner.run(read(local_file(args.input)))
        result = {k: job[k] for k in ('id', 'state', 'steps')}
        result['review_digest'] = job.get('review_digest')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if job['state'] == 'failed' else 0
    else:
        if not args.run_id or not re.fullmatch('[a-f0-9]{32}', args.run_id): raise ValueError('--run-id required')
        path = local_file(f'.local/agents/runs/{profile}/user_input/{args.run_id}/run.json')
        job = read(path)
        if job['id'] != args.run_id: raise ValueError('Run identity mismatch')
        if args.action == 'show': result = job
        else:
            if not args.input: raise ValueError('--input approval required')
            lib = Library(local_file('.local/research-library'), profile)
            revision = approve(lib, job, read(local_file(args.input)))
            result = dict(id=job['id'], kind='agent_note', revision=revision, state='human_reviewed_note_saved')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    try: sys.exit(main())
    except (ValueError, KeyError, TypeError, OSError):
        # Input files and provider errors can contain sensitive text: never echo them.
        print('Research agents: invalid/missing configuration, credential, input or review. Check local files.', file=sys.stderr)
        sys.exit(1)
