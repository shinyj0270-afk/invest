"""Write a standard verification report for independent (Claude) review. Read-only for sources and data."""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from investment.local_config import load_local  # noqa: E402
from investment.store import Store  # noqa: E402
from investment.market_discovery import load_market_cache  # noqa: E402
from investment.company_financials import load_cached  # noqa: E402
from investment.financial_table import load_local_financials, merge_financials  # noqa: E402
from investment.recommendations import RecommendationBook, research_context  # noqa: E402
from investment.verification import review_report, report_markdown  # noqa: E402


def targets(book, codes):
    """Explicit codes, otherwise the latest recommendation. Holdings are never read implicitly."""
    records = book.read()['records']
    latest = records[-1] if records else None
    prior = records[-2] if len(records) > 1 else None
    if codes:
        return [(c, None) for c in codes], latest, prior
    return [(t['code'], '편입') for t in (latest or {}).get('targets', [])], latest, prior


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--codes', nargs='*', default=[], help='6자리 종목코드; 생략 시 최신 월간 추천 종목')
    args = parser.parse_args()
    if any(not re.fullmatch(r'[0-9A-Z]{6}', c) for c in args.codes):
        raise SystemExit('종목코드 확인 필요')
    config = load_local(ROOT)
    snapshot = Store(config['data_dir'], config['profile'], 'user_input').latest()
    if snapshot is None:
        raise SystemExit('실제 저장 스냅샷 없음')
    today = datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    cache = load_market_cache(ROOT, snapshot) or {}
    book = RecommendationBook(ROOT)
    picked, latest, prior = targets(book, args.codes)
    universe = {r['code']: r for r in cache.get('universe', {}).get('companies', []) if r.get('eligibility') == 'candidate'}
    universe.update({r['code']: r for r in snapshot['companies']})
    rows = [universe[c] for c, _ in picked if c in universe]
    finances = merge_financials(load_local_financials(ROOT, snapshot), load_cached(ROOT, snapshot, rows, as_of=today, cache=cache), as_of=today)
    context = research_context(snapshot, cache, finances, today)
    found = {r['code']: r for r in (context or {}).get('snapshot', {}).get('companies', [])}
    previous = {t['code']: dict(opinion='편입', on=prior['created_on']) for t in (prior or {}).get('targets', [])}
    items = [dict(row=found.get(code) or dict(code=code, name=universe.get(code, {}).get('name', code)),
                  technical=(context or {}).get('research', {}).get('rows', {}).get(code, {}).get('technical'),
                  opinion=opinion, previous=previous.get(code)) for code, opinion in picked]
    report = review_report(items, today, mode=snapshot['meta']['data_mode'])
    out = Path(config['project_root']) / 'validation' / 'current' / 'review-reports' / today
    out.mkdir(parents=True, exist_ok=True)
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=1, allow_nan=False), encoding='utf-8')
    (out / 'report.md').write_text(report_markdown(report), encoding='utf-8')
    print(out.resolve())


if __name__ == '__main__':
    main()
