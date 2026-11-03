"""S10 follow-up: read-only sensitivity of the fixed constants inside `price_trend_status` (market_discovery.technical).

`price_trend_status` is a compound rule: close>SMA50>SMA150>SMA200, SMA200 above the mean of an earlier window, close above
the close 126 sessions ago, and 126-session excess return over the index above 0. This report recomputes it from the
stored adjusted daily bars with one constant changed at a time (or one sub-condition dropped) and shows how the number of
recommendation-filter passes moves. The baseline recomputation is checked against `technical()` itself (`parity`).
Aggregates only, no company codes. With `--root` every non-baseline variant is appended to the hash-chained trial log BEFORE
it is evaluated, each as rejected ("diagnostic, not adopted"). Nothing is ranked or adopted; a pass count is not a return
measure, and the bars are Naver adjusted prices at one date, not point-in-time data. Nothing is written to the data folders.
"""
import argparse
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import mean
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0, str(ROOT))
from investment.core import num
from investment.market_discovery import technical
from investment.market_history import benchmark_calendar
from investment.trial_log import record, summary
from tools.recommendation_score_report import build_real_context, manifest
from tools.threshold_sensitivity_report import BASE, feature_rows, passed_codes

TREND_BASE = dict(sma_a=50, sma_b=150, sma_c=200, mean_end=20, ret_lag=126, rs_lag=126, rs_min=0.0, drop='none')
GRID = dict(sma_a=(40, 60), sma_b=(120, 180), sma_c=(180, 220), mean_end=(10, 40), ret_lag=(105, 147), rs_lag=(105, 147), rs_min=(-5.0, 5.0))
DROPS = ('stack', 'slope', 'return', 'rs')
WINDOW = 200
RULE_VERSION = 'market_discovery.technical price_trend_status sma50/150/200 mean-window 200 end 20 lag126 rs126>0'
REASON = '민감도 진단용 변형이며 채택 대상이 아님(S10: 가장 좋은 값을 고르지 않는다)'


def trend_variants():
    out = [dict(TREND_BASE)] + [{**TREND_BASE, k: v} for k, values in GRID.items() for v in values]
    return out + [{**TREND_BASE, 'drop': d} for d in DROPS]


def label(p):
    diff = [f'{k}={p[k]}' for k in TREND_BASE if p[k] != TREND_BASE[k]]
    return ', '.join(diff) if diff else '현재 규칙'


def terms(e, p):
    """The four sub-conditions of the rule (same operations and comparison directions as `technical`)."""
    c = e['closes'];dates = e['dates'];bm = e['bm'];now = c[-1]
    totals = [0]
    for v in c:totals.append(totals[-1] + v)                      # prefix sums, exactly like `technical`, so strict comparisons agree bit for bit
    sma = lambda n: (totals[-1] - totals[-1 - n]) / n
    n = p['rs_lag']
    return dict(stack=now > sma(p['sma_a']) > sma(p['sma_b']) > sma(p['sma_c']),
        slope=sma(p['sma_c']) > mean(c[-(WINDOW + p['mean_end']):-p['mean_end']]),
        back=now > c[-1 - p['ret_lag']],
        rs=((now / c[-1 - n] - 1) - (bm[dates[-1]] / bm[dates[-1 - n]] - 1)) * 100 > p['rs_min'])


def price_status(e, p):
    """'pass'/'fail' from one record's closes, optionally ignoring one sub-condition (`drop`)."""
    t = terms(e, p);skip = {'return': 'back'}.get(p['drop'], p['drop'])
    return 'pass' if all(v for k, v in t.items() if k != skip) else 'fail'


def eligible_records(history, calendar, suspended, markets=None, codes=None):
    """Records for which `technical` computes the full rule at baseline; everything else keeps its stored status."""
    out = {}
    for code in (codes if codes is not None else history.get('histories', {})):
        record_ = history.get('histories', {}).get(code)
        if not record_:continue
        market = (markets or {}).get(code, 'KOSPI');bench = history.get('benchmarks', {}).get(market)
        if not bench:continue
        t = technical(record_, bench, calendar, suspended=code in suspended, include_series=False)
        if not num(t['rs126_pct']):continue
        prices = record_['prices']
        out[code] = dict(dates=[b['date'] for b in prices], closes=[b['close'] for b in prices],
            bm={b['date']: b['close'] for b in bench['prices']}, base_status=t['price_trend_status'])
    return out


def parity(elig):
    return sum(1 for e in elig.values() if price_status(e, TREND_BASE) != e['base_status'])


def trend_sensitivity(rows, elig, vs):
    def passes(v):
        changed = [{**r, 'status': price_status(elig[r['code']], v) if r['code'] in elig else r['status']} for r in rows]
        return passed_codes(changed, BASE)
    base = passes(vs[0]);out = []
    for v in vs:
        got = passes(v)
        out.append(dict(params=v, status_pass=sum(1 for e in elig.values() if price_status(e, v) == 'pass'), passed=len(got),
            retained=len(got & base), added=len(got - base), dropped=len(base - got)))
    out[0]['parity_mismatch'] = parity(elig)
    return out


def trial_entries(vs, experiment_id):
    return [dict(experiment_id=experiment_id, rule_version=RULE_VERSION, parameter_set=dict(v), decision='rejected', discard_reason=REASON) for v in vs[1:]]


def record_trials(root, profile, vs, experiment_id):
    return [record(root, profile, entry) for entry in trial_entries(vs, experiment_id)]


def render(results, source, trials, eligible):
    lines = [f'# price_trend_status 내부 상수 민감도 진단 (읽기 전용) — {source}', '',
        f'재계산 가능 기업 {eligible}개(저장 일봉 253봉 이상, 기준 재계산이 `technical()`과 불일치한 기업 {results[0]["parity_mismatch"]}개). 한 번에 하나만 바꾼 결과다.', '',
        '| 변형 | 추세 상태 통과 | 추천 필터 통과 | 유지 | 추가 | 탈락 |', '|---|---|---|---|---|---|']
    lines += [f"| {label(r['params'])} | {r['status_pass']} | {r['passed']} | {r['retained']} | {r['added']} | {r['dropped']} |" for r in results]
    lines += ['', f'시도 로그: 이번 실행의 변형 {trials}개(현재 규칙 제외)를 평가 전에 기록했다. 모두 기각 상태이며 어떤 값도 채택하지 않았다. 최적 값을 고르는 용도로 쓰지 않는다.',
        '네이버 수정주가 일봉의 한 시점 결과이며 시점 제약 자료가 아니다. 통과 수는 수익·위험 지표가 아니다.']
    return '\n'.join(lines)


def synthetic_market(n=60, seed=3):
    rng = random.Random(seed);days = [];d = date(2025, 1, 2)
    while len(days) < 300:
        if d.weekday() < 5:days.append(d.isoformat())
        d += timedelta(days=1)
    def walk(drift, noise):
        x = 100.0;out = []
        for _ in days:
            x *= math.exp(drift + rng.gauss(0, noise));out.append(round(x, 4))
        return out
    def bars(closes, index):
        return [dict(date=d_, close=c, open=c, high=c, low=c, volume=1000, turnover=None, final=True, venue='KRX', no_trade=False,
            adjustment_basis='index_level' if index else 'naver_chart_adjusted') for d_, c in zip(days, closes)]
    index = bars(walk(0.0004, 0.007), True)
    bench = {s: dict(symbol=s, kind='index', prices=[dict(b) for b in index], source=dict(url='x://' + s)) for s in ('KOSPI', 'KOSDAQ')}
    hist = {str(900000 + i): dict(symbol=str(900000 + i), kind='item', prices=bars(walk(rng.uniform(-0.002, 0.0045), 0.015), False)) for i in range(n)}
    return dict(benchmarks=bench, histories=hist), benchmark_calendar(bench)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--synthetic', action='store_true', help='합성 입력만 사용(실제 자료를 읽지 않고 시도 로그도 쓰지 않음)')
    source.add_argument('--root', type=Path, help='INVESTMENT 작업 폴더(읽기 전용 + 시도 로그 기록, 사용자 승인 후)')
    parser.add_argument('--experiment-id', default='S10-trend-status-sensitivity')
    args = parser.parse_args(argv)
    vs = trend_variants();before = after = None;note = '시도 로그: 합성 실행이라 기록하지 않았다.'
    try:
        if args.synthetic:
            history, calendar = synthetic_market();elig = eligible_records(history, calendar, set())
            rows = [dict(code=c, rs=80, short=60, close=100, sma200=90, status='fail', growth=20, margin=5, roe=10, debt=50, ocf=10) for c in elig]
            label_ = '합성 입력: 실제 자료를 읽지 않았다'
        else:
            from investment.local_config import load_local
            from investment.market_discovery import load_market_cache
            from tools.recommendation_score_report import latest_snapshot
            local = load_local(args.root)
            watched = [local['data_dir'] / local['profile']] + ([local['manual_snapshot_file'].parent] if local.get('manual_snapshot_file') else [])
            before = manifest(watched)
            context, today, _ = build_real_context(args.root)
            snapshot = latest_snapshot(local['data_dir'] / local['profile'] / 'user_input' / 'research.sqlite3')
            cache = load_market_cache(args.root, snapshot) or {}
            history = cache.get('history') or {}
            calendar = benchmark_calendar(history.get('benchmarks', {}))
            rows = feature_rows(context, today)
            markets = {r['code']: r.get('market') for r in context['snapshot']['companies']}
            suspended = {r['code'] for r in cache.get('universe', {}).get('companies', []) if r.get('trading_status', {}).get('tradeStopYn') == 'Y'}
            elig = eligible_records(history, calendar, suspended, markets, {r['code'] for r in rows})
            label_ = '저장 일봉(읽기 전용; 새로고침 미실행)'
            record_trials(args.root, local['profile'], vs, args.experiment_id)       # recorded before any variant is evaluated
            anchor = summary(args.root, local['profile'])
            note = f"시도 로그 누적: {anchor['trials']}회, 고유 파라미터 {anchor['distinct_parameter_sets']}개, head_digest {anchor['head_digest']}"
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'오류: {exc}', file=sys.stderr);return 2
    results = trend_sensitivity(rows, elig, vs)
    if not args.synthetic:after = manifest(watched)
    print(render(results, label_, len(vs) - 1, len(elig)))
    print('\n' + note)
    if results[0]['parity_mismatch']:
        print(f"\n오류: 기준 재계산이 technical()과 불일치한 기업 {results[0]['parity_mismatch']}개 — 위 표를 사용하지 않는다.");return 4
    if before is not None:
        same = before == after
        print(f"\n읽기 전용 확인: 데이터 폴더 파일 {len(before)}개의 크기·수정시각(SQLite는 해시)이 실행 전후 {'동일' if same else '**달라짐**'}.")
        return 0 if same else 3
    return 0


if __name__ == '__main__':
    sys.exit(main())
