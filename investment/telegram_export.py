"""Offline metadata preparation from user-exported single-channel Desktop JSON.

No Telegram access, AI calls, registry permission changes, or operational DB writes.
"""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .research_library import day, fields, text, url

KST = timezone(timedelta(hours=9))
MAX_BYTES = 64 * 1024 * 1024


def home(profile):
    if profile != 'home':
        raise ValueError('Telegram preparation requires configured home PC')


def local_file(root, name):
    root = Path(root).resolve()
    base = (root / '.local').resolve()
    path = (Path(root) / name).resolve()
    if not base.is_relative_to(root) or not path.is_relative_to(base) or path == base:
        raise ValueError('Input and output must stay under ignored .local/')
    return path


def read_json(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Export too large; split the export period')
    return json.loads(raw.decode('utf-8-sig'))


def timestamp(value):
    if isinstance(value, bool) or not re.fullmatch(r'[0-9]{1,12}', str(value)):
        raise ValueError('Unix timestamp required; local display dates are not inferred')
    try:
        return datetime.fromtimestamp(int(value), timezone.utc)
    except (ValueError, OverflowError, OSError):
        raise ValueError('Unix timestamp out of range') from None


def positive_id(value):
    if type(value) is not int or value < 1:
        raise ValueError('Positive numeric channel/message ID required')
    return value


def external_links(message):
    links = set()
    entities = message.get('text_entities', [])
    if not isinstance(entities, list):
        raise ValueError('Invalid text entity collection')
    for entity in entities:
        if not isinstance(entity, dict):
            raise ValueError('Invalid text entity')
        candidate = entity.get('href') if entity.get('type') == 'text_link' else entity.get('text') if entity.get('type') == 'link' else None
        if not isinstance(candidate, str):
            continue
        try:
            url(candidate)
        except ValueError:
            continue
        host = urlsplit(candidate).hostname.lower()
        if any(host == domain or host.endswith('.' + domain) for domain in ('t.me', 'telegram.me', 'telegram.dog')):
            continue  # No private invites or unrelated chat links in derived output.
        links.add(candidate)
    return sorted(links)


def prepare(document, channel, start, end, checked_on, *, profile, previous=None):
    home(profile)
    fields(channel, ('key', 'expected_name', 'expected_id'))
    text(channel['key'], 100); text(channel['expected_name'], 200)
    for value in (start, end, checked_on):
        day(value)
    if not start <= end <= checked_on:
        raise ValueError('Invalid collection window')
    if not isinstance(document, dict) or document.get('type') not in ('public_channel', 'private_channel'):
        raise ValueError('Export one broadcast channel, not an account, group or private conversation')
    chat_id = positive_id(document.get('id'))
    if document.get('name') != channel['expected_name']:
        raise ValueError('Channel name mismatch; review local mapping')
    if channel['expected_id'] is not None and positive_id(channel['expected_id']) != chat_id:
        raise ValueError('Channel ID mismatch; preserve input and review')
    messages = document.get('messages')
    if not isinstance(messages, list) or len(messages) > 100000:
        raise ValueError('Bounded single-channel messages required')
    items, counts = {}, dict(service=0, outside_window=0, exact_duplicates=0)
    for message in messages:
        if not isinstance(message, dict):
            raise ValueError('Invalid message record')
        if message.get('type') == 'service':
            counts['service'] += 1
            continue
        if message.get('type') != 'message':
            raise ValueError('Unsupported message type')
        mid = positive_id(message.get('id'))
        published = timestamp(message.get('date_unixtime'))
        published_on = published.astimezone(KST).date().isoformat()
        if published_on > checked_on:
            raise ValueError('Message timestamp is after check date')
        if not start <= published_on <= end:
            counts['outside_window'] += 1
            continue
        edited = timestamp(message['edited_unixtime']) if message.get('edited_unixtime') else None
        if edited and (edited < published or edited.astimezone(KST).date().isoformat() > checked_on):
            raise ValueError('Invalid edited timestamp')
        # A digest detects changed text without copying its body into research output.
        payload = {key: message.get(key) for key in ('text', 'text_entities', 'edited_unixtime', 'media_type')}
        # Export paths/placeholders depend on download options, not message edits.
        payload.update(photo_present=bool(message.get('photo')), file_present=bool(message.get('file')))
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
        item = dict(message_id=mid, published_on=published_on, published_at_utc=published.isoformat(),
                    reference=f'https://t.me/c/{chat_id}/{mid}', edited_at_utc=edited.isoformat() if edited else None,
                    external_urls=external_links(message), content_digest=fingerprint)
        if mid in items:
            if items[mid] != item:
                raise ValueError('Conflicting duplicate message; review before preparation')
            counts['exact_duplicates'] += 1
        items[mid] = item
    ordered = [items[key] for key in sorted(items)]
    comparison = dict(status='first_export', new=len(items), unchanged=0, changed_ids=[], absent_ids=[])
    if previous is not None:
        if previous.get('schema') != 'telegram-export-metadata-1' or previous.get('channel_key') != channel['key'] or previous.get('chat_id') != chat_id:
            raise ValueError('Previous receipt belongs to a different channel or schema')
        if previous['window']['start'] != start or previous['window']['end'] != end:
            raise ValueError('Compare only the same collection window')
        prior = {item['message_id']: item for item in previous['items']}
        changed = sorted(key for key in items.keys() & prior.keys() if items[key] != prior[key])
        comparison = dict(status='compared', new=len(items.keys() - prior.keys()),
                          unchanged=sum(items[k] == prior[k] for k in items.keys() & prior.keys()),
                          changed_ids=changed, absent_ids=sorted(prior.keys() - items.keys()))
    batches = []
    for offset in range(0, len(ordered), 1000):
        batches.append(dict(start=start, end=end, checked_on=checked_on, missing='unknown',
            coverage_basis='User Desktop JSON; metadata only; KST days; export completeness unverified',
            entries=[{k: item[k] for k in ('message_id', 'published_on', 'reference')} for item in ordered[offset:offset+1000]]))
    return dict(schema='telegram-export-metadata-1', channel_key=channel['key'], chat_id=chat_id,
                identity_status='name_only_review_required' if channel['expected_id'] is None else 'id_and_name_matched',
                window=dict(start=start, end=end, checked_on=checked_on, timezone='Asia/Seoul'),
                counts=dict(input=len(messages), prepared=len(items), **counts), items=ordered, comparison=comparison,
                completeness='unverified', missing='unknown', batches=batches,
                import_status='not_imported; identity, links and existing channel permission require review',
                privacy='home_local_only; no original bodies, sender identities, attachments or credentials')


def prepare_file(root, profile, export_path, channel, start, end, checked_on, output_path, previous_path=None):
    home(profile)  # Must precede opening any input.
    source = local_file(root, export_path)
    output = local_file(root, output_path)
    if output.exists():
        raise ValueError('Output exists; choose a new receipt filename')
    previous = read_json(local_file(root, previous_path)) if previous_path else None
    result = prepare(read_json(source), channel, start, end, checked_on, profile=profile, previous=previous)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return result
