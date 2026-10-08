"""Thesis v2.1: Lynch stock type + adopted master guidelines with type-adjusted thresholds.

Checks stored quarterly/annual financials and completed prices only. Never changes an opinion.
"""
import json
from calendar import monthrange
from datetime import date
from pathlib import Path

from .core import num

TRIGGERED, CLEAR, INSUFFICIENT, MANUAL = 'triggered', 'clear', 'insufficient', 'manual'
_CONFIG = json.loads((Path(__file__).resolve().parents[1] / 'config' / 'guideline_thresholds.json').read_text(encoding='utf-8'))
ADOPTED = {int(k): v for k, v in _CONFIG['adopted'].items()}
TYPES = dict(_CONFIG['types'])
THRESHOLDS = _CONFIG['thresholds']
# metric -> (label, guideline number)
METRICS = {
    'trend_template_failed': ('트렌드 템플릿 이동평균 조건 실패 수', 1),
    'range_failed': ('52주 범위 조건 실패 수', 2),
    'rs_score': ('자체 RS 점수', 3),
    'market_uptrend': ('소속 시장 지수 상승 정렬', 4),
    'breakout_failed': ('돌파 후 되밀림', 6),
    'op_profit_yoy_pct': ('분기 영업이익 전년 동기 대비 (%)', 7),
    'net_income_yoy_pct': ('분기 순이익 전년 동기 대비 (%) · 참고', 7),
    'op_profit_accel_pp': ('영업이익 증가율 변화 (%p, 직전 분기 대비)', 8),
    'annual_op_profit_cagr_3y_pct': ('연간 영업이익 3년 연평균 (%)', 9),
    'revenue_yoy_pct': ('분기 매출 전년 동기 대비 (%)', 10),
    'operating_margin_change_pp': ('영업이익률 전년 동기 대비 (%p)', 11),
    'gross_margin_change_pp': ('매출총이익률 전년 동기 대비 (%p)', 11),
    'operating_margin_drop_from_peak_pp': ('영업이익률 저장 분기 최고치 대비 (%p)', 11),
}
# net_income_yoy_pct is displayed for reference only (no stored EPS per quarter); it has no threshold.
REFERENCE_ONLY = {'net_income_yoy_pct'}
OPS = {'<': lambda a, b: a < b, '<=': lambda a, b: a <= b, '>': lambda a, b: a > b, '>=': lambda a, b: a >= b, '==': lambda a, b: a == b}
MA_CHECKS = ('price_long', 'long_stack', 'long_rising', 'short_stack', 'price50')
RANGE_CHECKS = ('above_low', 'near_high')
PEAK_WINDOW = 6


def threshold(metric, kind):
    """(operator, value) for a stock type, or None when the guideline does not apply to that type."""
    spec = THRESHOLDS.get(metric)
    if not spec:
        return None
    values = spec['values']
    if kind in values:
        return spec['op'], values[kind]
    if '*' in values:
        return spec['op'], values['*']
    return None


def guard(metric):
    """(guard metric, operator, value): the check only applies while the guard holds, else it is clear."""
    when = (THRESHOLDS.get(metric) or {}).get('when')
    return (when['metric'], when['op'], when['value']) if when else None


def _year_ago(end):
    d = date.fromisoformat(end)
    return date(d.year - 1, d.month, monthrange(d.year - 1, d.month)[1]).isoformat()


def _group(table, cadence):
    for basis in ('CFS', 'OFS'):
        cols = next((g['columns'] for g in (table or {}).get('groups', []) if g.get('basis') == basis and g.get('cadence') == cadence), None)
        if cols:
            return basis, sorted(cols, key=lambda c: c['period_end'])
    return None, []


def _prior(cols, c):
    return next((p for p in cols if p['period_end'] == _year_ago(c['period_end'])), None)


def _value(c, key):
    return ((c or {}).get('statement_values') or {}).get(key)


def _yoy(cols, c, key, turnaround=False):
    now, then = _value(c, key), _value(_prior(cols, c), key)
    if not (num(now) and num(then)):
        return None
    if then > 0:
        return (now / then - 1) * 100
    # Loss a year ago, profit now: growth starts from 0 (user rule). A continuing loss has no growth rate.
    return 0.0 if turnaround and now > 0 else None


def _margin(c, key='operating_profit'):
    value, revenue = _value(c, key), _value(c, 'revenue')
    return value / revenue * 100 if num(value) and num(revenue) and revenue > 0 else None


def _financial(cols, m):
    latest = cols[-1]
    m['revenue_yoy_pct'] = _yoy(cols, latest, 'revenue')
    m['op_profit_yoy_pct'] = _yoy(cols, latest, 'operating_profit', True)
    m['net_income_yoy_pct'] = _yoy(cols, latest, 'net_income', True)
    earlier = [c for c in cols if c['period_end'] < latest['period_end']]
    before = _yoy(cols, earlier[-1], 'operating_profit', True) if earlier else None
    m['op_profit_accel_pp'] = m['op_profit_yoy_pct'] - before if num(m['op_profit_yoy_pct']) and num(before) else None
    now, then = _margin(latest), _margin(_prior(cols, latest))
    m['operating_margin_change_pp'] = now - then if num(now) and num(then) else None
    now, then = _margin(latest, 'gross_profit'), _margin(_prior(cols, latest), 'gross_profit')
    m['gross_margin_change_pp'] = now - then if num(now) and num(then) else None
    recent = [_margin(c) for c in cols[-PEAK_WINDOW:]]
    if len(recent) >= 4 and all(num(x) for x in recent):
        m['operating_margin_drop_from_peak_pp'] = recent[-1] - max(recent)


def _annual(cols, m):
    if len(cols) < 4:
        return
    first, last = _value(cols[-4], 'operating_profit'), _value(cols[-1], 'operating_profit')
    if num(first) and num(last) and first > 0 and last > 0:
        m['annual_op_profit_cagr_3y_pct'] = ((last / first) ** (1 / 3) - 1) * 100


def _trend(trend, regime, m):
    analysis = (trend or {}).get('analysis') or {}
    checks = {c['id']: c for c in analysis.get('checks', []) if isinstance(c, dict)}
    for key, ids in (('trend_template_failed', MA_CHECKS), ('range_failed', RANGE_CHECKS)):
        found = [checks.get(i, {}).get('status') for i in ids]
        if all(s in ('pass', 'fail') for s in found):
            m[key] = found.count('fail')
    rs = (trend or {}).get('rs')
    m['rs_score'] = rs if num(rs) else None
    if analysis and not analysis.get('blocked') and analysis.get('phase'):
        m['breakout_failed'] = analysis['phase'] == '돌파 후 되밀림'
    if regime in ('상승 정렬', '하락 정렬') or (isinstance(regime, str) and regime.startswith('혼조')):
        m['market_uptrend'] = regime == '상승 정렬'


def observe(table, technical, trend=None, market_regime=None):
    """Metrics available from stored quarters/years and completed prices. Missing inputs stay None."""
    basis, quarters = _group(table, 'quarter')
    _, annual = _group(table, 'annual')
    m = dict.fromkeys(METRICS)
    if quarters:
        _financial(quarters, m)
    _annual(annual, m)
    _trend(trend, market_regime, m)
    analysis = (trend or {}).get('analysis') or {}
    latest = quarters[-1] if quarters else None
    prior_op = _value(_prior(quarters, latest), 'operating_profit') if latest else None
    turnaround = bool(latest and num(prior_op) and prior_op <= 0 and num(_value(latest, 'operating_profit')) and _value(latest, 'operating_profit') > 0)
    return dict(basis=basis, period=latest['period_end'] if latest else None, price_date=(technical or {}).get('as_of'), metrics=m, turnaround=turnaround,
                trend_phase=analysis.get('phase'), volume_multiple=analysis.get('volume_multiple'), contraction=analysis.get('contraction'))


def validate_thesis(entry):
    """Schema v2.1: Lynch type, exactly three scenarios, typed thresholds for every automatic condition."""
    kind = entry.get('type')
    if kind not in TYPES:
        raise ValueError('종목 유형 확인 필요')
    status = entry.get('status', 'draft')
    if status not in ('draft', 'confirmed') or (status == 'confirmed' and not entry.get('confirmed_on')):
        raise ValueError('초안·확정 상태와 확정일 확인 필요')
    scenarios, conditions = entry.get('scenarios'), entry.get('invalidation')
    if not isinstance(scenarios, list) or len(scenarios) != 3:
        raise ValueError('실패 시나리오 3개 필요')
    if not isinstance(conditions, list) or not conditions:
        raise ValueError('투자 논리 붕괴 조건 필요')
    ids, context = set(), set()
    for c in conditions:
        if not isinstance(c, dict) or not c.get('id') or c['id'] in ids or c.get('kind') not in ('auto', 'manual'):
            raise ValueError('붕괴 조건 형식 확인 필요')
        if c['kind'] == 'manual' and not c.get('label'):
            raise ValueError('수동 조건 설명 필요: ' + str(c['id']))
        if c['kind'] == 'auto':
            metric = c.get('metric')
            if metric not in METRICS or metric in REFERENCE_ONLY or metric not in THRESHOLDS:
                raise ValueError('자동 점검 지표 확인 필요: ' + str(c['id']))
            if threshold(metric, kind) is None:
                raise ValueError(f'{TYPES[kind]} 유형에는 {METRICS[metric][0]} 기준이 없습니다: ' + str(c['id']))
            if THRESHOLDS[metric].get('role') == 'context':
                context.add(c['id'])
        ids.add(c['id'])
    for s in scenarios:
        if not isinstance(s, dict) or not s.get('title') or not s.get('description') or not s.get('conditions'):
            raise ValueError('실패 시나리오 형식 확인 필요')
        if not set(s['conditions']) <= ids or set(s['conditions']) & context:
            raise ValueError('시나리오 조건 연결 확인 필요')
    return entry


def _text(spec, value):
    return spec['text'].format(value=value)


def _condition(c, kind, o):
    if c['kind'] == 'manual':
        return dict(id=c['id'], label=c['label'], text=c['label'], guideline=None, role='invalidation', status=MANUAL, observed=None, basis='수동 확인 필요')
    spec = THRESHOLDS[c['metric']]
    op, limit = threshold(c['metric'], kind)
    value = o['metrics'].get(c['metric'])
    status = INSUFFICIENT if value is None else TRIGGERED if OPS[op](value, limit) else CLEAR
    note = ''
    g = guard(c['metric'])
    if g and value is not None:
        gv = o['metrics'].get(g[0])
        if gv is None:
            status = INSUFFICIENT
        elif not OPS[g[1]](gv, g[2]):
            status, note = CLEAR, ' · 현재 증가율이 높아 둔화를 경고하지 않음'
    if o.get('turnaround') and c['metric'] in ('op_profit_yoy_pct', 'net_income_yoy_pct', 'op_profit_accel_pp'):
        note += ' · 전년 동기 적자→흑자 턴어라운드: 성장률 0에서 시작으로 계산'
    price_based = METRICS[c['metric']][1] in (1, 2, 3, 4, 6)
    basis = f"종가 {o['price_date']}" if price_based else f"재무 {o['period']} {o['basis']}"
    return dict(id=c['id'], label=METRICS[c['metric']][0], text=_text(spec, limit), guideline=METRICS[c['metric']][1],
                role=spec.get('role', 'invalidation'), status=status, observed=value, basis=(basis + note) if value is not None else '자료 부족')


def evaluate(entry, table, technical, trend=None, market_regime=None):
    """Check each condition and roll scenarios up. Advice for review only, never an opinion change."""
    kind = entry['type']
    o = observe(table, technical, trend, market_regime)
    results = [_condition(c, kind, o) for c in entry['invalidation']]
    by_id = {r['id']: r for r in results}
    scenarios = []
    for s in entry['scenarios']:
        linked = [by_id[i] for i in s['conditions']]
        auto = [r for r in linked if r['status'] != MANUAL]
        status = ('warning' if any(r['status'] == TRIGGERED for r in linked)
                  else 'insufficient' if auto and all(r['status'] == INSUFFICIENT for r in auto) else 'watch')
        scenarios.append(dict(title=s['title'], description=s['description'], status=status, conditions=s['conditions']))
    counted = [r for r in results if r['status'] != MANUAL and r['role'] != 'context']
    action = ('재검토 권고' if any(r['status'] == TRIGGERED for r in counted)
              else '자료 부족' if counted and all(r['status'] == INSUFFICIENT for r in counted) else '유지 점검')
    return dict(action=action, type=kind, type_label=TYPES[kind], conditions=results, scenarios=scenarios, observation=o,
                status=entry.get('status', 'draft'), confirmed_on=entry.get('confirmed_on'), drafted_by=entry.get('drafted_by'),
                note='저장된 재무·완료 종가로 조건만 점검합니다. 판단을 자동으로 바꾸지 않습니다. 수동 조건은 직접 확인하세요. 시장 환경은 참고용입니다.')


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
