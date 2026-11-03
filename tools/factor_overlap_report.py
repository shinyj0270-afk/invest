"""Q09 T1: read-only diagnostics for the long-term research score S_long (Q/G/C/V/B percentiles).

Reports factor-to-factor rank correlations, top-N overlap when one factor is left out (renormalized weights), and why rows
have no score. It reads one snapshot JSON (or the synthetic fixture) and writes nothing. It does not change weights,
definitions or thresholds, and says nothing about returns. Use on real data only with the user's approval.
"""
import argparse
import json
import sys
from itertools import combinations
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0, str(ROOT))
from investment.core import percentile, num
from investment.research import CONFIG, analyze

WEIGHTS = dict(CONFIG['weights'])
FACTORS = tuple(WEIGHTS)


def _ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i]);ranks = [0.0] * len(values);i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:j += 1
        for k in range(i, j + 1):ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(x, y):
    """Rank correlation with average ranks; None if fewer than 3 pairs or either side is constant."""
    if len(x) != len(y) or len(x) < 3:return None
    rx, ry = _ranks(list(x)), _ranks(list(y))
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxx, syy = sum((a - mx) ** 2 for a in rx), sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:return None
    return sum((a - mx) * (b - my) for a, b in zip(rx, ry)) / (sxx * syy) ** 0.5


def factor_percentiles(results):
    """Midrank percentile of each factor inside the analyzed cohort (same rule as research.analyze, minimum 1)."""
    out = {}
    for k in FACTORS:
        cohort = [r['factors'][k] for r in results]
        out[k] = [percentile(v, cohort, 1) if num(v) else None for v in cohort]
    return out


def correlation_matrix(results):
    out = {}
    for a, b in combinations(FACTORS, 2):
        pairs = [(r['factors'][a], r['factors'][b]) for r in results if num(r['factors'][a]) and num(r['factors'][b])]
        cell = dict(rho=spearman([p[0] for p in pairs], [p[1] for p in pairs]), n=len(pairs))
        out[(a, b)] = cell;out[(b, a)] = cell
    return out


def _score(row_percentiles, weights):
    total = sum(weights.values())
    return 100 * sum(weights[k] / total * row_percentiles[k] for k in weights)


def positive_int(value):
    try:number = int(value)
    except (TypeError, ValueError):number = 0
    if number < 1 or str(number) != str(value).strip():raise argparse.ArgumentTypeError('1 이상의 정수가 필요합니다')
    return number


def leave_one_out(results, weights, top_n):
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1:raise ValueError('top_n은 1 이상의 정수')
    p = factor_percentiles(results)
    scored = [i for i in range(len(results)) if all(p[k][i] is not None for k in weights)]
    out = dict(top_n=top_n, baseline_scored=len(scored), without={})
    def ranking(w):
        values = {i: _score({k: p[k][i] for k in w}, w) for i in scored}
        return sorted(scored, key=lambda i: (-values[i], results[i]['code'])), values
    if not scored:
        out['without'] = {k: dict(top_overlap=None, rank_spearman=None) for k in weights};return out
    base_rank, base_values = ranking(weights);size = min(top_n, len(scored));base_top = set(base_rank[:size])
    out['baseline_top'] = [results[i]['code'] for i in base_rank[:size]]
    for k in weights:
        w = {f: v for f, v in weights.items() if f != k}
        rank, values = ranking(w)
        out['without'][k] = dict(top_overlap=len(base_top & set(rank[:size])) / size,
            rank_spearman=spearman([base_values[i] for i in scored], [values[i] for i in scored]))
    return out


def missing_report(results):
    by_factor = {k: sum(1 for r in results if not num(r['factors'][k])) for k in FACTORS}
    scored = sum(1 for r in results if all(num(r['factors'][k]) for k in FACTORS))
    return dict(total=len(results), scored=scored, unscored=len(results) - scored, missing_by_factor=by_factor)


def build_report(results, top_n=5):
    return dict(correlations=correlation_matrix(results), leave_one_out=leave_one_out(results, WEIGHTS, top_n), missing=missing_report(results))


def _cell(value):
    return '-' if value is None else f'{value:.2f}'


def render(report, source):
    m, lo, miss = report['correlations'], report['leave_one_out'], report['missing']
    lines = [f'# 요인 중복 진단 (읽기 전용) — {source}', '', '## 요인 간 순위 상관 (Spearman, 쌍별 유효 표본)', '',
        '| | ' + ' | '.join(FACTORS) + ' |', '|---|' + '---|' * len(FACTORS)]
    for a in FACTORS:
        cells = ['1.00' if a == b else f"{_cell(m[(a, b)]['rho'])} (n={m[(a, b)]['n']})" for b in FACTORS]
        lines.append(f'| {a} | ' + ' | '.join(cells) + ' |')
    lines += ['', f"## 한 요인 제거 시 상위 {lo['top_n']}개 겹침 (점수 계산 가능 {lo['baseline_scored']}개, 가중치 재정규화)", '',
        '| 제거 요인 | 상위 겹침 | 점수 순위 상관 |', '|---|---|---|']
    for k, v in lo['without'].items():lines.append(f"| {k} | {_cell(v['top_overlap'])} | {_cell(v['rank_spearman'])} |")
    lines += ['', '## 점수 미계산 종목', '', f"전체 {miss['total']}개 중 점수 계산 {miss['scored']}개, 미계산 {miss['unscored']}개(다섯 요인이 모두 있어야 계산).", '',
        '| 요인 | 결측 종목 수 |', '|---|---|']
    lines += [f'| {k} | {n} |' for k, n in miss['missing_by_factor'].items()]
    lines += ['', '이 보고서는 구조 진단이다. 가중치·정의 변경 근거나 수익 예측 증거가 아니다.']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--fixture', action='store_true', help='합성 fixture만 사용(실제 자료를 읽지 않음)')
    source.add_argument('--snapshot', type=Path, help='분석 스냅샷 JSON 경로(읽기 전용, 사용자 승인 후)')
    parser.add_argument('--top-n', type=positive_int, default=5)
    args = parser.parse_args(argv)
    if args.fixture:
        from investment.fixture import make_fixture
        snapshot, label = make_fixture(), '합성 fixture: 실제 자료를 읽지 않았다'
    else:
        snapshot, label = json.loads(args.snapshot.read_text(encoding='utf-8')), f'스냅샷 {args.snapshot.name} (읽기 전용)'
    print(render(build_report(analyze(snapshot), args.top_n), label))
    return 0


if __name__ == '__main__':
    sys.exit(main())
