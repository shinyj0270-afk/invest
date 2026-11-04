"""Back up, run UI tests in isolation, and check the original data afterwards."""
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath, PureWindowsPath
from . import data_backup, sandbox

DEFAULT_TESTS = ('tests/test_daily_ui.py', 'tests/test_viewer_ui.py')


class _Server:
    def __init__(self, process, url):
        self.process, self.url = process, url

    def stop(self):
        if self.process.poll() is not None:return
        self.process.terminate()
        try:self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill();self.process.wait()


def _start_server(cwd):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0));port = sock.getsockname()[1]
    command = [sys.executable, '-m', 'streamlit', 'run', 'app.py', '--server.port', str(port),
               '--server.address', '127.0.0.1', '--server.headless', 'true', '--browser.gatherUsageStats', 'false']
    env = dict(os.environ, PYTHONPATH=str(cwd), PYTHONIOENCODING='utf-8')
    options = dict(creationflags=subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else {}
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **options)
    server = _Server(process, f'http://127.0.0.1:{port}');deadline = time.monotonic() + 60
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:raise RuntimeError('격리 서버가 조기에 종료되었습니다')
            try:
                with opener.open(server.url + '/_stcore/health', timeout=2) as response:
                    if response.status == 200:return server
            except (OSError, urllib.error.URLError):pass
            time.sleep(0.2)
        raise RuntimeError('격리 서버 시작 대기 시간을 초과했습니다')
    except BaseException:
        server.stop();raise


def _run_test(test, *, url, cwd):
    env = dict(os.environ, INVESTMENT_TEST_URL=url, PYTHONPATH=str(cwd), PYTHONIOENCODING='utf-8')
    try:
        return subprocess.run([sys.executable, '-X', 'utf8', test], cwd=cwd, env=env, timeout=300).returncode
    except subprocess.TimeoutExpired:return 124


def _tests(tests):
    tests = DEFAULT_TESTS if tests is None else tests
    if not isinstance(tests, (list, tuple)) or not tests:raise ValueError('테스트 경로 목록이 필요합니다')
    for test in tests:
        if not isinstance(test, str) or not test.startswith('tests/') or not test.endswith('.py'):
            raise ValueError('tests/ 아래 Python 테스트 경로가 필요합니다')
        if '\\' in test or PureWindowsPath(test).drive or PurePosixPath(test).is_absolute() or '..' in PurePosixPath(test).parts:
            raise ValueError('상대 테스트 경로 확인 필요')
    return tuple(tests)


def run_isolated(root, tests=None, *, keep=False, tracked_files=None, backup_fn=None, start_server=None, run_test=None):
    tests = _tests(tests)
    if not isinstance(keep, bool):raise ValueError('keep은 불리언이어야 합니다')
    backup_fn = data_backup.backup if backup_fn is None else backup_fn
    start_server = _start_server if start_server is None else start_server
    run_test = _run_test if run_test is None else run_test
    saved = backup_fn(root)
    info = sandbox.prepare(root, tracked_files=tracked_files);dest = Path(info['dest'])
    try:
        if any(not (dest / test).is_file() or not (dest / test).resolve().is_relative_to(dest) for test in tests):
            raise ValueError('샌드박스에 테스트 파일이 없습니다')
        server = start_server(dest)
    except BaseException:
        sandbox.remove(dest);raise
    try:
        results = [dict(test=test, returncode=run_test(test, url=server.url, cwd=dest)) for test in tests]
    finally:server.stop()
    changes = sandbox.check_source(dest)
    ok = all(r['returncode'] == 0 for r in results) and changes['unchanged']
    kept = keep or not ok
    if not kept:sandbox.remove(dest)
    return dict(ok=ok, results=results, source_unchanged=changes['unchanged'], source_changes=changes,
                backup=saved, sandbox=str(dest), kept=kept)
