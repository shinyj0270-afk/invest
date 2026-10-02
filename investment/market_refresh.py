"""User-triggered daily price refresh; promote only a validated complete update."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
from threading import Lock, Thread
import time
from uuid import uuid4
from zoneinfo import ZoneInfo

from .local_config import load_local
from .market_history import fetch_history, benchmark_calendar, completed_cutoff
from .naver_universe import fetch_listing


def write_json(path, value):
    temp = path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def collect_quotes(folder, progress, *, fetch=fetch_listing):
    """One explicit latest-price observation; never replace completed daily bars."""
    folder = Path(folder)
    original = json.loads((folder/'universe.json').read_text(encoding='utf-8'))
    result = fetch(progress=lambda p: progress(dict(completed=p.get('loaded', 0), total=0)))
    if not result.get('pagination_complete') or result.get('errors'):
        raise ValueError('quote_listing_incomplete')
    index = {r['code']: r for r in result['companies']}
    quotes = {}
    missing = 0
    for row in original['companies']:
        if row.get('eligibility') != 'candidate':
            continue
        fresh = index.get(row['code'])
        if not fresh or (fresh['name'], fresh['market']) != (row['name'], row['market']):
            missing += 1
            continue
        price = fresh.get('metrics', {}).get('price')
        if not isinstance(price, (float, int)) or isinstance(price, bool) or price <= 0:
            missing += 1
            continue
        quotes[row['code']] = dict(code=row['code'], name=row['name'], market=row['market'],
            price=price, change_pct=fresh['metrics'].get('change_pct'),
            market_cap_eok=fresh['metrics'].get('market_cap_eok'),
            retrieved_at=fresh['retrieved_at'], source=fresh['source'], final=False,
            price_time=None, note='네이버 공개 목록 제공가격 · 시세시각·지연 미확인 · 조회시각은 체결시각이 아닙니다.')
    if not quotes:
        raise ValueError('no_valid_quotes')
    write_json(folder/'latest-quotes.json',dict(schema_version='market-quotes-0.1',
        retrieved_at=result['retrieved_at'], quotes=quotes, missing=missing))
    return dict(status='complete', retrieved_at=result['retrieved_at'],
                updated_companies=len(quotes), failed=missing, message='최신 제공 가격 조회 완료')


def collect_daily(folder, progress, *, fetch=fetch_history, now=None, pace=.15, skip_unchanged=False):
    folder = Path(folder)
    now = now or datetime.now(ZoneInfo('Asia/Seoul'))
    end = completed_cutoff(now,True).isoformat()
    universe = json.loads((folder/'universe.json').read_text(encoding='utf-8'))
    old = json.loads((folder/'histories.json').read_text(encoding='utf-8'))
    if universe.get('schema_version') != 'naver-universe-0.1' or not universe.get('pagination_complete'):
        raise ValueError('시장 목록 확인 필요')
    rows = [r for r in universe['companies'] if r.get('eligibility') == 'candidate']
    codes = [r['code'] for r in rows]
    if not codes or len(codes) > 10000 or len(set(codes)) != len(codes):
        raise ValueError('invalid_universe')
    old_calendar = benchmark_calendar(old['benchmarks'])
    if old_calendar['valid_through'] > end:
        raise ValueError('future_cache')

    def get(symbol, kind, previous):
        first = old['start'] if previous is None else max(old['start'],
            (datetime.fromisoformat(previous['price_date']).date()-timedelta(days=7)).isoformat())
        time.sleep(pace)
        recent = fetch(symbol, kind=kind, start=first, end=end,
                       cache_dir=folder/'history', now=now, force=True,allow_same_day=True)
        if recent['symbol'] != symbol or recent['kind'] != kind:
            raise ValueError('identity_mismatch')
        if previous is None:
            return recent
        prior_prices = {p['date']: p['close'] for p in previous['prices']}
        if any(p['date'] in prior_prices and p['close'] != prior_prices[p['date']] for p in recent['prices']):
            # Split adjustments or corrections may also change the older price scale.
            # Re-read the full series instead of joining two incompatible price bases.
            time.sleep(pace)
            recent = fetch(symbol, kind=kind, start=old['start'], end=end,
                           cache_dir=folder/'history', now=now, force=True,allow_same_day=True)
            if recent['symbol'] != symbol or recent['kind'] != kind or recent['price_date'] < previous['price_date']:
                raise ValueError('corrected_series_invalid')
            return recent
        # Keep source evidence for the older segment; the new response replaces overlap.
        result = deepcopy(recent)
        result['prices'] = [p for p in previous['prices'] if p['date'] < first] + recent['prices']
        result['source_segments'] = deepcopy(previous.get('source_segments', [previous['source']])) + [recent['source']]
        if result['price_date'] < previous['price_date']:
            raise ValueError('price_date_regression')
        return result

    benchmarks = {s: get(s, 'index', old['benchmarks'].get(s)) for s in ('KOSPI', 'KOSDAQ')}
    calendar = benchmark_calendar(benchmarks)
    target = calendar['valid_through']
    if target < old_calendar['valid_through']:
        raise ValueError('calendar_regression')
    progress(dict(total=len(rows), completed=0, failed=0, target_date=target))
    if skip_unchanged and target == old_calendar['valid_through'] and not old.get('errors'):
        return dict(status='complete', target_date=target, updated_companies=0, failed=0,
                    message='새 완료 거래일 없음')
    result = dict(schema_version='market-history-bundle-0.1', start=old['start'], end=end,
                  benchmarks=benchmarks, calendar=calendar, histories={}, errors=[])
    successes = 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(get, c, 'item', old.get('histories', {}).get(c)): c for c in codes}
        for count, future in enumerate(as_completed(futures), 1):
            code = futures[future]
            try:
                record = future.result()
                dates = [p['date'] for p in record['prices']]
                if dates != sorted(set(dates)) or dates != calendar['sessions'][-len(dates):]:
                    raise ValueError('incomplete_sessions')
                result['histories'][code] = record
                successes += 1
            except Exception:
                result['errors'].append(dict(code=code, reason='완료 일봉 조회 또는 검증 실패'))
                if code in old.get('histories', {}):
                    result['histories'][code] = deepcopy(old['histories'][code])
            progress(dict(total=len(rows), completed=count, failed=len(result['errors']), target_date=target))
    # Failed companies keep their old observations; the display withholds mixed-date RS.
    if not successes:
        raise ValueError('existing_history_failed')
    temp = folder/('histories.'+uuid4().hex+'.tmp')
    try:
        temp.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding='utf-8')
        temp.replace(folder/'histories.json')
    finally:
        temp.unlink(missing_ok=True)
    return dict(status='complete', target_date=target, updated_companies=successes,
                failed=len(result['errors']), message='일별 가격 저장 완료')


class DailyMarketRefresh:
    def __init__(self, root, *, collector=collect_daily, kind='daily'):
        self.root, self.collector = root, collector
        self.kind = kind
        self.last_attempt = 0
        self.lock = Lock()
        self.state = dict(status='idle', completed=0, total=0, failed=0)

    def poll(self):
        with self.lock:
            return deepcopy(self.state)

    def start(self):
        with self.lock:
            if self.state['status'] == 'running':
                return deepcopy(self.state)
            self.state = dict(status='running', completed=0, total=0, failed=0)
            self.last_attempt = time.monotonic()
            Thread(target=self._run, daemon=True).start()
            return deepcopy(self.state)

    def ensure_due(self):
        """Called on page open and while its status is polled; no OS schedule."""
        if self.kind != 'daily':
            return self.poll()
        if self.poll()['status'] == 'running' or self.last_attempt and time.monotonic()-self.last_attempt < 1800:
            return self.poll()
        try:
            cfg=load_local(self.root)
            folder=cfg['data_dir']/cfg['profile']/'market-expansion'
            day=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
            stamp=folder/'daily-refresh-status.json'
            if stamp.exists():
                saved=json.loads(stamp.read_text(encoding='utf-8'))
                required=completed_cutoff(datetime.now(ZoneInfo('Asia/Seoul')),True).isoformat()
                if saved.get('checked_on') == day and saved.get('requested_end')==required and not saved.get('failed') and saved.get('target_date')==required:
                    if self.poll()['status']=='idle':self._progress(saved)
                    return self.poll()
        except (OSError, ValueError, KeyError):
            pass
        return self.start()

    def _progress(self, values):
        with self.lock:
            self.state.update(values)

    def _run(self):
        lease = None
        try:
            cfg = load_local(self.root)
            folder = cfg['data_dir']/cfg['profile']/'market-expansion'
            folder.mkdir(parents=True, exist_ok=True)
            lease = folder/(self.kind+'-refresh.lock')
            try:
                with lease.open('x', encoding='utf-8') as stream:
                    stream.write(datetime.now(ZoneInfo('Asia/Seoul')).isoformat())
            except FileExistsError:
                lease = None
                self._progress(dict(status='failed', message='다른 일별 가격 갱신이 진행 중이거나 이전 실행 점검이 필요합니다. 기존 자료를 유지합니다.'))
                return
            checked_on=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
            result = self.collector(folder, self._progress)
            if self.kind=='daily':
                result['checked_on']=checked_on
                result['requested_end']=completed_cutoff(datetime.now(ZoneInfo('Asia/Seoul')),True).isoformat()
                write_json(folder/'daily-refresh-status.json',result)
            self._progress(result)
        except Exception:
            self._progress(dict(status='failed', message='가격 조회·검증 실패 · 기존 자료 유지. 연결 상태와 시장 캐시를 확인하고 다시 시도하세요.'))
        finally:
            if lease is not None:
                lease.unlink(missing_ok=True)
