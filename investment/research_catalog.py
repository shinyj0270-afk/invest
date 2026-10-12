"""Local metadata over existing Library revisions; no retrieval or model calls."""
from copy import deepcopy
import json
from .core import digest
from .research_library import fields, text, day, instruments, MASTERS

KINDS = ('source', 'master', 'thesis', 'evidence')
STAGES = ('raw', 'derived', 'curated', 'excluded', 'deleted')

def identity(kind, key):
    if kind not in KINDS: raise ValueError('Catalog target kind invalid')
    text(key, 100)
    return digest([kind, key])

def annotation(library, kind, key):
    rows = library.history('catalog', identity(kind, key))
    return rows[-1] if rows else None

def annotate(library, kind, key, value, expected_revision=0):
    identity(kind, key)
    prior = annotation(library, kind, key)
    if prior and prior['value']['stage'] == 'deleted':
        rows = library.history(kind, key)
        if not rows: raise ValueError('Target not found')
        target = rows[-1]['value']
        if kind == 'source' and target['origin'] == 'telegram': library._telegram_allowed(target['channel_id'])
        for sid in target.get('source_ids', target.get('seed_source_ids', [])): library.get('source', sid)
    else:
        target = library.get(kind, key)
    fields(value, ('stage', 'topic', 'sector', 'tags', 'persons', 'instruments', 'event_id',
                   'summary', 'source_note', 'reason', 'reviewed_by', 'reviewed_on', 'human_reviewed'))
    if value['stage'] not in STAGES: raise ValueError('Explicit material stage required')
    for name in ('topic', 'sector', 'source_note', 'reason'): text(value[name])
    for name in ('tags', 'persons'):
        values = value[name]
        if not isinstance(values, list) or len(values) > 30 or len(set(values)) != len(values):
            raise ValueError('Bounded unique metadata list required')
        for item in values: text(item, 100)
    if not set(value['persons']) <= set(MASTERS): raise ValueError('Unknown master')
    instruments(value['instruments'])
    if value['event_id'] is not None: text(value['event_id'], 100)
    if value['summary'] is not None: text(value['summary'])
    if value['stage'] == 'raw' and kind != 'source':
        raise ValueError('Only source references can be raw')
    if value['stage'] == 'raw' and value['summary'] is not None:
        raise ValueError('Raw references cannot contain interpretations')
    if not isinstance(value['human_reviewed'], bool): raise ValueError('Review flag required')
    if value['reviewed_on'] is not None:
        day(value['reviewed_on'])
        if value['reviewed_on'] < target.get('accessed_on', target.get('as_of', '0001-01-01')):
            raise ValueError('Review predates referenced material')
    if value['reviewed_by'] is not None: text(value['reviewed_by'], 100)
    if value['stage'] == 'curated' and (not value['human_reviewed'] or not value['reviewed_by'] or not value['reviewed_on']):
        raise ValueError('Curated requires explicit human review')
    if value['human_reviewed'] and (not value['reviewed_by'] or not value['reviewed_on']):
        raise ValueError('Reviewer and review date required')
    # Provenance stays on immutable records; this annotation never relabels a source.
    payload = dict(kind=kind, record_id=key, **deepcopy(value))
    return library._put('catalog', identity(kind, key), payload, expected_revision)

def search(library, query='', *, person=None, topic=None, sector=None, company=None, stage=None, event_id=None):
    if stage is not None and stage not in STAGES: raise ValueError('Unknown stage')
    if person is not None and person not in MASTERS: raise ValueError('Unknown master')
    with library.connect() as db:
        rows = db.execute("SELECT kind,id,revision,payload FROM records WHERE kind IN ('source','master','thesis','evidence') ORDER BY revision").fetchall()
    latest = {(kind,key):(revision,json.loads(payload)) for kind,key,revision,payload in rows}
    result = []
    for (kind,key), (revision,value) in latest.items():
        note = annotation(library, kind, key)
        meta = note['value'] if note else {}
        lifecycle = meta.get('stage', 'raw' if kind == 'source' else 'derived')
        if lifecycle in ('deleted','excluded') and stage != lifecycle: continue
        if stage and stage != lifecycle: continue
        persons = set(meta.get('persons', [])) | ({value['master']} if kind == 'master' else set())
        if person and person not in persons: continue
        if topic and topic not in (meta.get('topic'), value.get('theme')): continue
        if sector and sector not in (meta.get('sector'), value.get('sector')): continue
        links = meta.get('instruments', value.get('instruments', []))
        if company and not any(x['code'] == company for x in links): continue
        if event_id and meta.get('event_id') != event_id: continue
        haystack = json.dumps([value,meta], ensure_ascii=False).casefold()
        if query and query.casefold() not in haystack: continue
        if lifecycle == 'deleted':
            # Tombstone metadata can also be Telegram-derived. Recheck its provenance
            # without get(), which intentionally refuses a deleted source itself.
            try:
                source_ids = [key] if kind == 'source' else list(value.get('source_ids', value.get('seed_source_ids', [])))
                for mid in value.get('master_ids', []):
                    source_ids.extend(library.history('master', mid)[-1]['value']['source_ids'])
                for sid in source_ids:
                    src = library.history('source', sid)[-1]['value']
                    if src['origin'] == 'telegram': library._telegram_allowed(src['channel_id'])
            except (ValueError, IndexError):
                continue
            result.append(dict(kind=kind,id=key,revision=revision,catalog_revision=note['revision'],stage=lifecycle,value={},metadata=meta,provenance=[]))
            continue
        # Recheck profile/permission for each provenance before exposing an item.
        try:
            checked = library.get(kind, key)
            sources = [key] if kind == 'source' else value.get('source_ids', value.get('seed_source_ids', []))
            if kind == 'thesis':
                sources = list(sources) + [sid for mid in value['master_ids'] for sid in library.get('master', mid)['source_ids']]
            provenance = [dict(id=sid, **library.get('source', sid)) for sid in dict.fromkeys(sources)]
            if (kind != 'source' or stage != 'excluded') and any((annotation(library, 'source', sid) or {}).get('value', {}).get('stage') in ('deleted','excluded') for sid in sources):
                continue
        except ValueError:
            continue  # revoked/unavailable provenance never becomes reusable search data
        result.append(dict(kind=kind,id=key,revision=revision,catalog_revision=note['revision'] if note else 0,stage=lifecycle,value=checked,
                           metadata=meta,provenance=provenance))
    return result

def source_unique(library, key, value):
    with library.connect() as db:
        rows = db.execute("SELECT id,payload FROM records WHERE kind='source'").fetchall()
    for stored_key,payload in rows:
        stored=json.loads(payload)
        if stored.get('url') == value.get('url'):
            library.get('source', stored_key)  # enforce current provenance gate on retry
            if stored != value: raise ValueError('Source URL already registered with different metadata; annotate correction')
            return dict(id=stored_key,revision=1,duplicate=True)
    return dict(id=key,revision=library.source(key,value),duplicate=False)
