"""Thesis v2: failure scenarios and invalidation conditions checked against stored data. Never changes an opinion."""
import json
from calendar import monthrange
from datetime import date
from pathlib import Path

from .core import num

TRIGGERED, CLEAR, INSUFFICIENT, MANUAL = 'triggered', 'clear', 'insufficient', 'manual'
METRICS = {
    'revenue_yoy_pct': '단독분기 매출 전년 동기 대비 (%)',
    'revenue_yoy_negative_streak': '매출 전년 동기 대비 감소 연속 분기 수',
    'operating_margin_change_pp': '영업이익률 전년 동기 대비 변화 (%p)',
    'ocf_ttm': 'TTM 영업현금흐름',
    'ocf_to_profit_ttm': 'TTM 영업현금흐름 / TTM 순이익',
    'debt_ratio_pct': '부채비율 (%)',
    'below_ma200': '완료 종가 200일선 아래',
    'rs_1m': '1개월 RS 점수',
}
OPS = {'<': lambda a, b: a < b, '<=': lambda a, b: a <= b, '>': lambda a, b: a > b, '>=': lambda a, b: a >= b, '==': lambda a, b: a == b}
PRICE_METRICS = {'below_ma200', 'rs_1m'}


def _year_ago(end):
    d = date.fromisoformat(end)
    return date(d.year - 1, d.month, monthrange(d.year - 1, d.month)[1]).isoformat()


def _quarters(table):
    groups = (table or {}).get('groups', [])
    for basis in ('CFS', 'OFS'):
        cols = next((g['columns'] for g in groups if g.get('basis') == basis and g.get('cadence') == 'quarter'), None)
        if cols:
            return basis, sorted(cols, key=lambda c: c['period_end'])
    return None, []


def _prior(cols, c):
    return next((p for p in cols if p['period_end'] == _year_ago(c['period_end'])), None)


def _yoy(cols, c, key):
    now, then = c['statement_values'].get(key), ((_prior(cols, c) or {}).get('statement_values') or {}).get(key)
    return (now / then - 1) * 100 if num(now) and num(then) and then > 0 else None


def _margin(c):
    v = (c or {}).get('statement_values') or {}
    return v['operating_profit'] / v['revenue'] * 100 if num(v.get('operating_profit')) and num(v.get('revenue')) and v['revenue'] > 0 else None


def _financial(cols, m):
    latest = cols[-1]
    m['revenue_yoy_pct'] = _yoy(cols, latest, 'revenue')
    streak = 0
    for c in reversed(cols):
        growth = _yoy(cols, c, 'revenue')
        if growth is None or growth >= 0:
            break
        streak += 1
    m['revenue_yoy_negative_streak'] = streak if m['revenue_yoy_pct'] is not None else None
    now, then = _margin(latest), _margin(_prior(cols, latest))
    m['operating_margin_change_pp'] = now - then if num(now) and num(then) else None
    four = cols[-4:]
    ocf = [c['statement_values'].get('ocf') for c in four]
    net = [c['statement_values'].get('net_income') for c in four]
    if len(four) == 4 and all(num(x) for x in ocf):
        m['ocf_ttm'] = sum(ocf)
        if all(num(x) for x in net) and sum(net) > 0:
            m['ocf_to_profit_ttm'] = sum(ocf) / sum(net)
    v = latest['statement_values']
    if num(v.get('liabilities')) and num(v.get('equity')) and v['equity'] > 0:
        m['debt_ratio_pct'] = v['liabilities'] / v['equity'] * 100


def observe(table, technical):
    """Metrics available from stored quarters and completed prices. Missing inputs stay None."""
    basis, cols = _quarters(table)
    m = dict.fromkeys(METRICS)
    if cols:
        _financial(cols, m)
    t = technical or {}
    close, ma200 = t.get('close'), (t.get('sma') or {}).get('200')
    if num(close) and num(ma200):
        m['below_ma200'] = close < ma200
    rs = ((t.get('short_rs') or {}).get('1m') or {}).get('score')
    m['rs_1m'] = rs if num(rs) else None
    return dict(basis=basis, period=cols[-1]['period_end'] if cols else None, price_date=t.get('as_of'), metrics=m)


def validate_thesis(entry):
    """Schema v2 contract: exactly three scenarios, each linked to declared conditions."""
    scenarios, conditions = entry.get('scenarios'), entry.get('invalidation')
    if not isinstance(scenarios, list) or len(scenarios) != 3:
        raise ValueError('실패 시나리오 3개 필요')
    if not isinstance(conditions, list) or not conditions:
        raise ValueError('투자 논리 붕괴 조건 필요')
    ids = set()
    for c in conditions:
        if not isinstance(c, dict) or not c.get('id') or c['id'] in ids or not c.get('label') or c.get('kind') not in ('auto', 'manual'):
            raise ValueError('붕괴 조건 형식 확인 필요')
        if c['kind'] == 'auto' and (c.get('metric') not in METRICS or c.get('op') not in OPS or 'value' not in c):
            raise ValueError('자동 점검 조건 확인 필요: ' + str(c.get('id')))
        ids.add(c['id'])
    for s in scenarios:
        if not isinstance(s, dict) or not s.get('title') or not s.get('description') or not s.get('conditions') or not set(s['conditions']) <= ids:
            raise ValueError('실패 시나리오 형식 확인 필요')
    return entry


def _condition(c, o):
    if c['kind'] == 'manual':
        return dict(id=c['id'], label=c['label'], status=MANUAL, observed=None, basis='수동 확인 필요')
    value = o['metrics'].get(c['metric'])
    status = INSUFFICIENT if value is None else TRIGGERED if OPS[c['op']](value, c['value']) else CLEAR
    basis = f"종가 {o['price_date']}" if c['metric'] in PRICE_METRICS else f"재무 {o['period']} {o['basis']}"
    return dict(id=c['id'], label=c['label'], status=status, observed=value, metric=METRICS[c['metric']],
                basis=basis if value is not None else '자료 부족')


def evaluate(entry, table, technical):
    """Check each condition; roll scenarios up. The result is advice for review, not an opinion change."""
    o = observe(table, technical)
    results = [_condition(c, o) for c in entry['invalidation']]
    by_id = {r['id']: r for r in results}
    scenarios = []
    for s in entry['scenarios']:
        linked = [by_id[i] for i in s['conditions']]
        auto = [r for r in linked if r['status'] != MANUAL]
        status = ('warning' if any(r['status'] == TRIGGERED for r in linked)
                  else 'insufficient' if auto and all(r['status'] == INSUFFICIENT for r in auto) else 'watch')
        scenarios.append(dict(title=s['title'], description=s['description'], status=status, conditions=s['conditions']))
    auto = [r for r in results if r['status'] != MANUAL]
    action = ('재검토 권고' if any(r['status'] == TRIGGERED for r in results)
              else '자료 부족' if auto and all(r['status'] == INSUFFICIENT for r in auto) else '유지 점검')
    return dict(action=action, conditions=results, scenarios=scenarios, observation=o, status=entry.get('status', 'draft'),
                drafted_by=entry.get('drafted_by'),
                note='저장된 재무·완료 종가로 조건만 점검합니다. 판단을 자동으로 바꾸지 않습니다. 수동 조건은 직접 확인하세요.')


def load_theses(root=None):
    """Valid v2 entries only; v1 fields keep working through the existing business review."""
    path = Path(root or Path(__file__).resolve().parents[1]) / 'config' / 'business_theses.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    if data.get('schema') != 2:
        return {}
    valid = {}
    for code, entry in (data.get('companies') or {}).items():
        try:
            valid[code] = validate_thesis(entry)
        except ValueError:
            continue
    return valid
