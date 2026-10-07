"""Isolated launcher, browser selection and validation boundary regressions."""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from tools import open_dashboard as launcher
from tools import browser_runtime as browser
from tools import validate_share_candidates as sharing

ROOT = Path(__file__).resolve().parents[1]


class LauncherTests(unittest.TestCase):
    def test_health_requires_matching_app_version_and_checkout(self):
        expected = dict(app='investment-holdings-sync', version=1,
                        root_id=hashlib.sha256(str(launcher.ROOT.resolve()).encode()).hexdigest())
        for record, valid in [(expected, True), ({**expected, 'root_id': 'other'}, False),
                              ({**expected, 'version': 2}, False),
                              ({**expected, 'app': 'other'}, False), ([], False), (None, False)]:
            with self.subTest(record=record), patch.object(launcher, 'urlopen',
                    return_value=io.BytesIO(json.dumps(record).encode())):
                self.assertEqual(launcher.health(8767), valid)

    def test_existing_server_reused_without_process_or_browser(self):
        with patch.object(sys, 'argv', ['launch', '--port', '12345', '--no-browser']), \
             patch.object(launcher, 'health', return_value=True) as health, \
             patch.object(launcher.subprocess, 'Popen') as spawn, \
             patch.object(launcher.webbrowser, 'open') as browse:
            launcher.main()
            health.assert_called_once_with(12345)
            spawn.assert_not_called()
            browse.assert_not_called()

    def test_occupied_port_never_starts_or_stops_process(self):
        sock = MagicMock()
        sock.__enter__.return_value.connect_ex.return_value = 0
        with patch.object(sys, 'argv', ['launch', '--no-browser']), \
             patch.object(launcher, 'health', return_value=False), \
             patch('socket.socket', return_value=sock), \
             patch.object(launcher.subprocess, 'Popen') as spawn:
            with self.assertRaisesRegex(RuntimeError, '기존 프로그램'):
                launcher.main()
            spawn.assert_not_called()

    def test_invalid_port_rejected_before_health_query(self):
        with patch.object(sys, 'argv', ['launch', '--port', '0']), \
             patch.object(launcher, 'health') as health, patch('sys.stderr', io.StringIO()):
            with self.assertRaises(SystemExit) as result:
                launcher.main()
            self.assertEqual(result.exception.code, 2)
            health.assert_not_called()

    def test_failed_start_reports_error_in_temporary_checkout(self):
        sock = MagicMock()
        sock.__enter__.return_value.connect_ex.return_value = 1
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(launcher, 'ROOT', Path(folder)), \
             patch.object(sys, 'argv', ['launch', '--no-browser']), \
             patch.object(launcher, 'health', return_value=False), \
             patch('socket.socket', return_value=sock), \
             patch.object(launcher.subprocess, 'Popen') as spawn:
            spawn.return_value.poll.return_value = 1
            with self.assertRaisesRegex(RuntimeError, '실행 환경'):
                launcher.main()
            self.assertEqual(spawn.call_args.args[0][0], sys.executable)
            self.assertEqual(spawn.call_args.kwargs['cwd'], Path(folder))


class BrowserTests(unittest.TestCase):
    def test_explicit_browser_wins_and_missing_override_fails(self):
        with tempfile.TemporaryDirectory(prefix='browser path ') as folder:
            exe = Path(folder) / 'custom.exe'
            exe.touch()
            with patch.dict(os.environ, {'CHROMIUM_PATH': str(exe)}, clear=True):
                self.assertEqual(browser.chromium_options(), {'executable_path': str(exe)})
                exe.unlink()
                with self.assertRaisesRegex(ValueError, 'CHROMIUM_PATH'):
                    browser.chromium_options()

    def test_path_browser_and_playwright_fallback(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(browser.shutil, 'which', return_value='browser'):
            self.assertEqual(browser.chromium_options(), {'executable_path': 'browser'})
        with patch.dict(os.environ, {}, clear=True), patch.object(browser.shutil, 'which', return_value=None):
            self.assertEqual(browser.chromium_options(), {})

    def test_windows_install_root_is_not_fixed(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / 'Microsoft/Edge/Application/msedge.exe'
            exe.parent.mkdir(parents=True)
            exe.touch()
            with patch.dict(os.environ, {'PROGRAMFILES': folder}, clear=True), \
                 patch.object(browser.shutil, 'which', return_value=None):
                self.assertEqual(browser.chromium_options(), {'executable_path': str(exe)})


class IsolationTests(unittest.TestCase):
    def test_private_cache_database_and_log_cannot_enter_manifest(self):
        for name in ('.local/holdings-sync/cache.json', 'state.sqlite3', 'state.sqlite3-wal',
                     'state.db-journal', 'server.log', 'config/local.json', '../outside.py'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                sharing.relative_file(name)
        self.assertEqual(sharing.relative_file('tools/browser_runtime.py'), Path('tools/browser_runtime.py'))

    def test_validation_writes_only_to_copy_and_does_not_copy_local_input(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'config').mkdir()
            (root / 'config/profile.example.json').write_text('{}')
            private = root / 'config/local.json'
            private.write_text('{"profile":"work","data_dir":"existing"}')
            source = root / 'app.py'
            source.write_text('# original')
            (root / '.local').mkdir()
            (root / '.local/input.txt').write_text('synthetic local sentinel')
            entries = {'app.py': 'app.py', 'config/profile.example.json': 'config/profile.example.json'}
            calls = []
            def run(command, *, cwd, **kwargs):
                calls.append(command)
                self.assertNotEqual(cwd, root)
                self.assertFalse((cwd / '.local').exists())
                cfg = json.loads((cwd / 'config/local.json').read_text())
                self.assertEqual((cfg['profile'], cfg['data_dir']), ('home', 'data'))
                self.assertFalse(cfg['scheduled_jobs_enabled'])
                (cwd / 'app.py').write_text('# changed only in copy')
                return subprocess.CompletedProcess(command, 0, 'synthetic validation\n', '')
            with patch.object(sharing, 'ROOT', root), patch.object(sharing, 'OUT', root / 'validation'), \
                 patch.object(sharing, 'audit', return_value=(entries, {}, [])), \
                 patch.object(sharing.subprocess, 'run', side_effect=run):
                self.assertEqual(sharing.main(ui=True), 0)
            self.assertEqual(len(calls), 8)
            self.assertIn('tests/test_portfolio_risk_ui.py', [command[1] for command in calls])
            self.assertIn('tests/test_trend_following_ui.py', [command[1] for command in calls])
            self.assertEqual(source.read_text(), '# original')
            self.assertEqual(json.loads(private.read_text())['profile'], 'work')
            self.assertEqual((root / '.local/input.txt').read_text(), 'synthetic local sentinel')

    def test_validation_stops_and_reports_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'config').mkdir()
            (root / 'config/profile.example.json').write_text('{}')
            with patch.object(sharing, 'ROOT', root), patch.object(sharing, 'OUT', root / 'validation'), \
                 patch.object(sharing, 'audit', return_value=({'config/profile.example.json': 'config/profile.example.json'}, {}, [])), \
                 patch.object(sharing.subprocess, 'run', return_value=subprocess.CompletedProcess([], 7, '', 'fixture failure')) as run:
                self.assertEqual(sharing.main(ui=True), 1)
                self.assertEqual(run.call_count, 1)


@unittest.skipUnless(os.name == 'nt' and shutil.which('pwsh'), 'Windows PowerShell wrapper integration')
class PowerShellTests(unittest.TestCase):
    def fixture(self, root):
        (root / 'scripts').mkdir()
        (root / 'tools').mkdir()
        (root / '.venv/Scripts').mkdir(parents=True)
        shutil.copyfile(sys.executable, root / '.venv/Scripts/python.exe')
        shutil.copyfile(Path(sys.prefix) / 'pyvenv.cfg', root / '.venv/pyvenv.cfg')

    def test_wrapper_forwards_port_no_browser_and_exit_code(self):
        with tempfile.TemporaryDirectory(prefix='launcher space ') as folder:
            root = Path(folder)
            self.fixture(root)
            shutil.copyfile(ROOT / 'scripts/open-investment.ps1', root / 'scripts/open-investment.ps1')
            (root / 'tools/open_dashboard.py').write_text(
                'import sys; assert sys.argv[1:]==["--port","12345","--no-browser"]; sys.exit(17)')
            run = subprocess.run(['pwsh', '-NoProfile', '-File', str(root / 'scripts/open-investment.ps1'),
                                  '-Port', '12345', '-NoBrowser'], capture_output=True, timeout=30)
            self.assertEqual(run.returncode, 17, run.stderr.decode(errors='replace'))

    def test_finish_delegates_to_isolation_and_propagates_failure(self):
        with tempfile.TemporaryDirectory(prefix='finish space ') as folder:
            root = Path(folder)
            self.fixture(root)
            shutil.copyfile(ROOT / 'scripts/pc-finish.ps1', root / 'scripts/pc-finish.ps1')
            (root / 'tools/pc_check.py').write_text('import sys; sys.exit(0)')
            (root / 'tools/validate_share_candidates.py').write_text(
                'import sys; assert sys.argv[1:]==["--ui"]; sys.exit(19)')
            run = subprocess.run(['pwsh', '-NoProfile', '-File', str(root / 'scripts/pc-finish.ps1'), '-RunTests'],
                                 capture_output=True, timeout=30)
            self.assertEqual(run.returncode, 19, run.stderr.decode(errors='replace'))


if __name__ == '__main__':
    unittest.main()
