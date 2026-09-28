"""Package explicitly selected project files; never crawl a working directory."""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    'AGENTS.md', 'CLAUDE.md', 'docs/DUAL_PC_WORKFLOW.md',
    'investment/local_config.py', 'tools/pc_check.py', 'tests/test_dual_pc.py',
    'scripts/pc-start.ps1', 'scripts/pc-finish.ps1',
    '.gitignore', 'README.md', 'DATA_DICTIONARY.md', 'VALIDATION.md',
    'INVESTMENT_META_PROMPT_v05.md', 'CODEX_APPLY_v05.txt',
    'INVESTMENT_Dashboard.html', 'build.py', 'snapshot.schema.json',
    'snapshot_empty.json', 'PROJECT_STATE.md', 'HANDOFF.md',
    'START_ON_HOME_PC.md', 'INFOMAX_CONNECTIVITY.md', 'INFOMAX_SAMPLE_VALIDATION.md',
    'INFOMAX_IMPORT.md', 'requirements-import.txt', 'config/infomax.example.json',
    'tools/infomax_import.py', 'tools/infomax_demo.py', 'tools/infomax_review.py',
    'INFOMAX_REVIEW_STATUS.md', 'tests/test_infomax_review.cjs', 'tests/test_review_tolerance.py',
    'tests/test_marketcap_history.py', 'tools/company_finish.py',
    'tests/test_company_finish.py', 'COMPANY_PC_COMPLETE.md',
    'tools/infomax_financials.py', 'tests/test_financial_reconciliation.py',
    'PROVIDER_FINANCIAL_AUDIT.md',
    'USER_DATA_DECISIONS.md', 'config/infomax.user-decisions.json',
    'tools/infomax_user_policy.py', 'tests/test_user_policy.py',
    'app.py', 'batch.py', 'collect.py', '.streamlit/config.toml', 'requirements.lock.txt',
    'investment/__init__.py', 'investment/core.py', 'investment/store.py',
    'investment/adapters.py', 'investment/fixture.py', 'investment/research.py',
    'investment/trend.py', 'investment/report.py', 'investment/metrics.py',
    'config/runtime.example.json', 'scripts/register-tasks.ps1', 'scripts/unregister-tasks.ps1',
    'tests/test_research_app.py', 'tests/test_streamlit_app.py',
    'tests/verify_report_browser.py', 'tests/verify_live_app.py', 'tools/verify_all.py',
    'IMPLEMENTATION_AUDIT.md', 'ENVIRONMENT.md', 'RESEARCH_MODEL.md',
    'examples/infomax_snapshot_fixture.json',
    'tests/test_infomax_import.py', 'tests/test_infomax_ui.cjs',
    'requirements-ui.txt', 'config/profile.example.json',
    'tools/handoff.py',
    'src/engine.js', 'src/ui.js', 'src/portfolio_engine.js',
    'src/portfolio_ui.js', 'src/shell.html', 'src/style.css',
    'examples/holdings_research_empty.json',
    'examples/holdings_research_fixture.json',
    'tests/test_engine.js', 'tests/test_portfolio.js',
    'tests/test_ui.py', 'tests/test_portfolio_ui.py',
)
MANIFEST = 'INVESTMENT/HANDOFF_MANIFEST.json'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify(path):
    with ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive entries')
        manifest = json.loads(archive.read(MANIFEST))
        entries = manifest['files']
        expected = {MANIFEST}
        for name, expected_hash in entries.items():
            if (not isinstance(name, str) or '\\' in name or ':' in name
                    or name.startswith('/') or any(p in ('', '.', '..') for p in name.split('/'))):
                raise ValueError('Unsafe manifest path')
            archive_name = 'INVESTMENT/' + name
            expected.add(archive_name)
            if digest(archive.read(archive_name)) != expected_hash:
                raise ValueError(f'Hash mismatch: {name}')
        if set(names) != expected:
            raise ValueError('Unexpected or missing archive entries')
    print(f'VERIFIED {len(entries)} files; version={manifest["version"]}')


def package(version):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', version):
        raise ValueError('Version must use letters, digits, dots, underscores or hyphens')
    state = (ROOT / 'PROJECT_STATE.md').read_text(encoding='utf-8')
    if f'`{version}`' not in state:
        raise ValueError('Update PROJECT_STATE.md with the exact version before packaging')
    payload = {}
    for name in FILES:
        path = ROOT / name
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError(f'Linked or external file: {name}')
        payload[name] = path.read_bytes()
    manifest = {
        'version': version,
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'files': {name: digest(data) for name, data in payload.items()},
        'scope': 'Explicit source, documentation and synthetic test files only',
    }
    destination = ROOT / 'dist'
    destination.mkdir(exist_ok=True)
    if destination.is_symlink() or not destination.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError('Output directory must stay inside this project')
    path = destination / f'INVESTMENT_{version}.zip'
    with ZipFile(path, 'x', compression=ZIP_DEFLATED) as archive:
        for name, data in payload.items():
            archive.writestr('INVESTMENT/' + name, data)
        archive.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'))
    verify(path)
    checksum = digest(path.read_bytes())
    path.with_suffix('.sha256').write_text(f'{checksum}  {path.name}\n', encoding='utf-8')
    print(f'CREATED dist/{path.name}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--version')
    choice.add_argument('--verify', type=Path)
    args = parser.parse_args()
    if args.verify:
        verify(args.verify)
    else:
        package(args.version)
