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
    for kind, target in (('source', 'sources'), ('master', 'cards'), ('thesis', 'theses')):
        result[target] = [v for (k, _), v in latest.items() if k == kind]
    result['status'] = 'ready'
    return result
