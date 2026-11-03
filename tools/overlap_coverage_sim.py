"""Q07 T1: how often confidence intervals for the mean of overlapping H-day plan returns contain the true mean.

Synthetic returns only. No market data, no DB, no network, no files written. Monthly-spaced plans (step 21 sessions)
make H-day returns overlap; naive standard errors ignore that. Compared methods: naive, non-overlapping subsample,
Newey-West (lag m-1, Bartlett), stationary bootstrap (mean block length m), where m = ceil(H/step).
Results are properties of the synthetic model, not of Korean stock returns.
"""
import argparse
import json
import math
import sys
import numpy as np

STEP = 21
HORIZONS = (63, 126, 252)
SESSIONS_PER_YEAR = 252
Z = 1.959963984540054
MODELS = ('iid', 'garch')
METHODS = ('naive', 'nonoverlap', 'newey_west', 'stationary_bootstrap')


def plan_returns(daily, horizon, step=STEP):
    """Sum of daily log returns over `horizon` sessions for plans starting every `step` sessions."""
    cumulative = np.concatenate(([0.0], np.cumsum(daily)))
    starts = np.arange(0, len(daily) - horizon + 1, step)
    return cumulative[starts + horizon] - cumulative[starts]


def newey_west_se(values, lag):
    n = len(values)
    centered = values - values.mean()
    variance = float(centered @ centered) / n
    for k in range(1, lag + 1):
        if k >= n:break
        variance += 2 * (1 - k / (lag + 1)) * float(centered[k:] @ centered[:-k]) / n
    return math.sqrt(max(variance, 0.0) / n)


def stationary_bootstrap_means(values, mean_block, reps, rng):
    n = len(values)
    p = 1.0 / mean_block
    jump = rng.random((reps, n)) < p
    start = rng.integers(0, n, (reps, n))
    index = np.empty((reps, n), dtype=np.int64)
    index[:, 0] = start[:, 0]
    for t in range(1, n):index[:, t] = np.where(jump[:, t], start[:, t], (index[:, t - 1] + 1) % n)
    return values[index].mean(axis=1)


def intervals(plans, overlap, boot_reps, rng):
    """95% intervals by method. `overlap` is m = ceil(H/step)."""
    n = len(plans);mean = float(plans.mean());out = {}
    out['naive'] = (mean, Z * float(plans.std(ddof=1)) / math.sqrt(n))
    sub = plans[::overlap]
    out['nonoverlap'] = (float(sub.mean()), Z * float(sub.std(ddof=1)) / math.sqrt(len(sub))) if len(sub) > 2 else (mean, float('nan'))
    out['newey_west'] = (mean, Z * newey_west_se(plans, max(overlap - 1, 0)))
    boots = stationary_bootstrap_means(plans, max(overlap, 1), boot_reps, rng)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    out['stationary_bootstrap'] = (mean, (hi - lo) / 2, (float(lo), float(hi)))
    return out


def daily_returns(model, sessions, mu, sigma, rng):
    if model == 'iid':return rng.normal(mu, sigma, sessions)
    alpha, beta = 0.10, 0.85
    omega = sigma * sigma * (1 - alpha - beta)
    shocks = rng.standard_normal(sessions);out = np.empty(sessions);variance = sigma * sigma
    for t in range(sessions):
        out[t] = mu + math.sqrt(variance) * shocks[t]
        variance = omega + alpha * (out[t] - mu) ** 2 + beta * variance
    return out


def simulate(horizon, years, *, model='iid', reps=300, boot_reps=200, seed=0, mu=0.0, sigma=0.01):
    if horizon not in HORIZONS:raise ValueError('horizon은 63/126/252')
    if not isinstance(years, int) or years < 2:raise ValueError('years는 2 이상의 정수')
    if model not in MODELS:raise ValueError('model 확인 필요')
    if not isinstance(reps, int) or reps < 10 or not isinstance(boot_reps, int) or boot_reps < 20:raise ValueError('반복 횟수 확인 필요')
    rng = np.random.default_rng(seed)
    overlap = math.ceil(horizon / STEP);truth = horizon * mu
    hits = {m: 0 for m in METHODS};widths = {m: 0.0 for m in METHODS};counted = {m: 0 for m in METHODS}
    plans_n = nonoverlap_n = 0
    for _ in range(reps):
        plans = plan_returns(daily_returns(model, years * SESSIONS_PER_YEAR, mu, sigma, rng), horizon)
        plans_n, nonoverlap_n = len(plans), len(plans[::overlap])
        for method, value in intervals(plans, overlap, boot_reps, rng).items():
            if method == 'stationary_bootstrap':lo, hi = value[2]
            else:
                center, half = value
                if not math.isfinite(half):continue
                lo, hi = center - half, center + half
            counted[method] += 1;hits[method] += int(lo <= truth <= hi);widths[method] += hi - lo
    return dict(horizon=horizon, years=years, model=model, reps=reps, seed=seed, plans=plans_n, nonoverlap_plans=nonoverlap_n, overlap_factor=overlap,
        methods={m: dict(coverage=hits[m] / counted[m] if counted[m] else None, mean_width=widths[m] / counted[m] if counted[m] else None) for m in METHODS})


def render(results):
    lines = ['| 지평 | 연수 | 모형 | 계획 수 | 비겹침 | ' + ' | '.join(METHODS) + ' |', '|---|---|---|---|---|' + '---|' * len(METHODS)]
    for r in results:
        cells = ' | '.join('-' if r['methods'][m]['coverage'] is None else f"{r['methods'][m]['coverage']:.2f}" for m in METHODS)
        lines.append(f"| {r['horizon']} | {r['years']} | {r['model']} | {r['plans']} | {r['nonoverlap_plans']} | {cells} |")
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--horizons', type=int, nargs='+', default=list(HORIZONS))
    parser.add_argument('--years', type=int, nargs='+', default=[3, 5, 10, 15])
    parser.add_argument('--model', choices=MODELS, default='iid')
    parser.add_argument('--reps', type=int, default=300)
    parser.add_argument('--seed', type=int, default=20261103)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    results = [simulate(h, y, model=args.model, reps=args.reps, seed=args.seed) for h in args.horizons for y in args.years]
    print(json.dumps(results, ensure_ascii=False, indent=2) if args.json else render(results))
    print('명목 95% 구간의 실제 포함률(합성 자료). 한국 주식 수익률의 성질이 아니다.', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
