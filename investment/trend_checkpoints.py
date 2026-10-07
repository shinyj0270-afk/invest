"""Compact immutable observations, never reconstructed historical candidate decisions.

The caller opts in to local derived storage (.local/trend-checkpoints); no jobs,
retrieval, raw price histories, portfolio positions or orders are stored here.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from .portfolio_risk import day, numeric

SCHEMA = 1
RULE = 'observed-default-cap1000-rs70-v1'
NOTE = '작성 당시 관측 체크포인트 비교 · 백테스트·전일 재구성 아님. RS는 당시 저장 유효기업 모집단 산식이며 필터 변경으로 과거 순위를 재계산하지 않습니다.'


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def summarize(data):
    if not day(data.get('as_of')):
        raise ValueError('완료 관측일 확인 필요')
    rows = []
    seen = set()
    for r in data.get('rows', []):
        identity = [r.get('market'), r.get('code'), r.get('name')]
        if identity[0] not in ('KOSPI', 'KOSDAQ') or not all(isinstance(v, str) and v for v in identity):
            raise ValueError('체크포인트 종목 식별 확인 필요')
        if tuple(identity[:2]) in seen:
            raise ValueError('체크포인트 종목 식별 중복')
        seen.add(tuple(identity[:2]))
        t = r.get('technical') or {}; a = r.get('analysis') or {}
        ready = r.get('ready') is True and t.get('as_of') == data['as_of'] and numeric(t.get('close')) and t['close'] > 0
        cap = r.get('cap_eok') if numeric(r.get('cap_eok')) else None
        rs = r.get('rs') if numeric(r.get('rs')) else None
        qualifies = bool(ready and r.get('discovery_allowed') is not False and cap is not None and cap >= 1000 and rs is not None and rs >= 70)
        ma50 = (t.get('sma') or {}).get('50')
        gap = a.get('pivot_gap_pct')
        rows.append(dict(identity=identity, ready=bool(ready), reason=r.get('reason', ''),
            discovery_allowed=r.get('discovery_allowed') is not False,
            qualified=qualifies, cap_eok=cap, rs=rs, close=t.get('close') if ready else None,
            near=bool(ready and numeric(gap) and -3 <= gap <= 0),
            breakout=bool(ready and numeric(gap) and gap > 0),
            volume_confirmed=bool(ready and a.get('phase') == '거래량 동반 돌파'),
            ma_fail=bool(ready and numeric(ma50) and t['close'] < ma50),
            pivot_gap_pct=gap if numeric(gap) else None, phase=r.get('phase'),
            rs_eligible_count=(t.get('price_strength') or {}).get('eligible_count')))
    rows.sort(key=lambda r: r['identity'])
    for rank, r in enumerate(sorted((r for r in rows if r['qualified']), key=lambda r: (-r['rs'], r['identity'])), 1):
        r['default_rank'] = rank
    return dict(schema=SCHEMA, rule=RULE, as_of=data['as_of'], mode=data.get('mode', 'unknown'),
                source_note=data.get('source_note'), rows=rows,
                rs_definition='기존 자체 12개월 가격강도·동일 거래소 저장 유효기업 모집단; 당시 점수·분모 보존',
                note=NOTE)


def _public(row, **extra):
    market, code, name = row['identity']
    return dict(market=market, code=code, name=name, rs=row['rs'], rank=row.get('default_rank'),
                phase=row.get('phase'), **extra)


def compare_observations(current, prior=None):
    if prior and (prior.get('rule') != current['rule'] or prior.get('mode') != current['mode'] or prior['as_of'] > current['as_of']):
        prior = None
    old = {tuple(r['identity']): r for r in prior['rows']} if prior else {}
    new = {tuple(r['identity']): r for r in current['rows']}
    changes = dict(status='ready' if prior else 'no_prior', as_of=current['as_of'],
        prior_as_of=prior['as_of'] if prior else None,
        prior_observed_at=prior.get('observed_at') if prior else None,
        prior_digest=prior.get('digest') if prior else None,
        current_digest=current.get('digest'), revision=current.get('revision'),
        comparison='동일 관측일 수정본 비교' if prior and prior['as_of'] == current['as_of'] else '직전 저장 관측 비교' if prior else '이전 체크포인트 없음 · 신규/이탈 판정 대기',
        note=NOTE, new_qualified=[], dropouts=[], pending=[], near=[], breakouts=[], ma_fail=[])
    for key, r in new.items():
        p = old.get(key)
        if prior and r['qualified'] and (p is None or not p['qualified']):
            changes['new_qualified'].append(_public(r, reason='관찰 대상에 새로 포함' if p is None else '기본 조건 새 충족'))
        if prior and p and p['qualified'] and not r['qualified']:
            failed = r['ready'] and r.get('discovery_allowed', True) and ((numeric(r['cap_eok']) and r['cap_eok'] < 1000) or (numeric(r['rs']) and r['rs'] < 70))
            changes['dropouts' if failed else 'pending'].append(_public(r, reason='시총1,000억원·RS70 기본 조건 이탈' if failed else r.get('reason') or '현재 가격·RS·시총·대상 확인 대기; 조건 이탈 확정 아님'))
        for field, label in (('near', 'near'), ('breakout', 'breakouts'), ('ma_fail', 'ma_fail')):
            if r[field] and (r['qualified'] or key in old and old[key]['qualified']):
                changes[label].append(_public(r, newly_observed=None if not prior else p is None or not p[field], volume_confirmed=r['volume_confirmed']))
    if prior:
        for key, r in old.items():
            if r['qualified'] and key not in new:
                changes['pending'].append(_public(r, reason='현재 관찰 대상에서 제외; 가격조건 이탈 확정 아님'))
    return changes


def observe_trend(data, directory, observed_at=None):
    """Append one immutable summary; compare the exact previous saved observation.

    Parent should pass its already-excluded local data directory. Builders do not
    call this function. Identical reloads reuse the latest checkpoint, preserving
    its original predecessor (and thus its historical decision).
    """
    summary = summarize(data)
    mode = summary['mode']
    if mode not in ('fixture', 'manual', 'live', 'unknown', 'user_input', 'connected'):
        raise ValueError('체크포인트 자료 모드 확인 필요')
    directory = Path(directory) / mode
    directory.mkdir(parents=True, exist_ok=True)
    records = []; unreadable = 0
    for path in sorted(directory.glob('*.json')):
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
            body = {k: v for k, v in record.items() if k not in ('digest', 'revision', 'observed_at', 'previous_digest')}
            if record['schema'] != SCHEMA or record['rule'] != RULE or record['mode'] != mode or not day(record['as_of']) or record['digest'] != sha256(_encoded(body)).hexdigest():
                raise ValueError('기록 무결성 불일치')
            if not isinstance(record['revision'], int) or record['revision'] < 1 or not isinstance(record['rows'], list):
                raise ValueError('기록 형식 불일치')
            # Validate row schema before trusting a prior observation.
            for row in record['rows']:
                if len(row['identity']) != 3 or row['identity'][0] not in ('KOSPI', 'KOSDAQ') or not all(isinstance(v, str) and v for v in row['identity']):
                    raise ValueError('기록 종목 식별 불일치')
                for key in ('ready', 'qualified', 'near', 'breakout', 'ma_fail', 'volume_confirmed'):
                    if not isinstance(row[key], bool): raise ValueError('기록 판정 형식 불일치')
            if record['as_of'] <= summary['as_of']: records.append(record)
        except (ValueError, KeyError, TypeError, OSError):
            unreadable += 1
    records.sort(key=lambda r: (r['as_of'], r['revision']))
    latest = records[-1] if records else None
    digest = sha256(_encoded(summary)).hexdigest()
    if latest and latest['as_of'] == summary['as_of'] and latest['digest'] == digest:
        current = latest
        prior = next((r for r in reversed(records[:-1]) if r['digest'] == current.get('previous_digest')), None)
    else:
        prior = latest
        revision = max((r['revision'] for r in records if r['as_of'] == summary['as_of']), default=0) + 1
        current = dict(summary, digest=digest, revision=revision,
            observed_at=observed_at or datetime.now(timezone.utc).isoformat(),
            previous_digest=prior['digest'] if prior else None)
        path = directory / f"{summary['as_of']}-v{revision:04d}-{digest[:16]}.json"
        # Exclusive write prevents an observation from silently replacing a decision.
        with path.open('x', encoding='utf-8') as stream:
            json.dump(current, stream, ensure_ascii=False, sort_keys=True, allow_nan=False)
    result = compare_observations(current, prior)
    result['observed_at'] = current['observed_at']
    result['unreadable_records'] = unreadable
    return result
