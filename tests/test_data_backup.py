"""Contract for `investment/data_backup.py`: consistent, verifiable local backups of the operating data (never touches Git, never leaves the machine)."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from investment import data_backup as db

KST = timezone(timedelta(hours=9))


def make_project(tmp, profile='work'):
    root = Path(tmp) / 'proj'
    (root / 'config').mkdir(parents=True)
    (root / 'config/local.json').write_text(json.dumps(dict(profile=profile, project_root=str(root), data_dir='data', manual_snapshot_file='private_data/infomax/snap.json',
                                                           enabled_data_adapters=['infomax_manual'])), encoding='utf-8')
    user = root / 'data' / profile / 'user_input'
    user.mkdir(parents=True)
    for name, rows in (('research.sqlite3', 3), ('external-reports.sqlite3', 2)):
        con = sqlite3.connect(user / name);con.execute('create table t(a)');con.executemany('insert into t values (?)', [(i,) for i in range(rows)]);con.commit();con.close()
    (user / 'daily-latest.json').write_text('{"a": 1}', encoding='utf-8')
    (user / 'refresh-snapshots').mkdir()
    (user / 'refresh-snapshots' / 'old.json').write_text('{"big": true}', encoding='utf-8')
    (root / 'private_data/infomax').mkdir(parents=True)
    (root / 'private_data/infomax/snap.json').write_text('{"s": 1}', encoding='utf-8')
    return root


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root = make_project(self.tmp.name)
        self.now = datetime(2026, 11, 4, 9, 0, 0, tzinfo=KST)

    def test_a_backup_holds_every_database_the_top_level_state_files_and_the_manual_snapshot_but_not_the_snapshot_archive(self):
        result = db.backup(self.root, now=self.now)
        folder = Path(result['path'])
        self.assertEqual(folder.parent, self.root / '.local/backups');self.assertEqual(folder.name, '20261104-090000')
        rels = sorted(f['rel'] for f in result['files'])
        self.assertEqual(rels, ['data/work/user_input/daily-latest.json', 'data/work/user_input/external-reports.sqlite3', 'data/work/user_input/research.sqlite3',
                                'private_data/infomax/snap.json'])
        for f in result['files']:
            self.assertEqual(sha(folder / f['rel']), f['sha256']);self.assertEqual((folder / f['rel']).stat().st_size, f['size'])
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual((manifest['tool'], manifest['created_at']), ('data_backup', self.now.isoformat()));self.assertEqual(manifest['files'], result['files'])

    def test_the_sources_are_not_modified_and_the_copies_are_valid_databases(self):
        user = self.root / 'data/work/user_input'
        before = {p.name: sha(p) for p in user.iterdir() if p.is_file()}
        result = db.backup(self.root, now=self.now)
        self.assertEqual({p.name: sha(p) for p in user.iterdir() if p.is_file()}, before)
        con = sqlite3.connect(Path(result['path']) / 'data/work/user_input/research.sqlite3')
        try:self.assertEqual(con.execute('select count(*) from t').fetchone()[0], 3);self.assertEqual(con.execute('pragma integrity_check').fetchone()[0], 'ok')
        finally:con.close()

    def test_a_write_ahead_log_database_is_backed_up_consistently(self):
        path = self.root / 'data/work/user_input/research.sqlite3'
        con = sqlite3.connect(path);con.execute('pragma journal_mode=wal');con.execute('insert into t values (99)');con.commit()   # row lives in the WAL until a checkpoint
        try:
            result = db.backup(self.root, now=self.now)
            copy = sqlite3.connect(Path(result['path']) / 'data/work/user_input/research.sqlite3')
            try:self.assertEqual(copy.execute('select count(*) from t').fetchone()[0], 4)
            finally:copy.close()
        finally:con.close()

    def test_two_backups_in_the_same_second_get_distinct_folders(self):
        first = db.backup(self.root, now=self.now);second = db.backup(self.root, now=self.now)
        self.assertNotEqual(first['path'], second['path']);self.assertEqual(len(db.list_backups(self.root)), 2)

    def test_retention_in_one_second_never_removes_the_backup_just_made(self):
        # keep=2 in one second: the 4th run used to reuse the freed base name and then delete itself.
        for _ in range(4):latest = db.backup(self.root, now=self.now, keep=2)
        self.assertTrue(Path(latest['path']).is_dir())
        names = db.list_backups(self.root)
        self.assertEqual(len(names), 2);self.assertEqual(names[0], Path(latest['path']).name)

    def test_backups_in_one_second_are_ordered_by_creation_not_by_text(self):
        made = [Path(db.backup(self.root, now=self.now, keep=3)['path']).name for _ in range(11)]
        self.assertEqual(db.list_backups(self.root), made[::-1][:3])                              # '-11','-10','-9', not '-9','-8','-7'

    def test_the_newest_backups_are_kept_and_only_tool_made_folders_are_ever_removed(self):
        stranger = self.root / '.local/backups/handmade';stranger.mkdir(parents=True);(stranger / 'note.txt').write_text('mine', encoding='utf-8')
        for i in range(5):db.backup(self.root, now=self.now + timedelta(minutes=i), keep=3)
        names = db.list_backups(self.root)
        self.assertEqual(names, ['20261104-090400', '20261104-090300', '20261104-090200'])      # newest first
        self.assertTrue((stranger / 'note.txt').exists())
        for bad in (0, -1, True, 1.5, None):
            with self.subTest(keep=bad), self.assertRaises(ValueError):
                db.backup(self.root, now=self.now, keep=bad)

    def test_verify_confirms_an_intact_backup_and_names_every_kind_of_damage(self):
        result = db.backup(self.root, now=self.now);folder = Path(result['path'])
        self.assertEqual(db.verify_backup(folder), dict(ok=True, checked=4, problems=[]))
        (folder / 'data/work/user_input/daily-latest.json').write_text('{"a": 2}', encoding='utf-8')
        (folder / 'private_data/infomax/snap.json').unlink()
        broken = folder / 'data/work/user_input/external-reports.sqlite3'
        data = bytearray(broken.read_bytes());data[len(data) // 2:len(data) // 2 + 64] = b'\xff' * 64;broken.write_bytes(bytes(data))
        report = db.verify_backup(folder)
        self.assertFalse(report['ok']);text = ' '.join(report['problems'])
        self.assertIn('daily-latest.json', text);self.assertIn('snap.json', text);self.assertIn('external-reports.sqlite3', text)
        self.assertFalse(db.verify_backup(self.root / 'nowhere')['ok'])
        (folder / 'manifest.json').write_text('not json', encoding='utf-8');self.assertFalse(db.verify_backup(folder)['ok'])

    def test_a_failed_backup_leaves_no_partial_folder_and_removes_nothing(self):
        good = db.backup(self.root, now=self.now)
        (self.root / 'data/work/user_input/research.sqlite3').write_bytes(b'this is not a database' * 100)
        with self.assertRaises(Exception):
            db.backup(self.root, now=self.now + timedelta(minutes=1), keep=1)
        self.assertEqual(db.list_backups(self.root), [Path(good['path']).name])                    # the good one survives even with keep=1
        self.assertEqual([p.name for p in (self.root / '.local/backups').iterdir()], [Path(good['path']).name])

    def test_a_missing_manual_snapshot_or_missing_data_is_reported_not_invented(self):
        (self.root / 'private_data/infomax/snap.json').unlink()
        result = db.backup(self.root, now=self.now)
        self.assertNotIn('private_data/infomax/snap.json', [f['rel'] for f in result['files']])
        empty = Path(self.tmp.name) / 'empty';(empty / 'config').mkdir(parents=True)
        (empty / 'config/local.json').write_text(json.dumps(dict(profile='work', project_root=str(empty), data_dir='data')), encoding='utf-8')
        with self.assertRaises(ValueError):
            db.backup(empty, now=self.now)                                                       # nothing to back up is an error, not an empty "success"

    def test_a_naive_time_is_refused(self):
        with self.assertRaises(ValueError):
            db.backup(self.root, now=datetime(2026, 11, 4, 9, 0, 0))


class SurvivorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root = make_project(self.tmp.name)
        self.now = datetime(2026, 11, 4, 9, 0, 0, tzinfo=KST)

    def test_a_manifest_with_no_files_is_not_a_verified_backup(self):
        folder = Path(self.tmp.name) / 'empty-backup';folder.mkdir()
        (folder / 'manifest.json').write_text(json.dumps(dict(tool='data_backup', version=1, files=[])), encoding='utf-8')
        report = db.verify_backup(folder)
        self.assertFalse(report['ok']);self.assertEqual(report['checked'], 0);self.assertTrue(report['problems'])
        from tools.backup_data import main
        from contextlib import redirect_stdout
        import io
        with redirect_stdout(io.StringIO()):self.assertNotEqual(main(['verify', str(folder)]), 0)

    def test_a_folder_with_a_foreign_manifest_is_neither_listed_nor_ever_removed(self):
        foreign = self.root / '.local/backups/20990101-000000';foreign.mkdir(parents=True)
        (foreign / 'manifest.json').write_text(json.dumps(dict(tool='other', files=[])), encoding='utf-8')
        for i in range(3):db.backup(self.root, now=self.now + timedelta(minutes=i), keep=1)
        self.assertEqual(db.list_backups(self.root), ['20261104-090200']);self.assertTrue(foreign.exists())

    def test_a_copy_that_fails_the_integrity_check_makes_the_backup_fail_cleanly(self):
        from unittest.mock import patch
        with patch.object(db, '_integrity', side_effect=ValueError('bad')), self.assertRaises(ValueError):
            db.backup(self.root, now=self.now)
        self.assertEqual(list((self.root / '.local/backups').iterdir()), [])

    def test_verify_reports_size_changes_a_database_failing_integrity_despite_matching_hashes_and_malformed_manifests(self):
        folder = Path(db.backup(self.root, now=self.now)['path'])
        target = folder / 'data/work/user_input/daily-latest.json';target.write_text('{"a": 1, "b": 2222}', encoding='utf-8')
        self.assertTrue(any('daily-latest.json' in p and '크기' in p for p in db.verify_backup(folder)['problems']))
        folder2 = Path(db.backup(self.root, now=self.now + timedelta(minutes=1))['path'])
        broken = folder2 / 'data/work/user_input/research.sqlite3';broken.write_bytes(b'not a database at all' * 50)
        manifest = json.loads((folder2 / 'manifest.json').read_text(encoding='utf-8'))
        for entry in manifest['files']:
            if entry['rel'].endswith('research.sqlite3'):entry.update(sha256=sha(broken), size=broken.stat().st_size)
        (folder2 / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        report = db.verify_backup(folder2);self.assertFalse(report['ok']);self.assertTrue(any('research.sqlite3' in p for p in report['problems']))
        folder3 = Path(db.backup(self.root, now=self.now + timedelta(minutes=2))['path'])
        (folder3 / 'manifest.json').write_text(json.dumps(dict(tool='data_backup')), encoding='utf-8');self.assertFalse(db.verify_backup(folder3)['ok'])
        (folder3 / 'manifest.json').write_text(json.dumps(dict(tool='other', files=[])), encoding='utf-8');self.assertFalse(db.verify_backup(folder3)['ok'])


if __name__ == '__main__':
    unittest.main()
