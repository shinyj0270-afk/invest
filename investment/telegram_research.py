"""Home-only manual research register. No Telegram client/API/export importer."""
from .core import digest
from .research_library import fields, text, day, url

TERMS = 'https://telegram.org/tos/content-licensing'


def channels(library, value, expected_revision=0):
    library._home()
    fields(value, ('core', 'auxiliary'))
    if not isinstance(value['core'], list) or len(value['core']) not in (2, 3) or not isinstance(value['auxiliary'], list):
        raise ValueError('Two or three core channel slots required')
    seen = set()
    for channel in value['core'] + value['auxiliary']:
        fields(channel, ('id', 'name', 'enabled', 'permission'))
        text(channel['id'], 100); text(channel['name'], 200)
        if channel['id'] in seen or not isinstance(channel['enabled'], bool): raise ValueError('Channel identity/enabled invalid')
        seen.add(channel['id'])
        if channel['enabled']: permission(channel['permission'])
        elif channel['permission'] is not None: permission(channel['permission'])
    return library._put('channel', 'registry', value, expected_revision)


def permission(value):
    fields(value, ('method', 'terms_url', 'terms_checked_on', 'platform_basis', 'channel_basis', 'reviewer', 'local_analysis_allowed'))
    if value['method'] != 'manual_reference' or value['terms_url'] != TERMS or value['local_analysis_allowed'] is not True:
        raise ValueError('Reviewed manual reference permission required')
    day(value['terms_checked_on'])
    for k in ('platform_basis', 'channel_basis', 'reviewer'): text(value[k])
    return value


def batch(library, channel_id, value):
    # Gate before reading registry or records. Caller must gate before opening files.
    library._home()
    registry = library.get('channel', 'registry')
    channel = next((c for c in registry['core']+registry['auxiliary'] if c['id'] == channel_id), None)
    if not channel or not channel['enabled']: raise ValueError('Channel not enabled')
    permission(channel['permission'])
    fields(value, ('start', 'end', 'checked_on', 'entries', 'missing', 'coverage_basis'))
    for k in ('start', 'end', 'checked_on'): day(value[k])
    if not value['start'] <= value['end'] <= value['checked_on']: raise ValueError('Collection window invalid')
    if channel['permission']['terms_checked_on'] > value['checked_on']: raise ValueError('Permission check predates processing incorrectly')
    if value['missing'] not in ('unknown', 'known_gaps', 'none_observed'): raise ValueError('Missingness required')
    text(value['coverage_basis'])
    if not isinstance(value['entries'], list) or len(value['entries']) > 1000: raise ValueError('Bounded entries required')
    # Validate the whole batch before writes. Keep only reference metadata, no text body.
    prepared = {}
    duplicates = 0
    for entry in value['entries']:
        fields(entry, ('message_id', 'published_on', 'reference'))
        if not isinstance(entry['message_id'], int) or isinstance(entry['message_id'], bool) or entry['message_id'] < 1: raise ValueError('Positive message ID required')
        day(entry['published_on']); url(entry['reference'])
        if not value['start'] <= entry['published_on'] <= value['end']: raise ValueError('Entry outside requested window')
        key = digest([channel_id, entry['message_id']])
        if key in prepared:
            if prepared[key] != entry: raise ValueError('Conflicting duplicate in batch')
            duplicates += 1
        prepared[key] = entry
    inserted = 0
    with library.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for key, entry in prepared.items():
            rows = db.execute("SELECT payload FROM records WHERE kind='telegram' AND id=?", (key,)).fetchall()
            if rows:
                import json
                if json.loads(rows[-1][0]) != entry: raise ValueError('Existing message changed; explicit review needed')
                duplicates += 1
            else:
                import json
                from datetime import datetime, timezone
                db.execute('INSERT INTO records VALUES(?,?,?,?,?)', ('telegram', key, 1, datetime.now(timezone.utc).isoformat(), json.dumps(entry)))
                inserted += 1
        report = dict(channel_id=channel_id, start=value['start'], end=value['end'], checked_on=value['checked_on'],
                      inserted=inserted, duplicates=duplicates, missing=value['missing'],
                      coverage_basis=value['coverage_basis'], completeness='unverified', permission=channel['permission'])
        import json
        from datetime import datetime, timezone
        key = digest(report)
        if not db.execute("SELECT 1 FROM records WHERE kind='coverage' AND id=?", (key,)).fetchone():
            db.execute('INSERT INTO records VALUES(?,?,?,?,?)', ('coverage', key, 1, datetime.now(timezone.utc).isoformat(), json.dumps(report)))
    # ID gaps do not prove missing messages; deleted/inaccessible/service messages exist.
    return dict(report_id=key, **report)
