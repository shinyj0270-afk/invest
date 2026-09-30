"""Read-only Infomax file adapters. No terminal/API authentication is inferred."""
import json
from pathlib import Path

from .core import validate_snapshot


class SavedDailyProvider:
    def __init__(self, root, config, converter):
        self.root, self.config, self.converter = Path(root), config, converter

    def path(self, key):
        value = self.config.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError('갱신 파일 설정 누락: ' + key)
        return (self.root / value).resolve()

    def fetch(self):
        identities = json.loads(self.path('company_config').read_text(encoding='utf-8-sig'))
        policy = json.loads(self.path('policy').read_text(encoding='utf-8-sig'))
        identities['decisions'] = policy.get('decisions', policy)
        snapshot = self.converter(self.path('daily_file'), identities)
        return snapshot, dict(source=snapshot['meta']['source_files'], config=identities), self.path('daily_file').name


class SavedSnapshotProvider:
    """Compatibility with the PC's existing reviewed manual export."""
    def __init__(self, path):
        self.path = Path(path)

    def fetch(self):
        if self.path.stat().st_size > 30 * 1024 * 1024:
            raise ValueError('스냅샷 파일 크기 제한 초과')
        snapshot = validate_snapshot(json.loads(self.path.read_text(encoding='utf-8-sig')))
        if 'sessions' not in snapshot:
            dates = [{b['date'] for b in r.get('prices', [])} for r in snapshot['companies']]
            snapshot['sessions'] = sorted(set.intersection(*dates)) if dates else []
            snapshot['meta'].setdefault('calendar_basis', 'observed_dates_unverified')
        return snapshot, snapshot, self.path.name


def provider_for(root, local, converter):
    if 'infomax_manual' not in local['enabled_data_adapters']:
        raise ValueError('이 PC의 인포맥스 저장 파일 경로를 먼저 설정하세요')
    config = local.get('infomax_refresh') or {}
    kind = config.get('provider', 'daily' if config.get('daily_file') else 'snapshot')
    if kind == 'daily':
        return SavedDailyProvider(root, config, converter)
    if kind == 'snapshot' and local.get('manual_snapshot_file'):
        return SavedSnapshotProvider(local['manual_snapshot_file'])
    raise ValueError('이 PC의 인포맥스 저장 파일 경로를 먼저 설정하세요')
