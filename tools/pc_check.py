"""Offline, read-only worktree inspection. Never fetches, stages, commits or pushes."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from investment.local_config import load_local


def excluded(path):
    p = path.replace('\\', '/').lower()
    parts = set(p.split('/'))
    return (bool(parts & {'private_data', 'data', 'dist', '.venv', 'node_modules', '.local',
                         '.codex', '.claude', 'logs', '__pycache__'})
            or '/validation/current/' in '/' + p
            or Path(p).name.startswith('.env')
            or p.endswith(('config/local.json', 'config/runtime.local.json', 'secrets.toml'))
            or any(word in Path(p).name for word in ('holdings_research_private', 'investment_note'))
            or any(suffix in p for suffix in ('.sqlite', '.db', '.log')))


def inspect(root):
    root = Path(root).resolve()
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                              text=True, encoding='utf-8', errors='replace', timeout=20)
    top = git('rev-parse', '--show-toplevel')
    if top.returncode:
        return dict(repository=False, state='remote_pending', transfer='not_executed')
    root = Path(top.stdout.strip())  # Inspect the whole parent repository, never a nested substitute.
    # Entire remote URLs are withheld, not just userinfo: paths can themselves contain credentials.
    remotes = git('remote').stdout.splitlines()
    status = git('status', '--porcelain=v1', '--untracked-files=all').stdout.splitlines()
    branch = git('symbolic-ref', '--quiet', '--short', 'HEAD')
    upstream = git('rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}')
    active = []
    for name in ('MERGE_HEAD', 'rebase-merge', 'rebase-apply', 'CHERRY_PICK_HEAD', 'REVERT_HEAD'):
        result = git('rev-parse', '--git-path', name)
        path = Path(result.stdout.strip())
        if not path.is_absolute(): path = root / path
        if result.returncode == 0 and path.exists(): active.append(name)
    tracked = git('ls-files', '-z').stdout.split('\0')
    unsafe = [p for p in tracked if p and excluded(p)]
    ahead = behind = None
    if upstream.returncode == 0:
        counts = git('rev-list', '--left-right', '--count', 'HEAD...@{upstream}')
        if counts.returncode == 0: ahead, behind = map(int, counts.stdout.split())
    state = ('unfinished_operation' if active else 'tracked_private_paths' if unsafe else
             'dirty' if status else 'detached_head' if branch.returncode else
             'no_remote' if not remotes else 'no_upstream' if upstream.returncode else
             'diverged' if ahead and behind else 'local_ahead' if ahead else
             'local_behind' if behind else 'clean_cached_refs')
    return dict(repository=True, repository_root=top.stdout.strip(),
                branch=branch.stdout.strip() if branch.returncode == 0 else None,
                remote_count=len(remotes), remote_urls='withheld',
                upstream_configured=upstream.returncode == 0, ahead=ahead, behind=behind,
                changed_count=len(status), operations=active, tracked_private_paths=unsafe,
                state=state, remote_freshness='not_fetched', history_content_review='pending',
                transfer='not_executed')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['start', 'finish'], default='start')
    args = parser.parse_args()
    config = load_local(ROOT)
    result = inspect(ROOT)
    result.update(phase=args.phase, profile=config['profile'],
                  configured_data_dir=str(config['data_dir']),
                  scheduled_jobs_enabled=config['scheduled_jobs_enabled'],
                  remote_destination_confirmed=False,
                  note='Inspection only; cached refs are not proof of current remote state.')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
