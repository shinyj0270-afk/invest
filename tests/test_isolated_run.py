"""Contract for `investment/isolated_run.py`: run UI test files against a sandbox copy of the app, with a backup first and a proof afterwards
that the operating data did not change. Server start and test execution are injected; tests use fakes."""
import tempfile
import unittest
from pathlib import Path
from investment import isolated_run as ir
from tests.test_data_backup import make_project
from tests.test_sandbox import add_code


class FakeServer:
    def __init__(self, events):
        self.events, self.url = events, 'http://127.0.0.1:9999'
    def stop(self):
        self.events.append('stop')


class RunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root = make_project(self.tmp.name)
        self.tracked = add_code(self.root);(self.root / 'tests/test_viewer_ui.py').write_text('# ui', encoding='utf-8');self.tracked.append('tests/test_viewer_ui.py')
        self.events = []

    def run_it(self, *, codes=None, mutate=None, backup_fail=False, start_fail=False, run_raises=False, **kw):
        events = self.events;codes = codes or {}
        def backup_fn(root):
            events.append('backup')
            if backup_fail:raise RuntimeError('backup failed')
            return dict(path=str(Path(root) / '.local/backups/x'))
        def start_server(sandbox):
            events.append(('start', Path(sandbox).name))
            if start_fail:raise RuntimeError('no server')
            return FakeServer(events)
        def run_test(test, *, url, cwd):
            events.append(('test', test, url, Path(cwd).name))
            if mutate:mutate()
            if run_raises:raise RuntimeError('crash')
            return codes.get(test, 0)
        return ir.run_isolated(self.root, tracked_files=self.tracked, backup_fn=backup_fn, start_server=start_server, run_test=run_test, **kw)

    def test_the_order_is_backup_then_sandbox_then_server_then_tests_then_stop_and_the_default_tests_are_the_two_server_tests(self):
        result = self.run_it()
        kinds = [e if isinstance(e, str) else e[0] for e in self.events]
        self.assertEqual(kinds, ['backup', 'start', 'test', 'test', 'stop'])
        tests = [e[1] for e in self.events if isinstance(e, tuple) and e[0] == 'test']
        self.assertEqual(tests, ['tests/test_daily_ui.py', 'tests/test_viewer_ui.py'])
        self.assertTrue(result['ok']);self.assertTrue(result['source_unchanged']);self.assertFalse(result['kept'])
        self.assertEqual([r['returncode'] for r in result['results']], [0, 0])
        self.assertEqual(list((self.root / '.local/sandbox').iterdir()), [])                  # a clean run leaves no sandbox behind
        sandbox_names = {e[1] if e[0] == 'start' else e[3] for e in self.events if isinstance(e, tuple)}
        self.assertEqual(len(sandbox_names), 1)                                               # server and tests ran in the same sandbox folder

    def test_a_failing_test_makes_the_run_fail_but_the_remaining_tests_still_run_and_the_sandbox_is_kept_for_inspection(self):
        result = self.run_it(codes={'tests/test_daily_ui.py': 1})
        self.assertFalse(result['ok']);self.assertEqual([r['returncode'] for r in result['results']], [1, 0])
        self.assertTrue(result['kept']);self.assertTrue(Path(result['sandbox']).exists());self.assertEqual(self.events.count('stop'), 1)

    def test_a_change_to_the_operating_data_during_the_run_is_reported_and_fails_the_run(self):
        target = self.root / 'data/work/user_input/daily-latest.json'
        result = self.run_it(mutate=lambda: target.write_text('{"a": 99}', encoding='utf-8'))
        self.assertFalse(result['ok']);self.assertFalse(result['source_unchanged']);self.assertEqual(result['source_changes']['changed'], ['data/work/user_input/daily-latest.json'])
        self.assertTrue(result['kept'])

    def test_the_server_is_always_stopped_even_when_a_test_raises(self):
        with self.assertRaises(RuntimeError):
            self.run_it(run_raises=True)
        self.assertEqual(self.events.count('stop'), 1)
        self.assertTrue(any(self.root.joinpath('.local/sandbox').iterdir()))                  # kept for inspection

    def test_a_backup_failure_stops_everything_before_any_sandbox_or_server_exists(self):
        with self.assertRaises(RuntimeError):
            self.run_it(backup_fail=True)
        self.assertEqual(self.events, ['backup']);self.assertFalse((self.root / '.local/sandbox').exists())

    def test_a_server_that_cannot_start_removes_the_sandbox_and_never_runs_tests(self):
        with self.assertRaises(RuntimeError):
            self.run_it(start_fail=True)
        self.assertEqual([e if isinstance(e, str) else e[0] for e in self.events], ['backup', 'start'])
        self.assertEqual(list((self.root / '.local/sandbox').iterdir()), [])

    def test_keep_leaves_the_sandbox_even_after_a_clean_run(self):
        result = self.run_it(keep=True)
        self.assertTrue(result['ok']);self.assertTrue(result['kept']);self.assertTrue(Path(result['sandbox']).exists())

    def test_test_paths_must_be_existing_test_files_of_the_sandbox_and_are_checked_before_the_server_starts(self):
        for bad in (['tests/nope_ui.py'], ['../x.py'], ['/etc/passwd'], ['app.py'], [], 'tests/test_daily_ui.py', [5]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.run_it(tests=bad)
        self.assertNotIn('start', [e if isinstance(e, str) else e[0] for e in self.events])
        result = self.run_it(tests=['tests/test_viewer_ui.py']);self.assertEqual([r['test'] for r in result['results']], ['tests/test_viewer_ui.py'])


class SurvivorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root = make_project(self.tmp.name)
        self.tracked = add_code(self.root);(self.root / 'tests/notes.txt').write_text('n', encoding='utf-8');self.tracked.append('tests/notes.txt')
        self.calls = []

    def go(self, **kw):
        def backup_fn(root):
            self.calls.append('backup');return dict(path='x')
        return ir.run_isolated(self.root, tracked_files=self.tracked, backup_fn=backup_fn, start_server=lambda s: self.calls.append('start'),
                               run_test=lambda *a, **k: 0, **kw)

    def test_invalid_arguments_are_refused_before_the_backup_even_runs(self):
        for kw in (dict(keep='yes'), dict(keep=1), dict(tests=['tests/notes.txt']), dict(tests=['tests/../app.py']), dict(tests=['tests/x/../../app.py'])):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self.go(**kw)
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
