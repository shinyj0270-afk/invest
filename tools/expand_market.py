"""Explicit one-time public market cache collection; never touches Infomax or DB."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys
import time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from investment.local_config import load_local
from investment.naver_universe import fetch_listing, attach_industries
from investment.market_history import fetch_history, benchmark_calendar


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-listing', action='store_true')
    parser.add_argument('--listing-only', action='store_true')
    parser.add_argument('--retry-errors', action='store_true',
                        help='retry only codes recorded as errors in the last history bundle')
    args = parser.parse_args()
    local = load_local(ROOT)
    folder = local['data_dir']/local['profile']/'market-expansion'
    listing = folder/'universe.json'
    def progress(p):
        if p.get('page', 0) % 5 == 0 or p.get('completed', 0) % 10 == 0:
            print(json.dumps(p, ensure_ascii=False), flush=True)
    if args.reuse_listing:
        bundle = json.loads(listing.read_text(encoding='utf-8'))
    else:
        bundle = attach_industries(fetch_listing(progress=progress), progress=progress)
        if not bundle['companies'] or not bundle['pagination_complete']:
            save(folder/'listing-failure.json', bundle)
            raise SystemExit('목록 수집 미완료: 기존 캐시 보존')
        save(listing, bundle)
    print('Universe:', dict(Counter(r['eligibility'] for r in bundle['companies'])), flush=True)
    if args.listing_only:
        return
    history_path = folder/'histories.json'
    previous = json.loads(history_path.read_text(encoding='utf-8')) if args.retry_errors and history_path.exists() else None
    if args.retry_errors and not previous:
        raise SystemExit('재시도할 기존 이력 묶음 없음')
    end = previous['end'] if previous else (datetime.now(ZoneInfo('Asia/Seoul')).date()-timedelta(days=1)).isoformat()
    start = previous['start'] if previous else (datetime.fromisoformat(end).date()-timedelta(days=620)).isoformat()
    history_dir = folder/'history'
    benchmarks = {s: fetch_history(s, kind='index', start=start, end=end, cache_dir=history_dir)
                  for s in ('KOSPI', 'KOSDAQ')}
    calendar = benchmark_calendar(benchmarks)
    result = dict(schema_version='market-history-bundle-0.1', start=start, end=end,
        benchmarks=benchmarks, calendar=calendar,
        histories=dict(previous.get('histories', {})) if previous else {}, errors=[])
    rows = [r for r in bundle['companies'] if r['eligibility'] == 'candidate']
    if previous:
        retry_codes = {e.get('code') for e in previous.get('errors', [])}
        rows = [r for r in rows if r['code'] in retry_codes]
    def collect(row):
        time.sleep(.15)
        return fetch_history(row['code'], start=start, end=end, cache_dir=history_dir)
    with ThreadPoolExecutor(max_workers=2) as executor:
        jobs = {executor.submit(collect, row): row['code'] for row in rows}
        for n, future in enumerate(as_completed(jobs), 1):
            code = jobs[future]
            try:
                result['histories'][code] = future.result()
            except Exception as exc:
                result['errors'].append(dict(code=code, reason=type(exc).__name__))
            if n % 100 == 0 or n == len(rows):
                print(f'History {n}/{len(rows)} total_success={len(result["histories"])} retry_failed={len(result["errors"])}', flush=True)
    save(history_path, result)
    print('Saved public universe and history caches.', flush=True)


if __name__ == '__main__':
    main()
