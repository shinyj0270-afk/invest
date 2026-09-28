"""Offline fixture verification for the curated two-PC source set."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
env = dict(os.environ, PYTHONIOENCODING='utf-8')
commands = [
    [sys.executable, 'build.py'],
    [sys.executable, '-m', 'unittest', 'tests.test_research_app', 'tests.test_streamlit_app'],
    [sys.executable, 'batch.py', 'init-fixture'],
    [sys.executable, 'batch.py', 'daily'],
    [sys.executable, 'batch.py', 'weekly'],
]
if (ROOT/'tests/test_engine.js').exists():
    commands += [['node', 'tests/test_engine.js'], ['node', 'tests/test_portfolio.js']]
for command in commands:
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, encoding='utf-8', errors='replace',
                            capture_output=True, timeout=180)
    print(('PASS ' if result.returncode == 0 else 'FAIL ') + ' '.join(command[1:]), flush=True)
    if result.returncode:
        print((result.stdout + result.stderr)[-3000:], file=sys.stderr)
        sys.exit(result.returncode)
