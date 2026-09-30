from contextlib import closing
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from investment.workspace_events import load_cached_events


class WorkspaceEventTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.snapshot = {'meta': {'data_mode': 'user_input', 'price_date': '2026-09-25'},
                         'companies': [{'code': '005930'}]}
        self.path = self.root / 'data/unknown/user_input/research.sqlite3'

    def database(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE market_event_versions(version TEXT PRIMARY KEY,'
                       'event_id TEXT,code TEXT,seen TEXT,payload TEXT,reviewed INTEGER)')

    def add(self, version, *, observed='2026-09-24T10:00:00+09:00', event='event', **changes):
        item = dict(id=event, code='005930', kind='disclosure', title='실적 발표',
                    source='OpenDART', url='https://dart.fss.or.kr/example',
                    published_on='2026-09-23', private_note='SECRET', reviewed=True)
        item.update(changes)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT INTO market_event_versions VALUES(?,?,?,?,?,1)',
                       (version, event, item['code'], observed, json.dumps(item)))

    def test_public_latest_version_without_writes(self):
        self.database()
        self.add('one')
        self.add('two', observed='2026-09-25T09:00:00+09:00', title='정정 실적 발표')
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        files = set(self.path.parent.iterdir())
        real_connect = sqlite3.connect
        with patch('investment.workspace_events.sqlite3.connect', wraps=real_connect) as connect:
            result = load_cached_events(self.root, self.snapshot)
        self.assertIn('?mode=ro', connect.call_args.args[0])
        self.assertTrue(connect.call_args.kwargs['uri'])
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)
        self.assertEqual(set(self.path.parent.iterdir()), files)
        self.assertEqual(len(result['005930']), 1)
        item = result['005930'][0]
        self.assertEqual(item['title'], '정정 실적 발표')
        self.assertEqual(set(item), {'kind', 'title', 'source', 'url', 'published_on', 'first_seen_at'})
        self.assertNotIn('SECRET', json.dumps(result))

    def test_future_unrelated_and_invalid_records_excluded(self):
        self.database()
        self.add('old')
        self.add('future-version', observed='2026-09-26T01:00:00+09:00', title='future')
        self.add('future-publication', event='future', published_on='2026-09-26')
        self.add('other', event='other', code='000660')
        self.add('unsafe', event='unsafe', url='javascript:alert(1)')
        self.add('naive', event='naive', observed='2026-09-25T10:00:00')
        self.add('timezone', event='timezone', observed='2026-09-25T17:00:00+00:00')
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('INSERT INTO market_event_versions VALUES(?,?,?,?,?,0)',
                       ('broken', 'broken', '005930', '2026-09-24T10:00:00+09:00', '{'))
        result = load_cached_events(self.root, self.snapshot)
        self.assertEqual(list(result), ['005930'])
        self.assertEqual([item['title'] for item in result['005930']], ['실적 발표'])

    def test_missing_corrupt_and_missing_table_return_empty(self):
        self.assertEqual(load_cached_events(self.root, self.snapshot), {})
        self.assertFalse(self.path.parent.exists())
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b'not sqlite')
        self.assertEqual(load_cached_events(self.root, self.snapshot), {})
        self.path.unlink()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE unrelated(value TEXT)')
        self.assertEqual(load_cached_events(self.root, self.snapshot), {})

    def test_modes_never_share_cache(self):
        self.database()
        self.add('actual')
        self.snapshot['meta']['data_mode'] = 'fixture'
        self.assertEqual(load_cached_events(self.root, self.snapshot), {})
        self.assertFalse((self.root / 'data/unknown/fixture').exists())
        self.snapshot['meta']['data_mode'] = '../user_input'
        self.assertEqual(load_cached_events(self.root, self.snapshot), {})


if __name__ == '__main__':
    unittest.main()
