"""Explicit review-only overrides; preserve unknown venue and finality facts."""
from infomax_import import require


def apply_observed_flow_policy(row, data, sessions, decisions):
    expected = {
        'unknown_venue': 'allow_use_with_label',
        'revision_finality': 'allow_provisional_use_with_label',
        'investor_aggregation': 'use_existing_provider_fields_with_label',
        'observed_sessions_calendar': 'use_latest_20_common_observed_dates_with_label',
    }
    if not all(decisions.get(k, {}).get('decision') == v for k, v in expected.items()):
        return
    code = row['code']
    common = sorted(set(data['prices'][code]) & set(data['flows'][code]))
    require(len(sessions) == 20 and sessions == common[-20:], 'Expected latest 20 common observed dates')
    values = [data['prices'][code][d]['누적거래대금'] for d in sessions]
    metrics = row['metrics']
    released = []
    total_turnover = sum(values) if all(v is not None for v in values) else None
    ratio_policy = decisions.get('flow_turnover_scope_comparability', {})
    allow_ratio = ratio_policy.get('decision') == 'allow_provisional_ratio_with_label'
    if all(v is not None for v in values):
        metrics['avg_trading_value_20d_eok'] = sum(values) / 20 / 1e8
        released.append('avg_trading_value_20d_eok')
    for prefix, field in [('foreign', '외국인순매수금액'), ('institution', '기관순매수금액')]:
        flows = [data['flows'][code][d][field] for d in sessions]
        if all(v is not None for v in flows):
            key = prefix + '_net_20d_eok'
            metrics[key] = sum(flows) * 1000 / 1e8
            released.append(key)
        key = prefix + '_net_turnover_20d_pct'
        metrics[key] = None
        row['metric_missing_reasons'][key] = '가격·수급의 거래소 범위 동일성 미확인: 수급/거래대금 비율 사용 결정 대기'
        if allow_ratio:
            if total_turnover is not None and total_turnover > 0 and all(v is not None for v in flows):
                metrics[key] = sum(flows) * 1000 / total_turnover * 100
                released.append(key)
            else:
                row['metric_missing_reasons'][key] = '동일 20개 관측일의 완전한 수급 값과 양수 거래대금 합계 필요'
    for key in released:
        row['metric_missing_reasons'].pop(key, None)
    row['user_policy_evidence'] = dict(
        status='provisional_user_accepted', sessions=sessions, released_metrics=released,
        official_calendar_verified=False, price_venue=None, flow_venue=None,
        prices_final=False, flows_final=False, venue_comparability_confirmed=False,
        labels=[decisions[k]['required_label'] for k in expected] +
               ([ratio_policy['required_label']] if allow_ratio else []))
