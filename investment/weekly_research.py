"""Atomic, offline weekly imports. No retrieval, model calls or review promotion."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import date
import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path

from .core import digest
from .research_library import Library, day, fields
from .research_catalog import search


class _ValidationLibrary(Library):
    @contextmanager
    def connect(self):
        with self.database:
            yield self.database


def read_bundle(markdown, manifest, archive=None):
    raw = Path(markdown).read_bytes()
    if len(raw) > 2_000_000:
        raise ValueError('Weekly Markdown exceeds 2 MB')
    raw.decode('utf-8-sig')
    value = json.loads(Path(manifest).read_text(encoding='utf-8-sig'))
    fields(value, ('research_date', 'markdown_sha256', 'records'))
    day(value['research_date'])
    if date.fromisoformat(value['research_date']).weekday() != 0:
        raise ValueError('Weekly research_date must be Monday')
    if hashlib.sha256(raw).hexdigest() != value['markdown_sha256']:
        raise ValueError('Markdown/manifest digest mismatch')
    if archive:
        with zipfile.ZipFile(archive) as zipped:
            entries = zipped.infolist()
            if len(entries) != 1 or entries[0].is_dir() or entries[0].file_size > 2_000_000:
                raise ValueError('ZIP must contain exactly one bounded Markdown file')
            if not entries[0].filename.lower().endswith('.md') or zipped.read(entries[0]) != raw:
                raise ValueError('ZIP Markdown differs from supplied original')
    return value


def import_week(library, bundle, *, apply=False):
    """Validate on a DB snapshot under one write lock; append all rows or none.

    Exact URL duplicates reuse existing IDs. Conflicts never update revisions.
    Date+digest identities survive renaming files. Links use explicit references
    and exact person/strategy/sector/topic metadata; similarity is not evidence.
    """
    fields(bundle, ('research_date', 'markdown_sha256', 'records'))
    observed = day(bundle['research_date'])
    if date.fromisoformat(observed).weekday() != 0:
        raise ValueError('Weekly research_date must be Monday')
    checksum = bundle['markdown_sha256']
    if not isinstance(checksum, str) or len(checksum) != 64 or any(c not in '0123456789abcdef' for c in checksum):
        raise ValueError('Lowercase SHA256 required')
    records = deepcopy(bundle['records'])
    if not isinstance(records, list) or not records or len(records) > 500:
        raise ValueError('Nonempty bounded records list required')
    seen = set()
    for record in records:
        fields(record, ('kind', 'id', 'value'))
        if record['kind'] not in ('source', 'master', 'thesis', 'evidence'):
            raise ValueError('Unsupported weekly record kind')
        key = (record['kind'], record['id'])
        if key in seen:
            raise ValueError('Repeated record ID in bundle')
        seen.add(key)
        if not isinstance(record['value'], dict):
            raise ValueError('Record value must be an object')
        value = record['value']
        for field in ('accessed_on', 'as_of', 'observed_on'):
            if field in value and value[field] > observed:
                raise ValueError('Record observation exceeds weekly date')
    batch_id = digest(['weekly', observed, checksum])
    with library.connect() as target:
        target.execute('BEGIN IMMEDIATE')
        baseline = target.execute('SELECT kind,id,revision,created,payload FROM records').fetchall()
        memory = sqlite3.connect(':memory:')
        try:
            memory.execute('CREATE TABLE records(kind TEXT,id TEXT,revision INTEGER,created TEXT,payload TEXT,PRIMARY KEY(kind,id,revision))')
            memory.executemany('INSERT INTO records VALUES(?,?,?,?,?)', baseline)
            memory.commit()
            validator = _ValidationLibrary.__new__(_ValidationLibrary)
            validator.database, validator.profile, validator.mode = memory, library.profile, library.mode
            previous = validator.history('weekly', batch_id)
            signature = digest(records)
            if previous:
                if previous[-1]['value']['input_digest'] != signature:
                    raise ValueError('Same original has conflicting derived records')
            aliases = {}
            inserted = skipped = 0
            for kind in ('source', 'master', 'thesis', 'evidence'):
                for record in (r for r in records if r['kind'] == kind):
                    key, value = record['id'], record['value']
                    if kind == 'source':
                        matches = [(sid, json.loads(payload)) for sid, payload in memory.execute("SELECT id,payload FROM records WHERE kind='source'") if json.loads(payload)['url'] == value.get('url')]
                        if matches:
                            sid, stored = matches[0]
                            validator.get('source', sid)
                            if any(stored_value != value for _, stored_value in matches):
                                raise ValueError('Existing URL has conflicting source metadata')
                            history = validator.history(kind, key)
                            if history and history[-1]['value'] != value:
                                raise ValueError('Source ID conflict')
                            aliases[key] = sid
                            skipped += 1
                            continue
                    for field in ('source_ids', 'seed_source_ids'):
                        if field in value:
                            value[field] = list(dict.fromkeys(aliases.get(s, s) for s in value[field]))
                    history = validator.history(kind, key)
                    if history:
                        validator.get(kind, key)
                        if history[-1]['value'] != value:
                            raise ValueError('Existing ID differs; preserve and review: '+key)
                        skipped += 1
                    else:
                        getattr(validator, kind)(key, value)
                        inserted += 1
            visible = search(validator)
            links = []
            for record in records:
                value = record['value']
                persons = {value['master']} if record['kind'] == 'master' else set()
                strategies = set(value.get('strategies', []))
                explicit = [('source', s) for s in value.get('source_ids', value.get('seed_source_ids', []))]
                explicit += [('master', m) for m in value.get('master_ids', [])]
                if 'thesis_id' in value:
                    explicit.append(('thesis', value['thesis_id']))
                for candidate in visible:
                    dest = (candidate['kind'], candidate['id'])
                    if dest == (record['kind'], aliases.get(record['id'], record['id'])):
                        continue
                    other, meta = candidate['value'], candidate['metadata']
                    reasons = []
                    if dest in explicit:
                        reasons.append('explicit_reference')
                    if persons & (set(meta.get('persons', [])) | ({other['master']} if 'master' in other else set())):
                        reasons.append('same_person')
                    if strategies & set(other.get('strategies', [])):
                        reasons.append('same_strategy')
                    for field, metadata_field in (('sector', 'sector'), ('theme', 'topic')):
                        label = value.get(field)
                        if label and label not in ('미확인', '산업공통') and label in (other.get(field), meta.get(metadata_field)):
                            reasons.append('same_'+metadata_field)
                    if reasons:
                        links.append(dict(origin=[record['kind'], aliases.get(record['id'], record['id'])], target=list(dest), reasons=reasons))
            if previous:
                if inserted:
                    raise ValueError('Previously imported bundle is missing records; preserve and review')
                return dict(inserted=0, skipped=skipped, duplicate=True, applied=apply, links=links)
            receipt = dict(research_date=observed, markdown_sha256=checksum, input_digest=signature,
                           inserted=inserted, skipped=skipped, links=links, source_aliases=aliases,
                           interpretation='derived_unverified')
            validator._put('weekly', batch_id, receipt)
            old = {(r[0], r[1], r[2]) for r in baseline}
            added = [r for r in memory.execute('SELECT kind,id,revision,created,payload FROM records') if (r[0], r[1], r[2]) not in old]
            if apply:
                target.executemany('INSERT INTO records VALUES(?,?,?,?,?)', added)
            return dict(inserted=inserted, skipped=skipped, duplicate=False, applied=apply, links=links)
        finally:
            memory.close()
