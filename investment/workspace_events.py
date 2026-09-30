"""Read public event metadata from the current snapshot's existing local cache."""
import json
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

from .local_config import load_local
from .market_events import KST, safe_url


def load_cached_events(root, snapshot):
    """Never create a database, fetch sources, or expose local review information."""
    try:
        config = load_local(root)
        mode = snapshot['meta']['data_mode']
        if mode not in ('fixture', 'user_input', 'live'):
            return {}
        as_of = date.fromisoformat(snapshot['meta']['price_date'])
        codes = {row['code'] for row in snapshot['companies']}
        path = Path(config['data_dir']) / config['profile'] / mode / 'research.sqlite3'
        if not path.is_file():
            return {}
        selected = {}
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True,
                                     timeout=1)) as db:
            for code in sorted(codes):
                records = db.execute('SELECT rowid,event_id,seen,payload FROM '
                                     'market_event_versions WHERE code=?', (code,))
                for rowid, event_id, observed, payload in records:
                    try:
                        stamp = datetime.fromisoformat(observed)
                        if stamp.tzinfo is None or stamp.astimezone(KST).date() > as_of:
                            continue
                        item = json.loads(payload)
                        published = date.fromisoformat(item['published_on'])
                        if (published > as_of or item.get('code') != code or
                                item.get('id') != event_id or
                                item.get('kind') not in ('news', 'disclosure')):
                            continue
                        title, source = item['title'], item['source']
                        if any(not isinstance(value, str) or not value.strip() or
                               len(value) > cap for value, cap in ((title, 1000), (source, 200))):
                            continue
                        public = dict(kind=item['kind'], title=title.strip(), source=source.strip(),
                                      url=safe_url(item['url']), published_on=published.isoformat(),
                                      first_seen_at=stamp.astimezone(KST).isoformat())
                        key, version = (code, event_id), (stamp, rowid)
                        if key not in selected or version > selected[key][0]:
                            selected[key] = (version, public)
                    except (ValueError, TypeError, KeyError, AttributeError):
                        continue
        result = {}
        for (code, _), (_, item) in selected.items():
            result.setdefault(code, []).append(item)
        for items in result.values():
            items.sort(key=lambda item: (item['published_on'], item['first_seen_at']), reverse=True)
        return result
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
        return {}
