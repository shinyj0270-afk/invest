"""PC-local research drop folder. Lists unprocessed files and records the user's
decision; never moves, deletes, registers or uploads anything by itself."""
import hashlib, json, os
from datetime import date
from pathlib import Path
from .local_config import load_local, require_profile

DECISIONS = ('report', 'library', 'thesis', 'archive')
SKIP_SUFFIXES = {'.crdownload', '.part', '.tmp', '.lnk', '.download'}
MAX_BYTES = 50 * 1024 * 1024


def _paths(root):
    cfg = load_local(root); profile = require_profile(cfg)
    configured = cfg.get('research_drop_inbox')
    folder = Path(configured).expanduser() if configured else Path.home()/'Downloads'/'INVESTMENT 자료'
    if not folder.is_absolute(): folder = Path(root)/folder
    return profile, folder.resolve(), Path(root)/'.local'/'research-drop'/profile/'ledger.json'


def _ledger(path):
    try:
        files = json.loads(path.read_text(encoding='utf-8'))['files']
        return files if isinstance(files, dict) else {}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def _items(folder):
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.name.startswith(('.', '~$')) or path.suffix.lower() in SKIP_SUFFIXES: continue
        size = path.stat().st_size
        if size > MAX_BYTES:
            yield dict(name=path.name, size=size, sha256=None, status='too_large'); continue
        yield dict(name=path.name, size=size, sha256=hashlib.sha256(path.read_bytes()).hexdigest(), status='pending')


def status(root):
    profile, folder, ledger_path = _paths(root)
    folder.mkdir(parents=True, exist_ok=True)
    ledger = _ledger(ledger_path); items = list(_items(folder))
    pending = [i for i in items if i['sha256'] not in ledger]
    return dict(profile=profile, folder=str(folder), pending=pending, decided=len(items) - len(pending))


def record(root, sha256, decision, *, note='', decided_on=None):
    profile, folder, ledger_path = _paths(root)
    if decision not in DECISIONS: raise ValueError('decision must be one of ' + ', '.join(DECISIONS))
    decided_on = decided_on or date.today().isoformat()
    date.fromisoformat(decided_on)
    match = next((i for i in _items(folder) if i['sha256'] == sha256), None) if folder.is_dir() else None
    if not match: raise ValueError('File with this SHA256 is not in the drop folder')
    ledger = _ledger(ledger_path)
    ledger[sha256] = dict(name=match['name'], size=match['size'], decision=decision, note=str(note), decided_on=decided_on)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    temp = ledger_path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(dict(folder=str(folder), files=ledger), ensure_ascii=False, indent=1), encoding='utf-8')
    os.replace(temp, ledger_path)
    return ledger[sha256]
