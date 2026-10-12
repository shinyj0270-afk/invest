"""Read-only dashboard projection. Never creates or migrates a research DB."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from .local_config import load_local, require_profile
from .research_library import MASTERS


def view(root):
    profile = require_profile(load_local(root))
    result = dict(status='empty', profile=profile, masters=[dict(id=k, name=v[0], strategy=v[1]) for k, v in MASTERS.items()], cards=[], theses=[], sources=[])
    path = Path(root)/'.local'/'research-library'/profile/'user_input'/'research_library.sqlite3'
    if not path.exists():
        return result
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)) as db:
        rows = db.execute('SELECT kind,id,revision,created,payload FROM records ORDER BY revision').fetchall()
    latest = {}
    for kind, key, revision, created, payload in rows:
        value = json.loads(payload)
        # A work DB must never import or display home Telegram research.
        if profile == 'work' and (kind in ('telegram', 'coverage', 'channel') or kind == 'source' and value.get('origin') == 'telegram'):
            raise ValueError('Home Telegram research cannot be displayed on work')
        latest[kind, key] = dict(id=key, revision=revision, recorded_at=created, value=value)
    hidden = {(v['value']['kind'], v['value']['record_id']) for (kind, _), v in latest.items() if kind == 'catalog' and v['value']['stage'] in ('deleted', 'excluded')}
    # Deleted/excluded provenance also hides dependent cards and theses in this projection.
    changed = True
    while changed:
        changed = False
        for (kind, key), row in latest.items():
            if kind not in ('master', 'thesis'): continue
            value = row['value']
            dependencies = [('source', sid) for sid in value.get('source_ids', value.get('seed_source_ids', []))]
            dependencies += [('master', mid) for mid in value.get('master_ids', [])]
            if (kind, key) not in hidden and any(dep in hidden for dep in dependencies):
                hidden.add((kind, key)); changed = True
    for kind, target in (('source', 'sources'), ('master', 'cards'), ('thesis', 'theses')):
        result[target] = [v for (k, _), v in latest.items() if k == kind and (k, v['id']) not in hidden]
    result['status'] = 'ready'
    return result
