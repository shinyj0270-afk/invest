"""Explicit user policies; preserve source observations and verification status."""
from infomax_import import require


def apply_analysis_basis(snapshot, decisions):
    """Apply the user's analysis basis without certifying the saved source's venue."""
    venue = decisions.get('unknown_venue', {})
    if venue.get('analysis_venue') != 'KRX' or venue.get('venue_basis') != 'user_declared':
        return snapshot
    require(decisions.get('revision_finality', {}).get('decision') == 'allow_provisional_use_with_label',
            '잠정값 사용 결정 필요')
    require(decisions.get('observed_sessions_calendar', {}).get('decision') == 'use_latest_20_common_observed_dates_with_label',
            '관측일 사용 결정 필요')
    labels = [decisions[k]['required_label'] for k in
              ('unknown_venue', 'revision_finality', 'observed_sessions_calendar')]
    replacements = {
        '가격·수급 거래소 범위 동일성 미확인': decisions['flow_turnover_scope_comparability']['required_label'],
        '거래소 범위 동일성 미확인': decisions['flow_turnover_scope_comparability']['required_label'],
        '거래소 범위 미확인': labels[0],
        '추후 정정 가능': labels[1],
        '공식 거래일 미대조': labels[2],
    }
    def revised(notes):
        return list(dict.fromkeys(replacements.get(note, note) for note in notes))
    meta = snapshot['meta']
    meta['analysis_venue'] = 'KRX'
    meta['venue'] = 'KRX · 사용자 지정 기준'
    meta['market_data_policy'] = dict(venue='KRX', venue_basis='user_declared',
        provisional_values_accepted=True, window_basis='latest_20_common_observations',
        official_calendar_required=False, official_calendar_verified=False,
        source_venue_independently_verified=False, user_answer=venue['user_answer'])
    meta['warnings'] = revised(meta.get('warnings', []))
    for label in labels:
        if label not in meta['warnings']: meta['warnings'].append(label)
    for row in snapshot['companies']:
        row['analysis_venue'] = 'KRX'
        row['data_quality'] = revised(row.get('data_quality', []))
        evidence = row.get('user_policy_evidence')
        if evidence:
            evidence['analysis_venue'] = 'KRX'
            evidence['venue_basis'] = 'user_declared'
            evidence['official_calendar_required'] = False
            evidence['labels'] = revised(evidence.get('labels', []))
    return snapshot


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
