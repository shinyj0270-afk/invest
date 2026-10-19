"""Minimal live receiver for one locked personal Telegram channel via Bot API getUpdates.

No scheduling/daemon, no raw message bodies/senders, no Research Library writes.
The caller runs this manually per poll cycle; connecting to the real API with a
real bot token and locking the real chat id are user actions outside this module.
"""
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import requests

from .telegram_export import KST, home, local_file

API_URL = 'https://api.telegram.org/bot{token}/{method}'
MAX_UPDATES = 200


def token_from_env():
    value = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not value or not value.strip():
        raise ValueError('Set TELEGRAM_BOT_TOKEN in the environment; tokens are never read from files or chat')
    return value.strip()


def default_fetch(token, method, params):
    response = requests.get(API_URL.format(token=token, method=method), params=params, timeout=20)
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict) or not body.get('ok'):
        raise ValueError('Telegram API returned a not-ok response')
    return body['result']


def utf16_substring(text, offset, length):
    units = text.encode('utf-16-le')
    chunk = units[offset * 2: (offset + length) * 2]
    return chunk.decode('utf-16-le', errors='strict')


def link_entities(text, entities):
    if not isinstance(entities, list):
        return []
    links = set()
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        kind = entity.get('type')
        try:
            offset, length = int(entity['offset']), int(entity['length'])
        except (KeyError, TypeError, ValueError):
            continue
        if kind == 'text_link' and isinstance(entity.get('url'), str):
            candidate = entity['url']
        elif kind == 'url':
            try:
                candidate = utf16_substring(text, offset, length)
            except (UnicodeDecodeError, IndexError):
                continue
        else:
            continue
        if not candidate.startswith(('http://', 'https://')) or '//' not in candidate:
            continue
        host = candidate.split('/', 3)[2].lower()
        if any(host == domain or host.endswith('.' + domain) for domain in ('t.me', 'telegram.me', 'telegram.dog')):
            continue
        links.add(candidate)
    return sorted(links)


def reference_link(chat_id, message_id):
    internal = str(chat_id)
    if internal.startswith('-100'):
        internal = internal[4:]
    elif internal.startswith('-'):
        internal = internal[1:]
    return f'https://t.me/c/{internal}/{message_id}'


def load_state(path):
    path = Path(path)
    if not path.exists():
        return dict(last_update_id=0, seen_message_ids=[])
    return json.loads(path.read_text(encoding='utf-8'))


def save_state(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix='.state-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def discover(token, *, fetch=default_fetch, limit=20):
    if not 1 <= limit <= 100:
        raise ValueError('Discovery limit out of range')
    updates = fetch(token, 'getUpdates', dict(timeout=0, allowed_updates=json.dumps(['channel_post'])))
    if not isinstance(updates, list):
        raise ValueError('Unexpected Telegram response')
    seen = {}
    for update in updates[:limit]:
        post = update.get('channel_post') if isinstance(update, dict) else None
        chat = post.get('chat') if isinstance(post, dict) else None
        if not isinstance(chat, dict) or not isinstance(chat.get('id'), int):
            continue
        seen[chat['id']] = dict(chat_id=chat['id'], title=chat.get('title'), username=chat.get('username'))
    return dict(schema='telegram-discover-1', channels=sorted(seen.values(), key=lambda c: c['chat_id']),
                note='Confirm the intended channel manually before locking expected_id; token not persisted')


def discover_checked(profile, token, *, fetch=default_fetch, limit=20):
    home(profile)  # Must precede any Telegram API call.
    return discover(token, fetch=fetch, limit=limit)


def poll(token, channel, state_path, output_dir, *, fetch=default_fetch, now=None):
    for key in ('key', 'expected_name', 'expected_id'):
        if key not in channel:
            raise ValueError('Channel mapping requires key/expected_name/expected_id')
    if type(channel['expected_id']) is not int:
        raise ValueError('Live polling requires a locked numeric expected_id; run discover first')
    locked_chat_id = channel['expected_id']
    state_path = Path(state_path)
    state = load_state(state_path)
    last_update_id = int(state.get('last_update_id', 0))
    params = dict(timeout=0, allowed_updates=json.dumps(['channel_post', 'edited_channel_post']))
    if last_update_id:
        params['offset'] = last_update_id + 1
    updates = fetch(token, 'getUpdates', params)
    if not isinstance(updates, list) or len(updates) > MAX_UPDATES:
        raise ValueError('Unexpected or oversized Telegram update batch')
    seen_ids = set(state.get('seen_message_ids', []))
    items = {}
    counts = dict(received=len(updates), accepted=0, rejected_wrong_chat=0, rejected_malformed=0, duplicate=0)
    max_update_id = last_update_id
    for update in updates:
        if not isinstance(update, dict) or not isinstance(update.get('update_id'), int):
            counts['rejected_malformed'] += 1
            continue
        max_update_id = max(max_update_id, update['update_id'])
        is_edit = 'edited_channel_post' in update
        post = update.get('edited_channel_post') if is_edit else update.get('channel_post')
        if not isinstance(post, dict):
            counts['rejected_malformed'] += 1
            continue
        chat = post.get('chat')
        if not isinstance(chat, dict) or chat.get('id') != locked_chat_id:
            counts['rejected_wrong_chat'] += 1
            continue
        try:
            message_id = int(post['message_id'])
            published = datetime.fromtimestamp(int(post['date']), timezone.utc)
        except (KeyError, TypeError, ValueError):
            counts['rejected_malformed'] += 1
            continue
        if channel['expected_name'] is not None and chat.get('title') != channel['expected_name']:
            raise ValueError('Channel title mismatch; preserve state and review before continuing')
        edited = None
        if post.get('edit_date'):
            try:
                edited = datetime.fromtimestamp(int(post['edit_date']), timezone.utc)
            except (TypeError, ValueError):
                counts['rejected_malformed'] += 1
                continue
        if message_id in items:
            counts['duplicate'] += 1
            continue
        if message_id in seen_ids and not is_edit:
            counts['duplicate'] += 1
            continue
        text = post.get('text') or post.get('caption') or ''
        entities = post.get('entities') or post.get('caption_entities') or []
        links = link_entities(text, entities)
        digest_payload = dict(text=text, entities=entities, edit_date=post.get('edit_date'),
                               has_photo=bool(post.get('photo')), has_document=bool(post.get('document')))
        digest = hashlib.sha256(json.dumps(digest_payload, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
        items[message_id] = dict(message_id=message_id, published_on=published.astimezone(KST).date().isoformat(),
                                  published_at_utc=published.isoformat(), is_edit=is_edit,
                                  edited_at_utc=edited.isoformat() if edited else None,
                                  reference=reference_link(locked_chat_id, message_id),
                                  external_urls=links, content_digest=digest)
        seen_ids.add(message_id)
        counts['accepted'] += 1
    ordered = [items[key] for key in sorted(items)]
    stamp_time = now or datetime.now(timezone.utc)
    receipt = dict(schema='telegram-live-metadata-1', channel_key=channel['key'], chat_id=locked_chat_id,
                   generated_at_utc=stamp_time.isoformat(), counts=counts, items=ordered,
                   completeness='unverified; Bot API retains undelivered updates up to 24h only',
                   privacy='home_local_only; no raw text, senders, attachments or credentials')
    output_dir = Path(output_dir)
    if ordered:
        output_dir.mkdir(parents=True, exist_ok=True)
        nonce = os.urandom(4).hex()
        out_path = output_dir / f"receipt-{stamp_time.strftime('%Y%m%dT%H%M%S%f')}Z-{nonce}.json"
        if out_path.exists():
            raise ValueError('Receipt filename collision; retry')
        with out_path.open('x', encoding='utf-8') as stream:
            json.dump(receipt, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    save_state(state_path, dict(last_update_id=max_update_id, seen_message_ids=sorted(seen_ids)[-5000:]))
    return receipt


def poll_file(root, profile, token, channel, state_name, output_dir_name, *, fetch=default_fetch, now=None):
    home(profile)  # Must precede any Telegram API call or local path use.
    state_path = local_file(root, state_name)
    output_dir = local_file(root, output_dir_name)
    return poll(token, channel, state_path, output_dir, fetch=fetch, now=now)
