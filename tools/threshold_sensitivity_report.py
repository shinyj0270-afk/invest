"""S10: read-only threshold sensitivity of the recommendation draft filters (Q06 follow-up, Q09 result).

Varies one filter at a time around the current rule (RS>=70, 1M RS>=50, revenue YoY>=10, debt ratio<=200, close>SMA200,
price trend pass) and reports how many companies pass and how the pass set changes versus the current rule. Aggregates
only, no company codes. Every variant is a trial: with `--root` all non-baseline variants are appended to the hash-chained
trial log (`.local/trial-log/<profile>.jsonl`) BEFORE they are evaluated, each as rejected ("diagnostic, not adopted").
The report never ranks variants and nothing here adopts a threshold. A pass count is not a performance measure.
Reads the saved snapshot and caches like `recommendation_score_report` (SQLite mode=ro, no refresh, before/after manifest).
"""
import argparse
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0, str(ROOT))
from investment.core import num
from investment.trial_log import record, summary
from tools.recommendation_score_report import candidate_table, synthetic_context, build_real_context, manifest

BASE = dict(rs_min=70, short_min=50, growth_min=10, debt_max=200, use_sma=True, use_trend_status=True)
GRID = dict(rs_min=(60, 65, 75, 80), short_min=(40, 60), growth_min=(5, 15, 20), debt_max=(150, 250))
REACHED = ('trend_failed', 'growth_or_financial_failed', 'passed')
RULE_VERSION = 'recommendations.propose filters rs70/short50/growth10/debt200 + sma200 + trend pass'
REASON = '민감도 진단용 변형이며 채택 대상이 아님(S10: 가장 좋은 값을 고르지 않는다)'


def feature_rows(context, created_on):
    """Raw filter inputs for the companies that reach the trend check in `propose` (same gating, same order)."""
    stage = {r['code']: r['stage'] for r in candidate_table(context, created_on)}
    out = []
    for r in context['snapshot']['companies']:
        if stage[r['code']] not in REACHED:continue
        t = context['research']['rows'][r['code']]['technical'];f = r['common_financial'];m = f['metrics']
        out.append(dict(code=r['code'], rs=t.get('price_strength', {}).get('score'), short=t.get('short_rs', {}).get('1m', {}).get('score'),
            close=t.get('close'), sma200=t.get('sma', {}).get('200'), status=t.get('price_trend_status'),
            growth=m['revenue_growth_pct'], margin=m['operating_margin_pct'], roe=m['roe_pct'], debt=m['debt_ratio_pct'], ocf=f.get('ttm_ocf')))
    return out


def conditions(row, p):
    """Each filter sub-condition as pass/fail. Comparisons are not judged when their input is missing (that is `trend_data`)."""
    need = [row['rs'], row['short']] + ([row['close'], row['sma200']] if p['use_sma'] else [])
    data = all(num(x) for x in need)
    return dict(trend_data=data,
        rs=not data or row['rs'] >= p['rs_min'], short=not data or row['short'] >= p['short_min'],
        sma=not data or not p['use_sma'] or row['close'] > row['sma200'], status=not p['use_trend_status'] or row['status'] == 'pass',
        growth=row['growth'] >= p['growth_min'], margin=row['margin'] > 0, roe=row['roe'] > 0, debt=row['debt'] <= p['debt_max'],
        ocf=num(row['ocf']) and row['ocf'] > 0)


def passed_codes(rows, p):
    return {r['code'] for r in rows if all(conditions(r, p).values())}


def variants():
    out = [dict(BASE)]
    out += [{**BASE, key: value} for key, values in GRID.items() for value in values]
    return out + [{**BASE, 'use_sma': False}, {**BASE, 'use_trend_status': False}]


def label(p):
    diff = [f'{k}={p[k]}' for k in BASE if p[k] != BASE[k]]
    return ', '.join(diff) if diff else '현재 규칙'


def trial_entries(vs, experiment_id):
    return [dict(experiment_id=experiment_id, rule_version=RULE_VERSION, parameter_set=dict(v), decision='rejected', discard_reason=REASON) for v in vs[1:]]


def record_trials(root, profile, vs, experiment_id):
    return [record(root, profile, entry) for entry in trial_entries(vs, experiment_id)]


def sensitivity(rows, vs):
    base = passed_codes(rows, vs[0]);out = []
    for v in vs:
        got = passed_codes(rows, v)
        out.append(dict(params=v, passed=len(got), retained=len(got & base), added=len(got - base), dropped=len(base - got)))
    return out


def blockers(rows):
    """Per sub-condition under the current rule: how many fail, and how many fail it as the only failing condition."""
    names = list(conditions(rows[0], BASE)) if rows else []
    out = {n: dict(failed=0, sole=0) for n in names}
    for r in rows:
        failing = [n for n, ok in conditions(r, BASE).items() if not ok]
        for n in failing:out[n]['failed'] += 1
        if len(failing) == 1:out[failing[0]]['sole'] += 1
    return out


def render(results, block, source, trials):
    lines = [f'# 추천 필터 임계값 민감도 진단 (읽기 전용) — {source}', '',
        '## 한 번에 한 임계값만 바꾼 결과 (현재 규칙 대비)', '', '| 변형 | 통과 | 유지 | 추가 | 탈락 |', '|---|---|---|---|---|']
    lines += [f"| {label(r['params'])} | {r['passed']} | {r['retained']} | {r['added']} | {r['dropped']} |" for r in results]
    lines += ['', '## 하위 조건별 탈락과 단독 차단 (현재 규칙)', '', '단독 차단 = 그 조건 하나만 실패한 기업 수(그 조건을 풀면 통과가 늘어나는 상한).', '',
        '| 조건 | 실패 | 단독 차단 |', '|---|---|---|']
    lines += [f"| {n} | {v['failed']} | {v['sole']} |" for n, v in block.items()]
    lines += ['', f'시도 로그: 이번 실행의 변형 {trials}개(현재 규칙 제외)를 평가 전에 기록했다. 모두 기각 상태이며 어떤 값도 채택하지 않았다. 최적 값을 고르는 용도로 쓰지 않는다.',
        '통과 수와 교체율은 후보 구성의 민감도일 뿐 수익·위험 지표가 아니다.']
    return '\n'.join(line for line in lines if line is not None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--synthetic', action='store_true', help='합성 입력만 사용(실제 자료를 읽지 않고 시도 로그도 쓰지 않음)')
    source.add_argument('--root', type=Path, help='INVESTMENT 작업 폴더(읽기 전용 + 시도 로그 기록, 사용자 승인 후)')
    parser.add_argument('--experiment-id', default='S10-threshold-sensitivity')
    args = parser.parse_args(argv)
    vs = variants();before = after = None;note = '시도 로그: 합성 실행이라 기록하지 않았다.'
    try:
        if args.synthetic:
            context, today, label_ = synthetic_context(), '2026-10-02', '합성 입력: 실제 자료를 읽지 않았다'
        else:
            from investment.local_config import load_local
            local = load_local(args.root)
            watched = [local['data_dir'] / local['profile']] + ([local['manual_snapshot_file'].parent] if local.get('manual_snapshot_file') else [])
            before = manifest(watched)
            context, today, _ = build_real_context(args.root)
            label_ = '저장 스냅샷과 시장 캐시(읽기 전용; 새로고침 미실행)'
            record_trials(args.root, local['profile'], vs, args.experiment_id)       # recorded before any variant is evaluated
            after = manifest(watched);anchor = summary(args.root, local['profile'])
            note = f"시도 로그 누적: {anchor['trials']}회, 고유 파라미터 {anchor['distinct_parameter_sets']}개, head_digest {anchor['head_digest']}"
    except (ValueError, OSError, KeyError) as exc:
        print(f'오류: {exc}', file=sys.stderr);return 2
    rows = feature_rows(context, today)
    print(render(sensitivity(rows, vs), blockers(rows), label_, len(vs) - 1))
    print('\n' + note)
    if before is not None:
        same = before == after
        print(f"\n읽기 전용 확인: 데이터 폴더 파일 {len(before)}개의 크기·수정시각(SQLite는 해시)이 실행 전후 {'동일' if same else '**달라짐**'}.")
        return 0 if same else 3
    return 0


if __name__ == '__main__':
    sys.exit(main())
