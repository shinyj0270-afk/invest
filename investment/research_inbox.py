"""Local batch research ledger. No HTTP, AI process, scheduler or Library writes."""
import hashlib
import json
import os
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from .local_config import load_local, require_profile
from .research_library import url as checked_url
from .research_drop import status as drop_status

LIMIT = 5 * 1024 * 1024


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read(path):
    if path.stat().st_size > LIMIT:
        raise ValueError('Research metadata file exceeds size limit')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    content = json.dumps(value, ensure_ascii=False, indent=2)
    if len(content.encode()) > LIMIT:
        raise ValueError('Research metadata exceeds size limit')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.write-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def base_path(root):
    if require_profile(load_local(root)) != 'home':
        raise ValueError('Personal research inbox requires home profile')
    return Path(root)/'.local/research-inbox'


@contextmanager
def locked(base):
    base.mkdir(parents=True, exist_ok=True)
    path = base/'operation.lock'
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.close(fd)
        yield
    finally:
        path.unlink()


def ledger(base):
    path = base/'index.json'
    value = read(path) if path.exists() else {'schema': 1, 'items': {}}
    if value.get('schema') != 1 or not isinstance(value.get('items'), dict):
        raise ValueError('Research ledger invalid; preserve and inspect')
    return value


def canonical(value):
    parts = urlsplit(value)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in ('fbclid', 'gclid')]
    clean = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(query), ''))
    return checked_url(clean)


def inventory(root):
    """Read only known local receipts and pending drop files; never fetch URLs."""
    base_path(root)
    root = Path(root)
    settings = root/'.local/telegram-research/channels.json'
    configured = read(settings)['channels'] if settings.exists() else []
    permitted = {(c['key'], c['expected_id']) for c in configured if type(c.get('expected_id')) is int}
    items = {}
    for file in sorted((root/'.local/telegram-research/live').glob('*/receipt-*.json')):
        receipt = read(file)
        if receipt.get('schema') != 'telegram-live-metadata-1':
            raise ValueError('Unexpected live receipt schema')
        if (receipt.get('channel_key'), receipt.get('chat_id')) not in permitted:
            raise ValueError('Receipt is outside confirmed channel scope')
        for entry in receipt['items']:
            provenance = {'receipt': str(file.relative_to(root)), 'posted_on': entry['published_on'],
                          'reference': entry['reference'], 'content_digest': entry['content_digest']}
            links = entry.get('external_urls', [])
            if not isinstance(links, list) or len(links) > 100:
                raise ValueError('Unexpected reference count')
            candidates = links or [None]
            for original in candidates:
                problem = None
                try:
                    target = canonical(original) if original else None
                except (ValueError, TypeError):
                    target = None
                    problem = 'URL requires manual access review; not fetched'
                key = fingerprint(['url', original if problem else target]) if original else fingerprint(['metadata', entry['reference']])
                value = items.setdefault(key, {'id': key, 'kind': 'url' if original else 'metadata',
                    'url': target, 'provenance': [], 'restriction': 'home_local_only',
                    'problem': problem or (None if original else 'No external article URL; body not stored')})
                if provenance not in value['provenance']:
                    value['provenance'].append(provenance)
    drop = drop_status(root)
    for item in drop['pending']:
        if item['sha256'] is None:
            continue  # The drop status retains oversized files as an explicit exception.
        key = fingerprint(['file', item['sha256']])
        value = items.setdefault(key, {'id': key, 'kind': 'file', 'sha256': item['sha256'],
            'files': [], 'provenance': [], 'restriction': 'home_local_only', 'problem': None})
        value['files'].append(str(Path(drop['folder'])/item['name']))
    return items, [x for x in drop['pending'] if x['sha256'] is None]


def prepare(root, limit=20):
    base = base_path(root)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Batch size must be 1..100')
    found, exceptions = inventory(root)
    with locked(base):
        state = ledger(base)
        for key, item in found.items():
            previous = state['items'].get(key, {})
            state['items'][key] = dict(item, status=previous.get('status', 'pending'),
                                      note=previous.get('note'), batch=previous.get('batch'),
                                      history=previous.get('history', []))
        pending = [v for v in state['items'].values() if v['status'] == 'pending']
        selected = pending[:limit]
        packet = {'schema': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
                  'items': [{'source': v, 'source_digest': fingerprint(v)} for v in selected],
                  'remaining': max(0, len(pending)-len(selected)), 'drop_exceptions': exceptions,
                  'execution': 'current_session_only; no automatic AI calls',
                  'knowledge': [v['note'] for v in state['items'].values() if v.get('note')]}
        batch = uuid.uuid4().hex
        write(base/'index.json', state)
        write(base/'batches'/f'{batch}.json', packet)
    return {'batch_id': batch, 'packet': str(base/'batches'/f'{batch}.json'),
            'selected': len(selected), 'remaining': packet['remaining'], 'exceptions': len(exceptions),
            'attention': sum(v['status'] in ('blocked', 'metadata_only') for v in state['items'].values())}


def finish(root, batch, results):
    base = base_path(root)
    if not isinstance(batch, str) or len(batch) != 32 or any(c not in '0123456789abcdef' for c in batch):
        raise ValueError('Invalid batch identifier')
    packet = read(base/'batches'/f'{batch}.json')
    current_sources, _ = inventory(root)
    expected = {row['source']['id']: row for row in packet['items']}
    if not isinstance(results, list) or len(results) != len(expected):
        raise ValueError('Every selected item needs an explicit outcome')
    ids = [r.get('id') for r in results]
    if len(set(ids)) != len(ids) or set(ids) != set(expected):
        raise ValueError('Result IDs must match the batch exactly')
    validated = []
    required = {'id', 'outcome', 'reading_basis', 'title', 'summary', 'observations',
                'interpretation', 'counterpoints', 'open_questions', 'tags', 'companies', 'source_urls'}
    for result in results:
        if set(result) != required or result['outcome'] not in ('read', 'blocked', 'metadata_only'):
            raise ValueError('Explicit research result schema required')
        if result['reading_basis'] not in ('full_text', 'metadata', 'unavailable'):
            raise ValueError('Reading basis required')
        for name in ('title', 'summary', 'interpretation'):
            if not isinstance(result[name], str) or len(result[name]) > 6000:
                raise ValueError('Bounded research text required')
        for name in ('observations', 'counterpoints', 'open_questions', 'tags', 'companies', 'source_urls'):
            if not isinstance(result[name], list) or len(result[name]) > 30 or any(not isinstance(x, str) or len(x) > 2000 for x in result[name]):
                raise ValueError('Bounded text lists required')
        for link in result['source_urls']:
            canonical(link)
        source = expected[result['id']]['source']
        original_fields = {k: v for k, v in source.items() if k not in ('status', 'note', 'batch', 'history')}
        if current_sources.get(result['id']) != original_fields:
            raise ValueError('Source changed since packet; prepare a fresh batch')
        if result['outcome'] == 'read':
            if result['reading_basis'] != 'full_text' or not result['summary'].strip() or not result['observations']:
                raise ValueError('Read outcome requires full text, observations and summary')
            if source.get('problem') or source['kind'] == 'metadata':
                raise ValueError('Metadata-only item cannot become full-text research')
            if source['kind'] == 'url' and source['url'] not in [canonical(u) for u in result['source_urls']]:
                raise ValueError('Original article citation required')
        elif result['reading_basis'] == 'full_text' or result['observations'] or result['interpretation'] or result['summary']:
            raise ValueError('Unread items cannot contain inferred article claims')
        note = dict(result, human_reviewed=False, status='ai_draft', source=source,
                    researched_at=datetime.now(timezone.utc).isoformat())
        validated.append(note)
    with locked(base):
        state = ledger(base)
        stored = 0
        for note in validated:
            key = note['id']
            current = state['items'].get(key)
            # A previously completed batch can be acknowledged without writing again.
            if current and current.get('batch') == batch:
                old = read(base/current['note'])
                if any(old[k] != note[k] for k in required):
                    raise ValueError('Completed batch differs; preserve and create a new research revision')
            elif not current or fingerprint(current) != expected[key]['source_digest']:
                raise ValueError('Inbox changed since packet; prepare a fresh batch')
        for note in validated:
            key = note['id']
            if state['items'][key].get('batch') == batch:
                continue
            name = str(Path('knowledge')/key/(fingerprint(note)+'.json'))
            write(base/name, note)
            state['items'][key].update(status=note['outcome'], note=name, batch=batch)
            stored += 1
        write(base/'index.json', state)
    return {'stored': stored, 'duplicates': len(validated)-stored, 'human_reviewed': False}


def search(root, query=''):
    base = base_path(root)
    state = ledger(base)
    result = []
    for item in state['items'].values():
        names = list(dict.fromkeys(item.get('history', []) + ([item['note']] if item.get('note') else [])))
        for name in names:
            path = (base/name).resolve()
            if not path.is_relative_to((base/'knowledge').resolve()):
                raise ValueError('Invalid knowledge path')
            note = read(path)
            if query.casefold() in json.dumps(note, ensure_ascii=False).casefold():
                result.append(dict(note, is_current=name == item.get('note')))
    return result


def reopen(root, item_id, reason):
    base = base_path(root)
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        raise ValueError('Explicit recheck reason required')
    with locked(base):
        state = ledger(base)
        item = state['items'][item_id]
        if item.get('note'):
            item['history'] = list(dict.fromkeys(item.get('history', []) + [item['note']]))
        item.update(status='pending', batch=None)
        write(base/'index.json', state)
        audit = base/'rechecks'/(uuid.uuid4().hex+'.json')
        write(audit, {'id': item_id, 'reason': reason, 'created_at': datetime.now(timezone.utc).isoformat()})
    return {'id': item_id, 'status': 'pending', 'prior_notes_preserved': True}


def status(root):
    state = ledger(base_path(root))
    counts = {name: sum(v['status'] == name for v in state['items'].values())
              for name in ('pending', 'read', 'blocked', 'metadata_only')}
    return {'counts': counts, 'knowledge_notes': sum(bool(v.get('note')) for v in state['items'].values()),
            'execution': 'current_session_only', 'human_reviewed': False}
