"""Q09 follow-up: read-only diagnostics for the recommendation draft score (the score that actually orders candidates).

Replays the filters and the weighted score of `recommendations.propose` (0.4*RS + 0.2*1M RS + 0.25*min(100,revenue YoY)
+ 0.15*min(100,ROE)) over the market candidate pool and reports: the filter funnel, rank correlations among the four
score terms, how often the 100 caps bind, and top-N overlap when one term is left out. Aggregates only, no per-company
output. Nothing is written: the saved snapshot is opened with SQLite mode=ro, and a before/after file manifest of the
data folders is compared. `tests/test_recommendation_score_report.py` pins parity with `propose`. This is a structure
diagnostic, not evidence about returns, and it changes no weights, filters or definitions.
"""
import argparse
import hashlib
import json
import os
import random
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0, str(ROOT))
from investment.core import num
from investment.recommendations import minimum_financial_period
from tools.factor_overlap_report import spearman

WEIGHTS = dict(rs=0.4, short=0.2, growth=0.25, roe=0.15)
TERMS = tuple(WEIGHTS)
CAP = 100
STAGES = ('not_discovery_allowed', 'financial_missing', 'financial_stale', 'trend_failed', 'growth_or_financial_failed', 'passed')


def candidate_table(context, created_on):
    """One row per company in the context snapshot, mirroring the checks and order of `propose`."""
    today = datetime.fromisoformat(created_on).date() if 'T' in created_on else __import__('datetime').date.fromisoformat(created_on)
    out = []
    for r in context['snapshot']['companies']:
        row = dict(code=r['code'], stage='not_discovery_allowed', reason=None, rs=None, short=None, growth=None, roe=None, score=None)
        out.append(row)
        if not r.get('discovery_allowed'):continue
        t = context['research']['rows'][r['code']]['technical'];f = r.get('common_financial');m = (f or {}).get('metrics', {})
        rs = t.get('price_strength', {}).get('score');short = t.get('short_rs', {}).get('1m', {}).get('score');sma = t.get('sma', {})
        row.update(rs=rs, short=short, growth=m.get('revenue_growth_pct'), roe=m.get('roe_pct'))
        if not f or f['basis'] != 'CFS' or not f['ttm_complete'] or not all(num(m.get(k)) for k in ('revenue_growth_pct', 'operating_margin_pct', 'roe_pct', 'debt_ratio_pct')):
            row.update(stage='financial_missing', reason='재무/비교기간 미확보');continue
        floor = minimum_financial_period(today, f.get('year_end_month', 12))
        if f['period'] < floor:
            row.update(stage='financial_stale', reason=f'재무 최신성 기준 {floor} 이후 자료 대기');continue
        if not all(num(x) for x in (rs, short, t.get('close'), sma.get('200'))) or rs < 70 or short < 50 or t['close'] <= sma['200'] or t.get('price_trend_status') != 'pass':
            row.update(stage='trend_failed', reason='추세 조건 미충족');continue
        if m['revenue_growth_pct'] < 10 or m['operating_margin_pct'] <= 0 or m['roe_pct'] <= 0 or m['debt_ratio_pct'] > 200 or not num(f.get('ttm_ocf')) or f['ttm_ocf'] <= 0:
            row.update(stage='growth_or_financial_failed', reason='성장/재무·현금흐름 조건 미충족');continue
        row.update(stage='passed', score=_score(row))
    return out


def _terms(row):
    return dict(rs=row['rs'], short=row['short'], growth=min(CAP, row['growth']), roe=min(CAP, row['roe']))


def _score(row, without=None):
    t = _terms(row)
    return sum(WEIGHTS[k] * t[k] for k in TERMS if k != without)


def _passed(table):
    return [r for r in table if r['stage'] == 'passed']


def funnel(table):
    counts = {k: sum(1 for r in table if r['stage'] == k) for k in STAGES}
    return dict(universe=len(table), **counts)


def component_stats(table):
    rows = _passed(table)
    out = dict(n=len(rows), cap_binding=dict(growth=sum(1 for r in rows if r['growth'] > CAP), roe=sum(1 for r in rows if r['roe'] > CAP)), correlations={})
    series = {k: [_terms(r)[k] for r in rows] for k in TERMS}
    for i, a in enumerate(TERMS):
        for b in TERMS[i + 1:]:
            cell = dict(rho=spearman(series[a], series[b]), n=len(rows))
            out['correlations'][(a, b)] = cell;out['correlations'][(b, a)] = cell
    ranked = sorted(rows, key=lambda r: (-r['score'], r['code']))
    out['boundary_gap'] = ranked[14]['score'] - ranked[15]['score'] if len(ranked) > 15 else None
    return out


def positive_int(value):
    try:number = int(value)
    except (TypeError, ValueError):number = 0
    if number < 1 or str(number) != str(value).strip():raise argparse.ArgumentTypeError('1 이상의 정수가 필요합니다')
    return number


def leave_one_out(table, top_n=15):
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n < 1:raise ValueError('top_n은 1 이상의 정수')
    rows = _passed(table)
    out = dict(top_n=top_n, passed=len(rows), baseline_top=[], without={})
    if not rows:
        out['without'] = {k: dict(top_overlap=None, rank_spearman=None) for k in TERMS};return out
    def rank(without=None):
        scores = {r['code']: _score(r, without) for r in rows}
        return sorted(rows, key=lambda r: (-scores[r['code']], r['code'])), scores
    base, base_scores = rank();size = min(top_n, len(rows));top = {r['code'] for r in base[:size]}
    out['baseline_top'] = [r['code'] for r in base[:size]]
    for k in TERMS:
        order, scores = rank(k)
        out['without'][k] = dict(top_overlap=len({r['code'] for r in order[:size]} & top) / size,
            rank_spearman=spearman([base_scores[r['code']] for r in rows], [scores[r['code']] for r in rows]))
    return out


def _cell(v):
    return '-' if v is None else f'{v:.2f}'


def render(fun, stats, loo, source):
    lines = [f'# 추천 초안 점수 진단 (읽기 전용) — {source}', '', '## 필터 통과 깔때기', '',
        '| 단계 | 기업 수 |', '|---|---|',
        f"| 전체(스냅샷에 담긴 기업) | {fun['universe']} |", f"| 탐색 대상 아님 | {fun['not_discovery_allowed']} |",
        f"| 재무·비교기간 미확보 | {fun['financial_missing']} |", f"| 재무 최신성 기준 미달 | {fun['financial_stale']} |",
        f"| 추세 조건 미충족 | {fun['trend_failed']} |", f"| 성장·재무·현금흐름 조건 미충족 | {fun['growth_or_financial_failed']} |",
        f"| **통과(점수 계산)** | **{fun['passed']}** |", '', '## 구성항 간 순위 상관 (Spearman, 통과 기업, 상한 적용 후 값)', '',
        '| | ' + ' | '.join(TERMS) + ' |', '|---|' + '---|' * len(TERMS)]
    for a in TERMS:
        lines.append(f'| {a} | ' + ' | '.join('1.00' if a == b else _cell(stats['correlations'][(a, b)]['rho']) for b in TERMS) + ' |')
    lines += ['', '## 상한(cap) 작동', '', f"통과 {stats['n']}개 중 매출 YoY>{CAP}% {stats['cap_binding']['growth']}개, ROE>{CAP}% {stats['cap_binding']['roe']}개(상한 {CAP}으로 잘림).",
        f"상위 15위와 16위의 점수 차: {_cell(stats['boundary_gap'])}", '',
        f"## 한 항 제거 시 상위 {loo['top_n']}개 겹침 (통과 {loo['passed']}개)", '', '| 제거 항 | 가중치 | 상위 겹침 | 점수 순위 상관 |', '|---|---|---|---|']
    lines += [f"| {k} | {WEIGHTS[k]} | {_cell(v['top_overlap'])} | {_cell(v['rank_spearman'])} |" for k, v in loo['without'].items()]
    lines += ['', '이 보고서는 구조 진단이다. 가중치·필터·정의 변경 근거나 수익 예측 증거가 아니다.']
    return '\n'.join(lines)


def latest_snapshot(path):
    """Newest `complete` snapshot payload, opened read-only. Never creates or modifies the file."""
    path = Path(path)
    if not path.is_file():raise ValueError('저장 스냅샷 DB를 찾을 수 없습니다')
    db = sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True)
    try:
        row = db.execute("SELECT payload FROM snapshots WHERE status='complete' ORDER BY created DESC, rowid DESC LIMIT 1").fetchone()
    finally:
        db.close()
    if not row:raise ValueError('완료된 스냅샷이 없습니다')
    return json.loads(row[0])


def manifest(paths):
    """(size, mtime_ns[, sha256 for SQLite files]) of every file under the given folders. A metadata comparison, not proof: a same-size edit that keeps its mtime would not show."""
    out = {}
    for base in map(Path, paths):
        if not base.exists():
            out[str(base)] = 'missing';continue
        for folder, _, files in os.walk(base):
            for name in files:
                p = Path(folder) / name;stat = p.stat()
                digest = hashlib.sha256(p.read_bytes()).hexdigest() if name.endswith(('.sqlite3', '.sqlite', '.db')) else None
                out[str(p)] = (stat.st_size, stat.st_mtime_ns, digest)
    return out


def build_real_context(root):
    from investment.local_config import load_local
    from investment.market_discovery import load_market_cache
    from investment.company_financials import load_cached as load_company_financials
    from investment.financial_table import load_local_financials, merge_financials
    from investment.recommendations import research_context
    local = load_local(root)
    snapshot = latest_snapshot(local['data_dir'] / local['profile'] / 'user_input' / 'research.sqlite3')
    cache = load_market_cache(root, snapshot) or {}
    rows = {r['code']: r for r in cache.get('universe', {}).get('companies', []) if r.get('eligibility') == 'candidate'}
    rows.update({r['code']: r for r in snapshot['companies']})
    today = datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    finances = load_company_financials(root, snapshot, list(rows.values()), as_of=today, cache=cache)
    finances = merge_financials(load_local_financials(root, snapshot), finances, as_of=today)
    context = research_context(snapshot, cache, finances, today)
    if not context:raise ValueError('추천 입력 맥락을 만들 수 없습니다(시장 캐시·공통 재무 확인 필요)')
    return context, today, local


def synthetic_context(count=40, seed=7):
    rng = random.Random(seed);rows = [];facts = {}
    for i in range(count):
        code = str(900000 + i)
        rows.append(dict(code=code, name=f'합성{i}', market='KOSPI', industry='합성', discovery_allowed=True,
            common_financial=dict(basis='CFS', period='2026-06-30', ttm_complete=True, ttm_ocf=rng.choice([-5, 10, 20, 30]),
                metrics=dict(revenue_growth_pct=rng.uniform(-5, 150), operating_margin_pct=rng.uniform(-2, 25), roe_pct=rng.uniform(-3, 120), debt_ratio_pct=rng.uniform(10, 260)))))
        facts[code] = dict(technical=dict(close=100, price_trend_status='pass', sma={'200': rng.choice([80, 95, 105])},
            price_strength=dict(score=rng.uniform(55, 99)), short_rs={'1m': dict(score=rng.uniform(30, 95))}))
    return dict(snapshot={'meta': {'price_date': '2026-10-01'}, 'companies': rows}, research={'rows': facts})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--synthetic', action='store_true', help='합성 입력만 사용(실제 자료를 읽지 않음)')
    source.add_argument('--root', type=Path, help='INVESTMENT 작업 폴더(읽기 전용, 사용자 승인 후)')
    parser.add_argument('--top-n', type=positive_int, default=15)
    args = parser.parse_args(argv)
    try:
        if args.synthetic:
            context, today, label, before, after = synthetic_context(), '2026-10-02', '합성 입력: 실제 자료를 읽지 않았다', None, None
        else:
            from investment.local_config import load_local
            local = load_local(args.root)
            watched = [local['data_dir'] / local['profile']] + ([local['manual_snapshot_file'].parent] if local.get('manual_snapshot_file') else [])
            before = manifest(watched)
            context, today, _ = build_real_context(args.root)
            after = manifest(watched);label = '저장 스냅샷과 시장 캐시(읽기 전용; 새로고침 미실행)'
    except (ValueError, OSError, KeyError) as exc:
        print(f'오류: {exc}', file=sys.stderr);return 2
    table = candidate_table(context, today)
    print(render(funnel(table), component_stats(table), leave_one_out(table, args.top_n), label))
    if before is not None:
        same = before == after
        print(f"\n읽기 전용 확인: 데이터 폴더 파일 {len(before)}개의 크기·수정시각(SQLite는 해시)이 실행 전후 {'동일' if same else '**달라짐**'}.")
        return 0 if same else 3
    return 0


if __name__ == '__main__':
    sys.exit(main())
