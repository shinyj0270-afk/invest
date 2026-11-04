"""Copy only selected code and data into a marked, adapter-free sandbox."""
import json
import shutil
import subprocess
from pathlib import Path
from .local_config import load_local
from .data_backup import _inside, _sha, _time


def _folders(profile):
    return [f'data/{profile}/user_input', f'data/{profile}/fixture', 'private_data/infomax']


def _scan(root, folders):
    paths = [p for rel in folders for p in _inside(root, rel).rglob('*')
             if p.is_file() and p.resolve().is_relative_to(root)]
    return {p.relative_to(root).as_posix(): _sha(p) for p in sorted(paths)}


def _code(root, tracked):
    if tracked is None:
        tracked = subprocess.run(['git', 'ls-files', '-z'], cwd=root, capture_output=True,
                                 encoding='utf-8', check=True).stdout.rstrip('\0').split('\0')
    if not isinstance(tracked, list) or any(not isinstance(p, str) for p in tracked):
        raise ValueError('추적 파일은 문자열 목록이어야 합니다')
    accepted = []
    for rel in tracked:
        try:path = _inside(root, rel)
        except ValueError:continue
        normalized = path.relative_to(root).as_posix()
        if normalized.startswith(('data/', 'private_data/', '.local/')) or normalized == 'config/local.json':continue
        if path.is_file():accepted.append(normalized)
    return sorted(set(accepted))


def _destination(root, dest, now):
    base = (root / '.local/sandbox').resolve()
    target = (Path(dest) if dest is not None else base / now.strftime('%Y%m%d-%H%M%S-%f')).resolve()
    if target.parent != base:raise ValueError('샌드박스의 직접 하위 경로만 허용합니다')
    if dest is None:
        original = target;index = 2
        while target.exists():target = original.with_name(f'{original.name}-{index}');index += 1
    if target.exists():raise ValueError('샌드박스 경로가 이미 존재합니다')
    return target


def _config(root, dest, local, hashes):
    raw = json.loads((root / 'config/local.json').read_text(encoding='utf-8-sig'))
    manual = raw.get('manual_snapshot_file')
    extra = {}
    if isinstance(manual, str) and not Path(manual).is_absolute():
        try:rel = _inside(root, manual).relative_to(root).as_posix()
        except ValueError:rel = None
        if rel in hashes:extra = dict(manual_snapshot_file=manual)
    return dict(profile=local['profile'], project_root=str(dest), data_dir='data', **extra,
                enabled_data_adapters=[], scheduled_jobs_enabled=False,
                note='Isolated sandbox copy for tests; no adapter enabled')


def prepare(root, dest=None, *, tracked_files=None, now=None):
    root = Path(root).resolve();local = load_local(root);now = _time(now)
    if local['profile'] not in ('work', 'home'):raise ValueError('PC 프로필 확인 필요')
    code = _code(root, tracked_files);dest = _destination(root, dest, now)
    folders = _folders(local['profile']);hashes = _scan(root, folders)
    copied = sorted(set(code) | set(hashes));config = _config(root, dest, local, hashes)
    dest.mkdir(parents=True)
    try:
        for rel in copied:
            target = dest / rel;target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / rel, target)
        (dest / 'config').mkdir(exist_ok=True)
        (dest / 'config/local.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
        marker = dict(tool='sandbox', version=1, created_at=now.isoformat(), source_root=str(root),
                      profile=local['profile'], folders=folders, source_hashes=hashes)
        (dest / 'SANDBOX.json').write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding='utf-8')
    except BaseException:
        shutil.rmtree(dest);raise
    return dict(dest=str(dest), source_hashes=hashes, copied=copied)


def _marker(dest):
    try:
        marker = json.loads((Path(dest) / 'SANDBOX.json').read_text(encoding='utf-8'))
        if not isinstance(marker, dict) or marker.get('tool') != 'sandbox':raise ValueError('표시 오류')
        root = Path(marker['source_root'])
        if not root.is_absolute() or marker['profile'] not in ('work', 'home'):raise ValueError('원본 경로 또는 프로필 오류')
        if marker['folders'] != _folders(marker['profile']):raise ValueError('원본 폴더 목록 오류')
        hashes = marker['source_hashes']
        if not isinstance(hashes, dict) or any(not isinstance(v, str) for v in hashes.values()):raise ValueError('해시 목록 오류')
        for rel in hashes:_inside(root.resolve(), rel)
        return marker
    except (OSError, ValueError, KeyError, TypeError) as exc:raise ValueError('유효한 샌드박스 표시가 필요합니다') from exc


def check_source(dest):
    marker = _marker(dest);before = marker['source_hashes']
    after = _scan(Path(marker['source_root']).resolve(), marker['folders'])
    changed = sorted(rel for rel in before.keys() & after.keys() if before[rel] != after[rel])
    missing = sorted(before.keys() - after.keys());added = sorted(after.keys() - before.keys())
    return dict(unchanged=not (changed or missing or added), changed=changed, missing=missing, added=added)


def remove(dest):
    dest = Path(dest).resolve();marker = _marker(dest)
    base = (Path(marker['source_root']) / '.local/sandbox').resolve()
    if dest.parent != base:raise ValueError('샌드박스의 직접 하위 경로만 삭제할 수 있습니다')
    shutil.rmtree(dest)
