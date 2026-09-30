"""Dashboard startup freshness policy, bounded retries and last-good fallback."""
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .core import digest, validate_snapshot
from . import local_config
from .store import Store

KST = ZoneInfo('Asia/Seoul')
STATUS_KEY = 'infomax_auto_refresh'


def target_date(root, config, checked_at):
    """Daily exports exclude today's partial observations, including after close.

    Without a supplied market calendar, weekdays are only a conservative estimate;
    Korean holidays must never be certified as trading sessions from this fallback.
    """
    today = checked_at.astimezone(KST).date()
    calendar = config.get('trading_calendar_file')
    if calendar:
        data = json.loads((Path(root) / calendar).read_text(encoding='utf-8-sig'))
        start = date.fromisoformat(data['valid_from'])
        end = date.fromisoformat(data['valid_through'])
        sessions = [date.fromisoformat(d) for d in data['sessions']]
        if (not data.get('source') or not start <= today <= end or
                sessions != sorted(set(sessions)) or
                any(d < start or d > end for d in sessions)):
            raise ValueError('거래일 달력 범위/출처/정렬 확인 필요')
        earlier = [d for d in sessions if d < today]
        if not earlier:
            raise ValueError('달력에 이전 거래일이 없습니다')
        return earlier[-1].isoformat(), 'configured_market_calendar'
    previous = today - timedelta(days=1)
    while previous.weekday() >= 5:
        previous -= timedelta(days=1)
    return previous.isoformat(), 'weekday_estimate_holidays_unverified'


def seconds_since(value, checked_at):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return None
        seconds = (checked_at - parsed).total_seconds()
        return seconds if seconds >= 0 else None
    except (TypeError, ValueError):
        return None


def summary(snapshot, previous, *, status, checked_at, target, calendar_basis,
            attempted=False, error=None):
    rows = snapshot['companies'] if snapshot else []
    old = {r['code']: r for r in previous['companies']} if previous else {}
    changed = [r for r in rows if digest(r) != digest(old.get(r['code']))] if attempted and not error else []
    updated_prices = 0
    for row in changed:
        old_prices = {p['date']: p for p in old.get(row['code'], {}).get('prices', [])}
        updated_prices += sum(b != old_prices.get(b['date']) for b in row.get('prices', []))
    meta = snapshot['meta'] if snapshot else {}
    price_date = meta.get('price_date')
    return dict(status=status, success=status in ('complete', 'unchanged', 'cached'),
                attempted=attempted, checked_at=checked_at.isoformat(timespec='seconds'),
                data_as_of=price_date, source_fetched_at=meta.get('fetched_at'),
                target_date=target, calendar_basis=calendar_basis,
                stale=not price_date or not target or price_date < target,
                updated_companies=len(changed), price_records=sum(len(r.get('prices', [])) for r in rows),
                updated_price_records=updated_prices,
                failed_companies=len(old) if error else 0,
                failure_scope='whole_refresh' if error else None,
                fallback=bool(snapshot) and bool(error), error=error)


def ensure_data(root, *, force=False, provider=None, checked_at=None):
    """Never substitute fixture data. File/transport failures return validated cache.

    ``provider`` is injectable for offline tests or a future verified API adapter.
    The existing refresh transaction owns promotion and the per-PC lock.
    """
    checked_at = checked_at or datetime.now(KST)
    if checked_at.tzinfo is None:
        raise ValueError('timezone-aware checked_at required')
    checked_at = checked_at.astimezone(KST)
    snapshot, store, previous, prior = None, None, None, {}
    target, basis = None, 'unavailable'
    attempted = False
    try:
        local = local_config.load_local(root)
        root = local.get('project_root', root)
        store = Store(local['data_dir'], local['profile'], 'user_input')
        snapshot = store.latest()
        manual = local.get('manual_snapshot_file')
        if (snapshot is None and local['profile'] != 'unknown' and
                'infomax_manual' in local['enabled_data_adapters'] and manual is not None and manual.is_file()):
            snapshot = json.loads(manual.read_text(encoding='utf-8-sig'))
        if snapshot is not None:
            validate_snapshot(snapshot)
            if snapshot['meta']['data_mode'] != 'user_input':
                raise ValueError('cache mode mismatch')
        previous = snapshot
        config = local.get('infomax_refresh') or {}
        target, basis = target_date(root, config, checked_at)
        ttl = config.get('freshness_seconds', 900)
        retry = config.get('retry_seconds', 60)
        if any(type(v) is not int or not 1 <= v <= 86400 for v in (ttl, retry)):
            raise ValueError('갱신 간격은 1~86400 정수 초로 설정하세요')
        prior = store.setting(STATUS_KEY, {})
        age = seconds_since(prior.get('last_attempt_at'), checked_at)
        fresh = snapshot is not None and snapshot['meta']['price_date'] >= target
        same_snapshot = snapshot is not None and prior.get('snapshot_id') == digest(snapshot)
        policy_hash = digest(config)
        same_policy = prior.get('policy_hash') == policy_hash
        source_age = seconds_since(snapshot['meta'].get('fetched_at'), checked_at) if snapshot else None
        if not force and not prior and fresh and source_age is not None and source_age < ttl:
            receipt = summary(snapshot, previous, status='cached', checked_at=checked_at,
                              target=target, calendar_basis=basis)
            return dict(snapshot=snapshot, receipt=receipt)
        if not force and same_snapshot and same_policy and age is not None:
            if fresh and prior.get('success') and age < ttl:
                receipt = summary(snapshot, previous, status='cached', checked_at=checked_at,
                                  target=target, calendar_basis=basis)
                receipt['last_attempt_at'] = prior.get('last_attempt_at')
                return dict(snapshot=snapshot, receipt=receipt)
        if (not force and same_policy and age is not None and age < retry and
                (same_snapshot or snapshot is None)):
            receipt = summary(snapshot, previous, status='retry_wait', checked_at=checked_at,
                              target=target, calendar_basis=basis, error=prior.get('error'))
            receipt['last_attempt_at'] = prior.get('last_attempt_at')
            return dict(snapshot=snapshot, receipt=receipt)
        if local['profile'] == 'unknown' or 'infomax_manual' not in local['enabled_data_adapters']:
            return dict(snapshot=snapshot, receipt=summary(snapshot, previous, status='setup_pending',
                checked_at=checked_at, target=target, calendar_basis=basis, error='PC 프로필·파일 연결 설정 대기'))
        from .refresh import refresh
        attempted = True
        result = refresh(root, provider=provider) if provider is not None else refresh(root)
        snapshot = result['snapshot']
        receipt = summary(snapshot, previous, status=result['receipt']['status'],
                          checked_at=checked_at, target=target, calendar_basis=basis, attempted=True)
        receipt['last_success_at'] = result['receipt'].get('last_success_at')
    except Exception as exc:
        # Exception strings from providers may contain URLs, credentials or private paths.
        # Expose only the error class here. The persisted last good snapshot is authoritative.
        if store is not None:
            try:
                saved = store.latest()
                if saved is not None:
                    validate_snapshot(saved)
                    if saved['meta']['data_mode'] == 'user_input':
                        snapshot = saved
                    else:
                        snapshot = previous
                else:
                    snapshot = previous
            except Exception:
                snapshot = previous
        receipt = summary(snapshot, previous, status='failed', checked_at=checked_at,
                          target=target, calendar_basis=basis, attempted=attempted,
                          error='갱신 실패 · ' + type(exc).__name__)
    if attempted:
        receipt['last_attempt_at'] = checked_at.isoformat(timespec='seconds')
    else:
        receipt['last_attempt_at'] = prior.get('last_attempt_at')
    receipt['snapshot_id'] = digest(snapshot) if snapshot else None
    receipt['policy_hash'] = digest(config) if 'config' in locals() else None
    if store is not None:
        try:
            store.save_setting(STATUS_KEY, receipt)
        except Exception:
            receipt['status'] = 'partial' if snapshot else 'failed'
            receipt['success'] = False
            receipt['error'] = '갱신 상태 저장 실패'
    return dict(snapshot=snapshot, receipt=receipt)
