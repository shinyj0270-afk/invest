"""Append-only, hash-chained log of every rule/threshold experiment (Q06). Local files only; no DB, no network.

Every attempt counts as a trial, including rejected ones, so selection-bias corrections can use the real number of trials.
Editing or deleting a middle line breaks the chain. Truncating the newest lines cannot be detected from the file alone,
so keep `summary()['head_digest']` in the handoff as an external anchor.
"""
import json
import os
import time
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from .core import digest, num

PROFILES = ('work', 'home')
DECISIONS = ('pending', 'rejected', 'adopted')
HORIZONS = (63, 126, 252)
LOCK_WAIT_SECONDS = 10
REQUIRED = ('experiment_id', 'rule_version', 'parameter_set', 'decision')
OPTIONAL = ('label_horizon', 'train_period', 'validation_period', 'test_period', 'discard_reason', 'metrics_ref')


def log_path(root, profile):
    if profile not in PROFILES:raise ValueError('프로필 확인 필요')
    return Path(root)/'.local/trial-log'/f'{profile}.jsonl'


def _text(value, name, limit=200):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:raise ValueError(f'{name} 확인 필요')
    return value


def _period(value, name):
    if value is None:return None
    if not isinstance(value, (list, tuple)) or len(value) != 2:raise ValueError(f'{name}은 [시작일, 종료일]이어야 합니다')
    start, end = value
    for item in (start, end):
        if not isinstance(item, str) or date.fromisoformat(item).isoformat() != item:raise ValueError(f'{name} 날짜 형식 확인 필요')
    if start > end:raise ValueError(f'{name} 시작일이 종료일보다 늦습니다')
    return [start, end]


def _parameters(value):
    if not isinstance(value, dict) or not value:raise ValueError('parameter_set 필요')
    for key, item in value.items():
        if not isinstance(key, str) or not key or not (isinstance(item, (str, bool)) or num(item)):raise ValueError('parameter_set 값은 문자·불리언·유한 숫자만 허용')
    return dict(value)


def _clean(entry):
    if not isinstance(entry, dict):raise ValueError('시도 기록 형식 확인 필요')
    unknown = set(entry) - set(REQUIRED) - set(OPTIONAL)
    if unknown:raise ValueError('알 수 없는 필드: ' + ','.join(sorted(map(str, unknown))))
    if any(k not in entry for k in REQUIRED):raise ValueError('필수 필드 누락')
    decision = entry['decision']
    if decision not in DECISIONS:raise ValueError('decision 확인 필요')
    reason = entry.get('discard_reason')
    if decision == 'rejected' and not (isinstance(reason, str) and reason.strip()):raise ValueError('기각 사유 필요')
    horizon = entry.get('label_horizon')
    if horizon is not None and horizon not in HORIZONS:raise ValueError('label_horizon 확인 필요')
    return dict(experiment_id=_text(entry['experiment_id'], 'experiment_id', 100), rule_version=_text(entry['rule_version'], 'rule_version', 100),
        parameter_set=_parameters(entry['parameter_set']), label_horizon=horizon,
        train_period=_period(entry.get('train_period'), 'train_period'), validation_period=_period(entry.get('validation_period'), 'validation_period'),
        test_period=_period(entry.get('test_period'), 'test_period'), decision=decision,
        discard_reason=reason if reason is None else _text(reason, 'discard_reason', 500),
        metrics_ref=None if entry.get('metrics_ref') is None else _text(entry['metrics_ref'], 'metrics_ref', 300))


def read_all(root, profile):
    path = log_path(root, profile)
    if not path.exists():return []
    rows = []
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():continue
        try:row = json.loads(line)
        except ValueError as exc:raise ValueError(f'시도 로그 {number}번째 줄 손상') from exc
        body = {k: v for k, v in row.items() if k != 'digest'}
        previous = rows[-1]['digest'] if rows else None
        if row.get('trial_index') != len(rows) + 1 or row.get('prev_digest') != previous or row.get('digest') != digest(body):
            raise ValueError(f'시도 로그 연쇄 검증 실패(줄 {number}); 수정·삭제 의심, 보존하고 검토')
        rows.append(row)
    return rows


@contextmanager
def _exclusive(path):
    """Cross-process lock held across head read and append. A crash can leave the .lock file behind; remove it by hand after checking no writer runs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix('.lock');deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY);break
        except (FileExistsError, PermissionError):      # Windows reports a lock file that is being deleted as PermissionError
            if time.monotonic() >= deadline:raise ValueError('시도 로그 잠금 대기 초과; 쓰는 프로세스가 없는지 확인한 뒤 잠금 파일을 수동 정리')
            time.sleep(0.02)
    try:yield
    finally:
        os.close(fd);os.unlink(lock)


def record(root, profile, entry):
    clean = _clean(entry)
    path = log_path(root, profile)
    with _exclusive(path):
        rows = read_all(root, profile)
        if path.exists() and path.stat().st_size and not path.read_bytes().endswith(b'\n'):raise ValueError('시도 로그 마지막 줄이 개행으로 끝나지 않음; 보존하고 검토')
        row = dict(clean, trial_index=len(rows) + 1, created_at=datetime.now(timezone.utc).isoformat(), prev_digest=rows[-1]['digest'] if rows else None)
        row['digest'] = digest(row)
        with path.open('a', encoding='utf-8', newline='\n') as f:f.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n')
    return row


def summary(root, profile):
    rows = read_all(root, profile)
    return dict(profile=profile, trials=len(rows), distinct_parameter_sets=len({digest(r['parameter_set']) for r in rows}),
        by_decision=dict(Counter(r['decision'] for r in rows)), experiments=len({r['experiment_id'] for r in rows}),
        head_digest=rows[-1]['digest'] if rows else None)
