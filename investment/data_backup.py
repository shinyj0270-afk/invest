"""Consistent local SQLite backups with manifests and bounded retention."""
import hashlib
import json
import shutil
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from .local_config import load_local


def _sha(path):
    with path.open('rb') as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b''):digest.update(block)
    return digest.hexdigest()


def _time(now):
    now = datetime.now(timezone.utc).astimezone() if now is None else now
    if not isinstance(now, datetime) or now.utcoffset() is None:raise ValueError('시간대가 있는 시각이 필요합니다')
    return now


def _inside(root, rel):
    path = Path(rel)
    if path.is_absolute() or '..' in path.parts:raise ValueError('상대 경로 확인 필요')
    result = (root / path).resolve()
    if not result.is_relative_to(root):raise ValueError('허용 경로 밖입니다')
    return result


def _integrity(path):
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as con:
        if con.execute('pragma integrity_check').fetchall() != [('ok',)]:raise ValueError('SQLite 무결성 검사 실패')


def _copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix != '.sqlite3':
        shutil.copyfile(source, target);return
    with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)) as src:
        with closing(sqlite3.connect(target)) as dst:src.backup(dst)
    _integrity(target)


def _sources(root):
    local = load_local(root);base = local['data_dir'] / local['profile']
    sources = set(p for p in base.rglob('*.sqlite3') if p.is_file())
    user = base / 'user_input'
    if user.is_dir():sources.update(p for p in user.iterdir() if p.is_file() and p.suffix != '.sqlite3')
    manual = local['manual_snapshot_file']
    if manual and manual.is_relative_to(root) and manual.is_file():sources.add(manual)
    if any(not p.resolve().is_relative_to(root) for p in sources):raise ValueError('백업 원본이 프로젝트 경로 밖입니다')
    if not sources:raise ValueError('백업할 파일이 없습니다')
    return sorted(sources, key=lambda p: p.relative_to(root).as_posix())


def list_backups(root):
    base = Path(root) / '.local/backups'
    if not base.is_dir():return []
    names = []
    for path in base.iterdir():
        if not path.is_dir() or path.is_symlink() or path.name.endswith('.partial'):continue
        try:manifest = json.loads((path / 'manifest.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):continue
        if isinstance(manifest, dict) and manifest.get('tool') == 'data_backup':names.append(path.name)
    return sorted(names, reverse=True)


def backup(root, *, now=None, keep=10):
    if type(keep) is not int or keep < 1:raise ValueError('보관 개수는 1 이상의 정수여야 합니다')
    now = _time(now);root = Path(root).resolve();sources = _sources(root)
    base = root / '.local/backups';base.mkdir(parents=True, exist_ok=True)
    name = now.strftime('%Y%m%d-%H%M%S');index = 1
    while True:
        target = base / (name if index == 1 else f'{name}-{index}')
        partial = target.with_name(target.name + '.partial')
        if not target.exists() and not partial.exists():break
        index += 1
    partial.mkdir()
    try:
        files = []
        for source in sources:
            rel = source.relative_to(root).as_posix();copy = partial / rel
            _copy(source, copy)
            files.append(dict(rel=rel, sha256=_sha(copy), size=copy.stat().st_size))
        manifest = dict(tool='data_backup', version=1, created_at=now.isoformat(), files=files)
        (partial / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        partial.rename(target)
    except BaseException:
        shutil.rmtree(partial);raise
    for old in list_backups(root)[keep:]:shutil.rmtree(base / old)
    return dict(path=str(target), files=files, created_at=now.isoformat())


def _verify_file(root, entry):
    rel = entry.get('rel', '?') if isinstance(entry, dict) else '?'
    try:
        path = _inside(root, rel)
        if not path.is_file():return [f'{rel}: 파일 누락']
        problems = []
        if path.stat().st_size != entry['size']:problems.append(f'{rel}: 크기 불일치')
        if _sha(path) != entry['sha256']:problems.append(f'{rel}: SHA256 불일치')
        if path.suffix == '.sqlite3':_integrity(path)
        return problems
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
        return [f'{rel}: 검증 실패 ({exc})']


def verify_backup(path):
    root = Path(path).resolve()
    try:
        manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
        if not isinstance(manifest, dict) or manifest.get('tool') != 'data_backup':raise ValueError('백업 표시 확인 필요')
        files = manifest.get('files')
        if not isinstance(files, list):raise ValueError('백업 파일 목록 확인 필요')
    except (OSError, ValueError) as exc:return dict(ok=False, checked=0, problems=[str(exc)])
    problems = [problem for entry in files for problem in _verify_file(root, entry)]
    return dict(ok=not problems, checked=len(files), problems=problems)
