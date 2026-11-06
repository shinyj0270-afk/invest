"""Read-only session summary; optional network access is limited to git fetch."""
import argparse
from datetime import date
import os
from pathlib import Path
import re
import socket
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def summary(root=ROOT, *, profile=None, fetch=False):
    def git(*args):
        try:
            return subprocess.run(
                ['git', '-C', str(root), *args], capture_output=True,
                text=True, encoding='utf-8', errors='replace', timeout=30,
                env=dict(os.environ, GIT_OPTIONAL_LOCKS='0'))
        except (OSError, subprocess.TimeoutExpired):
            return subprocess.CompletedProcess(args, 1, '', '')

    freshness = '캐시 (fetch 미실행)'
    if fetch:
        freshness = ('fetch 성공' if git('fetch', 'origin', 'main').returncode == 0
                     else '미확인 (fetch 실패; 아래 수치는 캐시)')
    branch = git('symbolic-ref', '--quiet', '--short', 'HEAD')
    head = git('rev-parse', '--short', 'HEAD')
    counts = git('rev-list', '--left-right', '--count', 'HEAD...origin/main')
    pair = counts.stdout.split() if counts.returncode == 0 else []
    relation = (f'{pair[0]}/{pair[1]}' if len(pair) == 2
                and all(n.isdecimal() for n in pair) else '미확인')
    status = git('status', '--porcelain=v1', '-z', '--untracked-files=all')
    changed = '미확인'
    if status.returncode == 0:
        records = iter(status.stdout.split('\0'))
        count = 0
        for record in records:
            if not record:
                continue
            count += 1
            if 'R' in record[:2] or 'C' in record[:2]:
                next(records, None)  # Rename/copy source is not another change.
        changed = str(count)
    updated = '미확인'
    try:
        # Read only the small digest, never local config or the state archive.
        with (Path(root) / 'STATE_DIGEST.md').open(encoding='utf-8') as stream:
            digest = stream.read(3073)
        match = re.search(r'^마지막 갱신일: (\d{4}-\d{2}-\d{2})', digest, re.M)
        if match:
            updated = date.fromisoformat(match[1]).isoformat()
    except (OSError, UnicodeError, ValueError):
        pass
    return [
        f'hostname: {socket.gethostname()}',
        f'branch: {branch.stdout.strip() if branch.returncode == 0 else "미확인 (detached 또는 Git 오류)"}',
        'remote ref: origin/main',
        f'ahead/behind: {relation}',
        f'remote freshness: {freshness}',
        f'uncommitted files: {changed}',
        f'HEAD: {head.stdout.strip() if head.returncode == 0 else "미확인"}',
        f'PC profile: {profile + " (명시 입력, 설정 대조 미확인)" if profile else "미확인"}',
        f'STATE_DIGEST updated: {updated}',
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch', action='store_true', help='git fetch origin main only')
    parser.add_argument('--profile', choices=['work', 'home'], help='Explicit user-confirmed profile; no config access')
    args = parser.parse_args()
    print('\n'.join(summary(profile=args.profile, fetch=args.fetch)))


if __name__ == '__main__':
    main()
