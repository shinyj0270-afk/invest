"""Contract for `investment/sandbox.py`: an isolated copy of the app (code + the data it needs) so UI tests never write to the operating data
and never reach the network (the sandbox config enables no data adapter, so the app's start-up refresh cannot run)."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from investment import sandbox as sb
from tests.test_data_backup import make_project, sha


def add_code(root):
    (root / 'app.py').write_text('print("app")', encoding='utf-8')
    (root / 'investment').mkdir(exist_ok=True)
    (root / 'investment/core.py').write_text('X = 1', encoding='utf-8')
    (root / 'tests').mkdir(exist_ok=True)
    (root / 'tests/test_daily_ui.py').write_text('# ui', encoding='utf-8')
    (root / 'config/profile.example.json').write_text('{}', encoding='utf-8')
    return ['app.py', 'investment/core.py', 'tests/test_daily_ui.py', 'config/profile.example.json', 'config/local.json', 'data/work/user_input/research.sqlite3', 'missing.py']


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root = make_project(self.tmp.name)
        self.tracked = add_code(self.root)

    def prepare(self, **kw):
        return sb.prepare(self.root, tracked_files=self.tracked, **kw)

    def test_the_sandbox_has_the_code_the_needed_data_and_a_config_that_enables_no_adapter_and_no_network_paths(self):
        info = self.prepare();dest = Path(info['dest'])
        self.assertEqual(dest.parent, (self.root / '.local/sandbox').resolve());self.assertTrue((dest / 'SANDBOX.json').exists())
        for rel in ('app.py', 'investment/core.py', 'tests/test_daily_ui.py', 'config/profile.example.json'):
            self.assertEqual(sha(dest / rel), sha(self.root / rel))
        self.assertFalse((dest / 'missing.py').exists())
        for rel in ('data/work/user_input/research.sqlite3', 'data/work/user_input/external-reports.sqlite3', 'data/work/user_input/daily-latest.json',
                    'data/work/user_input/refresh-snapshots/old.json', 'private_data/infomax/snap.json'):
            self.assertEqual(sha(dest / rel), sha(self.root / rel), rel)
        config = json.loads((dest / 'config/local.json').read_text(encoding='utf-8'))
        self.assertEqual((config['profile'], Path(config['project_root']).resolve(), config['data_dir']), ('work', dest.resolve(), 'data'))
        self.assertEqual(config['enabled_data_adapters'], []);self.assertIs(config['scheduled_jobs_enabled'], False)
        for key in ('infomax_refresh', 'market_events', 'goose_report_inbox', 'research_drop_inbox', 'shared_dashboard'):
            self.assertNotIn(key, config)
        self.assertEqual(config['manual_snapshot_file'], 'private_data/infomax/snap.json')

    def test_the_real_local_config_the_operating_data_outside_the_needed_folders_and_the_local_folder_are_never_copied(self):
        (self.root / 'data/work/company-financials').mkdir(parents=True);(self.root / 'data/work/company-financials/000020.json').write_text('{}', encoding='utf-8')
        (self.root / 'private_data/secret.txt').write_text('key', encoding='utf-8');(self.root / '.local/x').mkdir(parents=True)
        info = self.prepare();dest = Path(info['dest'])
        self.assertFalse((dest / 'data/work/company-financials').exists());self.assertFalse((dest / 'private_data/secret.txt').exists());self.assertFalse((dest / '.local/x').exists())
        original = json.loads((self.root / 'config/local.json').read_text(encoding='utf-8'))
        self.assertEqual(original['project_root'], str(self.root))                                  # the source config is untouched

    def test_changing_the_sandbox_never_changes_the_source_and_check_source_sees_real_changes(self):
        info = self.prepare();dest = Path(info['dest'])
        (dest / 'data/work/user_input/daily-latest.json').write_text('{"changed": true}', encoding='utf-8')
        self.assertEqual(sb.check_source(dest), dict(unchanged=True, changed=[], missing=[], added=[]))
        source_file = self.root / 'data/work/user_input/daily-latest.json';source_file.write_text('{"a": 2}', encoding='utf-8')
        (self.root / 'data/work/user_input/new.json').write_text('{}', encoding='utf-8');(self.root / 'private_data/infomax/snap.json').unlink()
        report = sb.check_source(dest)
        self.assertFalse(report['unchanged']);self.assertEqual(report['changed'], ['data/work/user_input/daily-latest.json'])
        self.assertEqual(report['added'], ['data/work/user_input/new.json']);self.assertEqual(report['missing'], ['private_data/infomax/snap.json'])

    def test_the_marker_records_source_hashes_of_exactly_the_copied_data_files(self):
        info = self.prepare();marker = json.loads((Path(info['dest']) / 'SANDBOX.json').read_text(encoding='utf-8'))
        self.assertEqual(marker['tool'], 'sandbox');self.assertEqual(Path(marker['source_root']).resolve(), self.root.resolve())
        self.assertEqual(sorted(marker['source_hashes']), sorted(['data/work/user_input/research.sqlite3', 'data/work/user_input/external-reports.sqlite3',
                                                                    'data/work/user_input/daily-latest.json', 'data/work/user_input/refresh-snapshots/old.json',
                                                                    'private_data/infomax/snap.json']))
        for rel, digest in marker['source_hashes'].items():
            self.assertEqual(digest, hashlib.sha256((self.root / rel).read_bytes()).hexdigest())

    def test_destinations_outside_the_sandbox_folder_or_already_existing_are_refused(self):
        for dest in (self.root, self.root / 'data', self.root / '.local', Path(self.tmp.name) / 'elsewhere', self.root / '.local/sandbox/../../data/x'):
            with self.subTest(dest=str(dest)), self.assertRaises(ValueError):
                sb.prepare(self.root, dest=dest, tracked_files=self.tracked)
        ok = self.root / '.local/sandbox/mine';self.assertEqual(Path(sb.prepare(self.root, dest=ok, tracked_files=self.tracked)['dest']), ok.resolve())
        with self.assertRaises(ValueError):
            sb.prepare(self.root, dest=ok, tracked_files=self.tracked)

    def test_tracked_file_lists_cannot_escape_the_root_or_name_data_folders(self):
        outside = Path(self.tmp.name) / 'outside.txt';outside.write_text('x', encoding='utf-8')
        info = sb.prepare(self.root, tracked_files=['app.py', '../outside.txt', str(outside), 'data/work/user_input/daily-latest.json', '.local/x', 'private_data/infomax/snap.json'])
        dest = Path(info['dest']);self.assertTrue((dest / 'app.py').exists());self.assertFalse((dest.parent / 'outside.txt').exists());self.assertFalse((dest / 'outside.txt').exists())
        for bad in ('x', 5, [1], [None], 'app.py'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                sb.prepare(self.root, tracked_files=bad)

    def test_remove_deletes_only_a_marked_sandbox_inside_the_sandbox_folder(self):
        info = self.prepare();dest = Path(info['dest']);sb.remove(dest);self.assertFalse(dest.exists());self.assertTrue((self.root / 'data/work/user_input/research.sqlite3').exists())
        for target in (self.root, self.root / 'data', self.root / '.local/sandbox', Path(self.tmp.name) / 'nothing'):
            with self.subTest(target=str(target)), self.assertRaises(ValueError):
                sb.remove(target)
        unmarked = self.root / '.local/sandbox/plain';unmarked.mkdir(parents=True);(unmarked / 'f.txt').write_text('x', encoding='utf-8')
        with self.assertRaises(ValueError):
            sb.remove(unmarked)
        self.assertTrue((unmarked / 'f.txt').exists())

    def test_an_unknown_profile_or_missing_config_is_refused(self):
        bare = Path(self.tmp.name) / 'bare';bare.mkdir()
        with self.assertRaises(ValueError):
            sb.prepare(bare, tracked_files=[])


class SurvivorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root = make_project(self.tmp.name);self.tracked = add_code(self.root)

    def test_tracked_files_under_data_private_data_and_local_are_never_copied_even_if_listed(self):
        names = ('data/work/market-expansion/a.json', 'private_data/secret.txt', '.local/note.txt')
        for rel in names:
            p = self.root / rel;p.parent.mkdir(parents=True, exist_ok=True);p.write_text('x', encoding='utf-8')
        dest = Path(sb.prepare(self.root, tracked_files=self.tracked + list(names))['dest'])
        for rel in names:
            self.assertFalse((dest / rel).exists(), rel)

    def test_a_missing_manual_snapshot_is_not_named_in_the_sandbox_config(self):
        (self.root / 'private_data/infomax/snap.json').unlink()
        dest = Path(sb.prepare(self.root, tracked_files=self.tracked)['dest'])
        self.assertNotIn('manual_snapshot_file', json.loads((dest / 'config/local.json').read_text(encoding='utf-8')))

    def test_a_marker_copied_elsewhere_cannot_delete_that_folder_and_a_foreign_marker_is_refused(self):
        import shutil
        dest = Path(sb.prepare(self.root, tracked_files=self.tracked)['dest'])
        elsewhere = self.root / 'precious';elsewhere.mkdir();(elsewhere / 'keep.txt').write_text('x', encoding='utf-8');shutil.copyfile(dest / 'SANDBOX.json', elsewhere / 'SANDBOX.json')
        with self.assertRaises(ValueError):
            sb.remove(elsewhere)
        self.assertTrue((elsewhere / 'keep.txt').exists())
        marker = json.loads((dest / 'SANDBOX.json').read_text(encoding='utf-8'));marker['tool'] = 'other'
        (dest / 'SANDBOX.json').write_text(json.dumps(marker), encoding='utf-8')
        for call in (sb.check_source, sb.remove):
            with self.subTest(call=call.__name__), self.assertRaises(ValueError):
                call(dest)

    def test_a_failure_while_copying_removes_the_half_built_sandbox(self):
        from unittest.mock import patch
        with patch('investment.sandbox.shutil.copyfile', side_effect=OSError('disk full')), self.assertRaises(OSError):
            sb.prepare(self.root, tracked_files=self.tracked)
        folder = self.root / '.local/sandbox'
        self.assertEqual(list(folder.iterdir()) if folder.exists() else [], [])


if __name__ == '__main__':
    unittest.main()
