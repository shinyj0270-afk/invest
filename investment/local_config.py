"""PC-local paths and explicit source gates. Contains no credentials."""
import json
from pathlib import Path


def load_local(root):
    root = Path(root).resolve()
    path = root / 'config/local.json'
    config = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    profile = config.get('profile', 'unknown')
    if profile not in ('work', 'home', 'unknown'):
        raise ValueError('PC profile must be work/home/unknown')
    configured_root = config.get('project_root') or '.'
    project_root = Path(configured_root)
    if not project_root.is_absolute():
        project_root = root / project_root
    if project_root.resolve() != root:
        raise ValueError('Local project_root does not match this checkout; configure this PC')
    data = Path(config.get('data_dir') or 'data')
    if not data.is_absolute():
        data = root / data
    manual_file = config.get('manual_snapshot_file')
    if manual_file:
        manual_file = Path(manual_file)
        if not manual_file.is_absolute():
            manual_file = root / manual_file
        manual_file = manual_file.resolve()
    sources = config.get('enabled_data_adapters', [])
    if not isinstance(sources, list) or any(s not in ('kiwoom', 'dart', 'infomax_manual') for s in sources):
        raise ValueError('Unknown local source permission')
    return dict(profile=profile, project_root=root, data_dir=data.resolve(),
                market_events=config.get('market_events'),
                infomax_refresh=config.get('infomax_refresh'),
                manual_snapshot_file=manual_file,
                enabled_data_adapters=sources,
                scheduled_jobs_enabled=config.get('scheduled_jobs_enabled', False) is True)


def require_profile(local, requested=None):
    actual = local['profile']
    if actual == 'unknown' or (requested is not None and requested != actual):
        raise ValueError('Explicit matching PC profile required; config/local.json')
    return actual
