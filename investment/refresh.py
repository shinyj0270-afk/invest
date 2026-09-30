"""Validate a saved daily workbook, retain reviewed financials, and refresh local lists."""
import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .core import digest, validate_snapshot
from .local_config import require_profile
from . import local_config
from .store import Store
from .infomax_provider import provider_for
from tools.infomax_daily import convert

MARKET_METRICS = ('price', 'market_cap_eok', 'avg_trading_value_20d_eok',
                  'foreign_net_20d_eok', 'institution_net_20d_eok',
                  'foreign_net_turnover_20d_pct', 'institution_net_turnover_20d_pct')
STATUS_KEY = 'infomax_refresh'


def now():
    return datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds')


def merge_daily(previous, daily):
    """Replace market observations only; financial evidence keeps its original dates."""
    validate_snapshot(previous)
    if previous['meta']['data_mode'] != 'user_input':
        raise ValueError('실제 저장자료만 갱신할 수 있습니다')
    old = {r['code']: r for r in previous['companies']}
    if set(old) != {r['code'] for r in daily['companies']}:
        raise ValueError('종목 구성이 다릅니다. 종목 설정과 재무자료를 먼저 확인하세요')
    for key in ('as_of', 'price_date'):
        if daily['meta'][key] < previous['meta'][key]:
            raise ValueError('기존 자료보다 과거인 파일입니다: ' + key)
    old_fetched = previous['meta'].get('fetched_at')
    new_fetched = daily['meta'].get('fetched_at')
    if old_fetched and new_fetched and datetime.fromisoformat(new_fetched) < datetime.fromisoformat(old_fetched):
        raise ValueError('기존 자료보다 과거인 관측 시각입니다')
    result = copy.deepcopy(previous)
    # The daily importer has no financials; never copy those placeholders.
    market_meta = {k: v for k, v in daily['meta'].items()
                   if not k.startswith('financial_') and k != 'warnings'}
    result['meta'].update(market_meta)
    result['sessions'] = daily['sessions']
    market_warnings = [w for w in daily['meta']['warnings'] if w != '재무자료 미수집']
    old_market_warnings = previous['meta'].get('refresh_daily_warnings', market_warnings)
    result['meta']['warnings'] = list(dict.fromkeys(market_warnings + [
        w for w in previous['meta'].get('warnings', []) if w not in old_market_warnings]))
    result['meta']['refresh_daily_warnings'] = market_warnings
    rows = []
    for incoming in daily['companies']:
        row = copy.deepcopy(old[incoming['code']])
        for key in ('name', 'market', 'security_type', 'analysis_profile', 'industry'):
            if row.get(key) != incoming.get(key):
                raise ValueError('종목 식별·분류 설정 변경 확인 필요: ' + incoming['code'])
        for key in MARKET_METRICS:
            row['metrics'][key] = incoming['metrics'].get(key)
            row.setdefault('metric_missing_reasons', {}).pop(key, None)
            if incoming['metrics'].get(key) is None and key in incoming.get('metric_missing_reasons', {}):
                row['metric_missing_reasons'][key] = incoming['metric_missing_reasons'][key]
        # Keep earlier observations when a new export contains a shorter rolling window.
        # Overlapping dates are replaced once by the newly validated observation.
        if 'prices' in incoming:
            bars = {b['date']: b for b in row.get('prices', [])}
            bars.update({b['date']: b for b in incoming['prices']})
            row['prices'] = [bars[d] for d in sorted(bars)]
        for key in ('flows', 'price_venue', 'analysis_venue', 'user_policy_evidence'):
            row.pop(key, None)
            if key in incoming:
                row[key] = incoming[key]
        # Earlier bars remain in the cache, so keep their original source evidence.
        sources = incoming['sources'] + row.get('sources', [])
        row['sources'] = list({digest(s): s for s in sources}.values())
        row['data_quality'] = list(dict.fromkeys(market_warnings + [
            w for w in row.get('data_quality', []) if w not in old_market_warnings]))
        rows.append(row)
    result['companies'] = rows
    return validate_snapshot(result)


def refresh(root, *, provider=None):
    root = Path(root).resolve()
    local = local_config.load_local(root)
    profile = require_profile(local)
    if 'infomax_manual' not in local['enabled_data_adapters']:
        raise ValueError('이 PC의 인포맥스 저장 파일 경로를 먼저 설정하세요')
    provider = provider or provider_for(root, local, convert)
    store = Store(local['data_dir'], profile, 'user_input')
    lock = store.path.parent / 'refresh.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError('갱신이 실행 중입니다. 잠시 후 다시 시도하세요. 계속되면 남은 잠금을 확인하세요') from None
    os.close(fd)
    prior = {}
    receipt = dict(last_attempt_at=now())
    promoted = False
    try:
        prior = store.setting(STATUS_KEY, {})
        receipt = dict(prior, last_attempt_at=receipt['last_attempt_at'])
        daily, identity, source_name = provider.fetch()
        previous = store.latest()
        if previous and daily['meta']['price_date'] < previous['meta']['price_date']:
            raise ValueError('기존 자료보다 과거인 파일입니다: price_date')
        validate_snapshot(daily)
        for row in daily['companies']:
            for metric in ('price', 'market_cap_eok'):
                value = row['metrics'].get(metric)
                if value is not None and value <= 0:
                    raise ValueError('가격/시가총액은 양수여야 합니다')
        if daily['meta']['data_mode'] != 'user_input':
            raise ValueError('실제 저장자료만 갱신할 수 있습니다')
        from tools.infomax_import import day
        as_of = day(daily['meta']['as_of'], '조회일')
        if daily['meta']['price_date'] > as_of:
            raise ValueError('가격일이 조회일보다 미래입니다')
        if as_of > datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat():
            raise ValueError('저장 파일의 조회 종료일이 미래입니다')
        if previous is None:
            manual = local.get('manual_snapshot_file')
            if manual is not None and manual.is_file():
                previous = json.loads(manual.read_text(encoding='utf-8-sig'))
            else:
                previous = daily
        fingerprint = digest(identity)
        previous_id = digest(previous)
        input_unchanged = fingerprint == prior.get('input_hash') and previous_id == prior.get('snapshot_id')
        candidate = previous if input_unchanged else merge_daily(previous, daily)
        trend_error = None
        trend_source = candidate['meta'].get('trend_source', {})
        if trend_source.get('provider') == 'Yahoo Finance' and trend_source.get('cutoff') != candidate['meta']['price_date']:
            try:
                from tools.trend_history import build, fetch_charts
                source_dir = store.path.parent / 'trend-source' / candidate['meta']['price_date']
                candidate = build(candidate, fetch_charts(source_dir))
            except Exception as exc:
                trend_error = '추세 시세 재조회 실패: ' + str(exc)
        unchanged = input_unchanged and digest(candidate) == previous_id and store.latest() is not None
        sid = digest(candidate)
        receipt.update(input_hash=fingerprint, snapshot_id=sid,
                       source_file=source_name, as_of=candidate['meta']['as_of'],
                       price_date=candidate['meta']['price_date'],
                       financial_period=candidate['meta']['financial_period'],
                       companies=len(candidate['companies']), status='processing', errors=[])
        if not unchanged:
            archive = store.path.parent / 'refresh-snapshots' / (sid + '.json')
            archive.parent.mkdir(parents=True, exist_ok=True)
            if not archive.exists():
                temp = archive.with_suffix('.tmp')
                temp.write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding='utf-8')
                temp.replace(archive)
            # Snapshot and receipt commit together; SQLite is the app's authoritative store.
            with store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                current = db.execute("SELECT payload FROM snapshots WHERE status='complete' ORDER BY created DESC LIMIT 1").fetchone()
                if current and digest(json.loads(current[0])) != digest(previous):
                    raise ValueError('갱신 중 저장자료가 변경되었습니다. 다시 시도하세요')
                db.execute('INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?)',
                           (sid, datetime.now(timezone.utc).isoformat(), 'complete',
                            json.dumps(candidate, ensure_ascii=False)))
                receipt['last_data_saved_at'] = now()
                db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',
                           (STATUS_KEY, json.dumps(receipt, ensure_ascii=False)))
        promoted = True
        from batch import run
        errors = [trend_error] if trend_error else []
        for frequency in ('daily', 'weekly'):
            try:
                result = run(profile, 'user_input', frequency, root=root)
                if result['snapshot_id'] != sid:
                    raise ValueError('저장자료가 다시 변경되어 목록 기준이 다릅니다')
            except Exception as exc:
                errors.append(f'{frequency}: {exc}')
        receipt['errors'] = errors
        receipt['status'] = 'partial' if errors else 'unchanged' if unchanged else 'complete'
        if not errors:
            receipt['last_success_at'] = now()
        store.save_setting(STATUS_KEY, receipt)
        return dict(receipt=receipt, snapshot=candidate)
    except Exception as exc:
        failed = dict(receipt if promoted else prior, status='failed',
                      last_attempt_at=receipt['last_attempt_at'], errors=['갱신 실패 · ' + type(exc).__name__])
        store.save_setting(STATUS_KEY, failed)
        raise
    finally:
        lock.unlink(missing_ok=True)
