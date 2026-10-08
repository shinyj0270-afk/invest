"""Common verification of stored analysis results. Read-only: never changes source values or opinions."""
from copy import deepcopy

from .core import num
from .financial_table import valid_day

PASS, CONDITIONAL, REVIEW = 'pass', 'conditional', 'review'
LABELS = {PASS: '통과', CONDITIONAL: '조건부 통과', REVIEW: '재검토 필요'}
CAUSES = {'error': '계산 오류', 'missing': '자료 부족'}
RANK = {PASS: 0, CONDITIONAL: 1, REVIEW: 2}
# Displayed ratios are rounded; a larger gap means the stored ratio does not follow from stored amounts.
RECOMPUTE_TOLERANCE_PCT_POINT = 0.05
POSITIVE = {'HOLD', 'BUY', '보유', '보유 검토', '유지', '편입', '신규 편입'}
SCHEMA = 'investment-review-report-1'
KEY_METRICS = {'operating_margin_pct': '영업이익률', 'revenue_growth_pct': '매출 증가율', 'roe_pct': 'ROE', 'debt_ratio_pct': '부채비율', 'per': 'PER', 'pbr': 'PBR'}


def _check(cid, label, status, kind, detail):
    return dict(id=cid, label=label, status=status, kind=kind, detail=detail)


def _dates(common, technical, as_of):
    period = common.get('period')
    price_day = (technical or {}).get('as_of')
    observed = [d.get('observed_on') for d in (common.get('metric_details') or {}).values() if isinstance(d, dict) and d.get('observed_on')]
    if not valid_day(period) or not valid_day(price_day):
        return _check('source_date', '출처·기준일', REVIEW, 'missing', '재무 기간 또는 완료 종가 기준일 미확인')
    future = [d for d in [period, price_day, *observed] if valid_day(d) and d > as_of]
    if future:
        return _check('source_date', '출처·기준일', REVIEW, 'error', '기준일보다 늦은 날짜 ' + ', '.join(sorted(set(future))))
    if not (common.get('source_urls') or any(isinstance(d, dict) and d.get('source') for d in (common.get('metric_details') or {}).values())):
        return _check('source_date', '출처·기준일', CONDITIONAL, 'missing', '재무 출처 기록 없음')
    return _check('source_date', '출처·기준일', PASS, 'ok', f'재무 {period} · 종가 {price_day}')


def _recompute(common):
    a, m = common.get('amounts') or {}, common.get('metrics') or {}
    revenue, profit, stored = a.get('revenue'), a.get('operating_profit'), m.get('operating_margin_pct')
    if not (num(revenue) and revenue > 0 and num(profit) and num(stored)):
        return _check('recompute', '계산 재검산', CONDITIONAL, 'missing', '영업이익률 재검산 금액 부족')
    expected = profit / revenue * 100
    if abs(expected - stored) > RECOMPUTE_TOLERANCE_PCT_POINT:
        return _check('recompute', '계산 재검산', REVIEW, 'error', f'영업이익률 저장 {stored:.2f}% · 재계산 {expected:.2f}%')
    return _check('recompute', '계산 재검산', PASS, 'ok', f'영업이익률 {expected:.2f}% 일치')


def verify_company(row, technical, as_of):
    """Verdict for one company's stored analysis inputs; distinguishes errors from missing data."""
    common = (row or {}).get('common_financial')
    if not common:
        checks = [_check('source_date', '출처·기준일', REVIEW, 'missing', '검증된 재무 기간 자료 없음')]
    else:
        currency, basis = common.get('currency', 'KRW'), common.get('basis')
        details = common.get('metric_details') or {}
        approx = sorted(k for k, d in details.items() if isinstance(d, dict) and (d.get('status') in ('estimated', 'reference_with_tolerance') or d.get('within_tolerance')))
        comp = row.get('financial_completeness') or common.get('financial_completeness') or {}
        pending = [k for k in ('latest_stored', 'required_accounts', 'ttm', 'roe') if (comp.get(k) or {}).get('status') not in (None, 'ready')]
        if not common.get('ttm_complete') and 'ttm' not in pending:
            pending.append('ttm')
        metrics = common.get('metrics') or {}
        pending += [label for key, label in KEY_METRICS.items() if not num(metrics.get(key))]
        checks = [
            _dates(common, technical, as_of),
            _check('unit', '단위·통화', PASS if currency == 'KRW' else CONDITIONAL, 'ok' if currency == 'KRW' else 'limit',
                   '원화' if currency == 'KRW' else f'{currency} 재무 · 원화 가격배수와 직접 비교하지 않음'),
            _recompute(common),
            _check('basis', '연결·별도 구분', PASS if basis == 'CFS' else CONDITIONAL if basis == 'OFS' else REVIEW,
                   'ok' if basis == 'CFS' else 'limit' if basis == 'OFS' else 'missing',
                   {'CFS': '연결', 'OFS': '별도 기준 · 연결 미확보'}.get(basis, '회계 기준 미확인')),
            _check('approximation', '근사·허용오차 값', CONDITIONAL if approx else PASS, 'limit' if approx else 'ok',
                   ('근사·참고값 ' + ', '.join(approx)) if approx else '근사값 없음'),
            _check('completeness', '누락 데이터', CONDITIONAL if pending else PASS, 'missing' if pending else 'ok',
                   ('대기 ' + ', '.join(pending)) if pending else '필수 항목 확보'),
        ]
    worst = max(checks, key=lambda c: RANK[c['status']])['status']
    reviews = [c for c in checks if c['status'] == REVIEW]
    cause = None if worst != REVIEW else 'error' if any(c['kind'] == 'error' for c in reviews) else 'missing'
    label = LABELS[worst] + (' · ' + CAUSES[cause] if cause else '')
    return dict(status=worst, label=label, cause=cause, as_of=as_of, checks=checks)


def compact(verification):
    """Wire summary: verdict plus non-passing checks only."""
    return dict(status=verification['status'], label=verification['label'], cause=verification['cause'], as_of=verification['as_of'],
                issues=[[c['id'], c['label'], c['detail'], c['status']] for c in verification['checks'] if c['status'] != PASS])


def overclaim(opinion, verification):
    """Rule-based: a positive conclusion resting on a 'review' verdict is stronger than its evidence."""
    positive = opinion in POSITIVE
    flag = positive and verification.get('status') == REVIEW
    return dict(flag=flag, opinion=opinion,
                reason=('근거 재검토 필요 상태에서 긍정 결론' if flag else '근거 수준과 결론 일치'))


def opinion_change(previous, current):
    """Record the difference between the last stored opinion and the current one."""
    if not previous:
        return dict(kind='first', before=None, after=current.get('opinion'), on=current.get('on'), reasons=current.get('reasons', []))
    kind = 'unchanged' if previous.get('opinion') == current.get('opinion') else 'changed'
    return dict(kind=kind, before=previous.get('opinion'), after=current.get('opinion'),
                since=previous.get('on'), on=current.get('on'), reasons=current.get('reasons', []))


def review_report(items, as_of, *, mode):
    """Standard report for independent review. Holds inputs and reasoning, never instructions to edit sources."""
    out, summary = [], {PASS: 0, CONDITIONAL: 0, REVIEW: 0}
    for item in items:
        r, tech = item['row'], item.get('technical') or {}
        v = verify_company(r, tech, as_of)
        summary[v['status']] += 1
        common = r.get('common_financial') or {}
        current = dict(opinion=item.get('opinion'), on=as_of, reasons=item.get('reasons', []))
        out.append(dict(
            code=r.get('code'), name=r.get('name'), market=r.get('market'),
            data_used=dict(financial_period=common.get('period'), basis=common.get('basis'), currency=common.get('currency'),
                           price_date=tech.get('as_of'), sources=common.get('source_urls', [])),
            calculations=dict(amounts=deepcopy(common.get('amounts')), metrics=deepcopy(common.get('metrics')),
                              formula_notes={k: d.get('reason') for k, d in (common.get('metric_details') or {}).items() if isinstance(d, dict) and d.get('reason')}),
            previous=item.get('previous'), current=current, change=opinion_change(item.get('previous'), current),
            verification=v, overclaim=overclaim(item.get('opinion'), v),
            unconfirmed=[c['label'] + ': ' + c['detail'] for c in v['checks'] if c['status'] != PASS]))
    return dict(schema=SCHEMA, as_of=as_of, mode=mode, summary=summary, items=out,
                reviewer_note='독립 검토용 사본입니다. 검토자는 원본을 수정하지 않습니다. 수치 재계산·출처·기준일 대조 결과와 미확인 항목만 기록합니다.')


def report_markdown(report):
    """Readable companion of the JSON report for a reviewer."""
    s = report['summary']
    lines = [f"# 분석 검증 보고서 · {report['as_of']}", '',
             f"자료 모드 {report['mode']} · 통과 {s[PASS]} · 조건부 통과 {s[CONDITIONAL]} · 재검토 필요 {s[REVIEW]}", '',
             report['reviewer_note'], '']
    for item in report['items']:
        d, v, ch = item['data_used'], item['verification'], item['change']
        lines += [f"## {item['name']} ({item['code']}) · {v['label']}", '',
                  f"- 사용 자료: 재무 {d['financial_period'] or '미확인'} {d['basis'] or ''} {d['currency'] or ''} · 종가 {d['price_date'] or '미확인'}",
                  f"- 기존 판단: {(item['previous'] or {}).get('opinion') or '기록 없음'} → 현재 판단: {item['current']['opinion'] or '미입력'} ({ch['kind']})",
                  f"- 과도한 결론: {'예 · ' if item['overclaim']['flag'] else '아니오 · '}{item['overclaim']['reason']}"]
        lines += [f"- 계산 근거 {k}: {n}" for k, n in item['calculations']['formula_notes'].items()]
        lines += [f"- 미확인: {u}" for u in item['unconfirmed']] or ['- 미확인 항목 없음']
        lines += [f"- 출처: {u}" for u in d['sources'][:4]] + ['']
    return '\n'.join(lines)
