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
    latest, histories = {}, {}
    for kind, key, revision, created, payload in rows:
        value = json.loads(payload)
        # A work DB must never import or display home Telegram research.
        if profile == 'work' and (kind in ('telegram', 'coverage', 'channel') or kind == 'source' and value.get('origin') == 'telegram'):
            raise ValueError('Home Telegram research cannot be displayed on work')
        latest[kind, key] = dict(id=key, revision=revision, recorded_at=created, value=value)
        histories.setdefault((kind, key), []).append(latest[kind, key])
    hidden = {(v['value']['kind'], v['value']['record_id']) for (kind, _), v in latest.items() if kind == 'catalog' and v['value']['stage'] in ('deleted', 'excluded')}
    # Revocation on home applies to every historical derivation as well.
    registry = latest.get(('channel', 'registry'), {}).get('value', {})
    for (kind, key), row in latest.items():
        if kind == 'source' and row['value'].get('origin') == 'telegram':
            channel = next((c for c in registry.get('core', []) + registry.get('auxiliary', []) if c['id'] == row['value'].get('channel_id')), None)
            try:
                from .telegram_research import permission
                if not channel or not channel['enabled']: raise ValueError('Revoked')
                permission(channel['permission'])
            except (ValueError, KeyError, TypeError):
                hidden.add((kind, key))
    # Deleted/excluded provenance also hides dependent cards and theses in this projection.
    changed = True
    while changed:
        changed = False
        for kind, key in latest:
            if kind not in ('master', 'thesis', 'evidence'): continue
            dependencies = []
            for row in histories[kind, key]:
                value = row['value']
                dependencies += [('source', sid) for sid in value.get('source_ids', value.get('seed_source_ids', []))]
                dependencies += [('master', mid) for mid in value.get('master_ids', [])]
                if kind == 'evidence': dependencies.append(('thesis', value['thesis_id']))
            if kind == 'thesis':
                dependencies += [('evidence', eid) for (ek, eid), revisions in histories.items()
                                 if ek == 'evidence' and any(r['value']['thesis_id'] == key for r in revisions)]
            if (kind, key) not in hidden and any(dep in hidden or dep not in latest for dep in dependencies):
                hidden.add((kind, key)); changed = True
    def project(k, key):
        row = latest[k, key]
        metadata = next((v['value'] for (t, _), v in latest.items() if t == 'catalog' and v['value']['kind'] == k and v['value']['record_id'] == key), {})
        source_ids = []
        for revision in histories[k, key]:
            value = revision['value']
            source_ids.extend(value.get('source_ids', value.get('seed_source_ids', [])))
            for mid in value.get('master_ids', []):
                for master_revision in histories['master', mid]:
                    source_ids.extend(master_revision['value']['source_ids'])
        evidence = [project('evidence', eid) for (ek, eid), revisions in histories.items()
                    if k == 'thesis' and ek == 'evidence' and (ek, eid) not in hidden
                    and any(r['value']['thesis_id'] == key for r in revisions)]
        for item in evidence:
            source_ids.extend(src['id'] for src in item['provenance'])
        return dict(row, kind=k, metadata=metadata,
            stage=metadata.get('stage', 'raw' if k == 'source' else 'derived'),
            catalog_history=[revision for (t, _), revisions in histories.items() if t == 'catalog' for revision in revisions if revision['value']['kind'] == k and revision['value']['record_id'] == key],
            history=histories[k, key], evidence=evidence,
            provenance=[latest['source', sid] for sid in dict.fromkeys(source_ids)])

    for kind, target in (('source', 'sources'), ('master', 'cards'), ('thesis', 'theses')):
        for (k, key), row in latest.items():
            if k != kind or (k, key) in hidden: continue
            result[target].append(project(k, key))
    result['status'] = 'ready'
    return result
