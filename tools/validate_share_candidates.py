"""Review an explicit source list and test a temporary, local home-profile checkout.

This never creates an archive, initializes Git, accesses a remote or transmits files.
Content scanning is a heuristic; direct review of the shared content remains necessary.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'config/share_candidates.json'
OUT = ROOT / 'validation/current'
BLOCKED_PARTS = {'.git', '.venv', '.local', 'data', 'private_data', 'dist', 'validation',
                 'node_modules', '__pycache__', '.codex', '.claude', 'logs'}
BLOCKED_NAMES = {'local.json', 'runtime.local.json', 'secrets.toml'}
SUSPICIOUS = {
    'embedded_url_userinfo': re.compile(r'https?://[^\s/]+:[^\s/@]+@', re.I),
    'private_key_header': re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----'),
}


def relative_file(name):
    path = Path(name.replace('\\', '/'))
    if path.is_absolute() or '..' in path.parts or not path.parts or any(x.lower() in BLOCKED_PARTS for x in path.parts):
        raise ValueError('Excluded or unsafe candidate path: ' + name)
    if path.name.lower() in BLOCKED_NAMES or path.name.lower().startswith('.env'):
        raise ValueError('Local settings in candidate path: ' + name)
    if re.search(r'\.(?:db|sqlite3?)(?:$|[-.])', path.name, re.I) or path.suffix.lower() == '.log':
        raise ValueError('Local database or log in candidate path: ' + name)
    return path


def audit():
    entries = json.loads(MANIFEST.read_text(encoding='utf-8'))['files']
    if not entries or len(entries) != len(set(entries.values())):
        raise ValueError('Candidate list is empty or has duplicate targets')
    issues = []
    digests = {}
    for source, target in entries.items():
        source_path = relative_file(source)
        relative_file(target)
        path = ROOT / source_path
        if not path.resolve().is_relative_to(ROOT.resolve()) or not path.is_file() or path.is_symlink():
            issues.append((source, 'missing_or_symlink'))
            continue
        content = path.read_bytes()
        try: text = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            issues.append((source, 'non_utf8'))
            continue
        if '\0' in text: issues.append((source, 'binary_content'))
        # Exact .invalid URLs below are intentional rejection fixtures, not credentials.
        fake_urls = {
            'tests/test_portfolio.js': ('https://' + 'synthetic:synthetic@example.invalid',),
            'tests/test_dual_pc.py': ('https://' + 'fake:NOT_REAL@example.invalid/repo?key=NOT_REAL',),
        }
        scan_text = text
        for fixture in fake_urls.get(source, ()):
            scan_text = scan_text.replace(fixture, '')
        for label, pattern in SUSPICIOUS.items():
            if pattern.search(scan_text): issues.append((source, label))
        digests[target] = hashlib.sha256(content).hexdigest()
    return entries, digests, issues


def main(*, ui=False):
    OUT.mkdir(parents=True, exist_ok=True)
    entries, digests, issues = audit()
    report = dict(executed_at=datetime.now(timezone.utc).isoformat(),
                  candidate_files=len(entries), issues=[dict(path=p, rule=r) for p, r in issues],
                  files=digests, external_transfer='not_executed',
                  content_review='credential_and_local_path_checks_only',
                  remote_destination='not_selected',
                  synthetic_fixture_allowlisted=['tests/test_portfolio.js: example.invalid URL',
                                                 'tests/test_dual_pc.py: example.invalid URL'])
    if not issues:
        # Temporary test checkout stays inside this workspace and is removed on exit.
        with tempfile.TemporaryDirectory(prefix='share-check-', dir=OUT) as folder:
            stage = Path(folder).resolve()
            if OUT.resolve() not in stage.parents:
                raise ValueError('Temporary stage escaped validation/current')
            for source, target in entries.items():
                destination = stage / relative_file(target)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative_file(source), destination)
            local = stage / 'config/local.json'
            local.write_text(json.dumps(dict(profile='home', project_root='.', data_dir='data',
                                             manual_snapshot_file=None, enabled_data_adapters=[],
                                             scheduled_jobs_enabled=False)), encoding='utf-8')
            env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONPATH=str(stage))
            commands = [
                [sys.executable, 'tools/verify_portable.py'],
                [sys.executable, '-c',
                 "from streamlit.testing.v1 import AppTest; "
                 "a=AppTest.from_file('app.py',default_timeout=30).run(); "
                 "assert len(a.exception)==0; "
                 "assert any('실제 저장자료가 없습니다' in x.value for x in a.info); "
                 "print('PASS home actual mode empty without manual file')"],
            ]
            if ui:
                commands += [[sys.executable, 'tests/' + name] for name in (
                    'test_dashboard_journey_ui.py', 'test_dashboard_upgrade_ui.py',
                    'test_trend_diagnostics_ui.py', 'test_trend_chart_ui.py')]
            results = []
            for command in commands:
                run = subprocess.run(command, cwd=stage, env=env, capture_output=True,
                                     text=True, encoding='utf-8', errors='replace', timeout=240)
                results.append(dict(command=command[1], exit_code=run.returncode))
                (OUT / ('share-test-' + str(len(results)) + '.txt')).write_text(
                    run.stdout + run.stderr, encoding='utf-8')
                if run.returncode: break
            report['validation'] = results
    (OUT / 'share-candidate-review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Candidate paths checked:', len(entries), '| flagged:', len(issues))
    for path, rule in issues: print('FLAG', path, rule)
    for result in report.get('validation', []):
        print('PASS' if result['exit_code'] == 0 else 'FAIL', result['command'])
    return 1 if issues or any(x['exit_code'] for x in report.get('validation', [])) else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ui', action='store_true', help='Also run four synthetic UI journeys in the isolated copy')
    args = parser.parse_args()
    sys.exit(main(ui=args.ui))
