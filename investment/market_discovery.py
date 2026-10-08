"""Source-labelled public discovery, separate from the reviewed snapshot contract."""
from bisect import bisect_left, bisect_right
from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
import json
from statistics import mean

from .core import num
from .local_config import load_local
from .naver_universe import classify
from .market_history import benchmark_calendar, ADJUSTMENT_NOTE
from .workspace_research import METRICS, RS_LABEL
from .trend_diagnostics import diagnose, update_rank
from threading import RLock

# Discovery scope (user decision 2026-10-08): about 1,000 companies, fixed cap rule for stable daily membership.
MIN_DISCOVERY_CAP_EOK=1500


def discovery_cap(row,quote=None):
    if (quote and (quote.get('name'),quote.get('market'))==(row.get('name'),row.get('market'))
            and num(quote.get('market_cap_eok'))):return quote['market_cap_eok']
    return row.get('metrics',{}).get('market_cap_eok')


def discovery_candidate(row,quote=None):
    cap=discovery_cap(row,quote)
    return row.get('eligibility')=='candidate' and num(cap) and cap>MIN_DISCOVERY_CAP_EOK


def load_market_cache(root, snapshot):
    if snapshot['meta']['data_mode'] == 'fixture':
        return None
    local = load_local(root)
    folder = local['data_dir']/local['profile']/'market-expansion'
    try:
        universe = json.loads((folder/'universe.json').read_text(encoding='utf-8'))
        history = json.loads((folder/'histories.json').read_text(encoding='utf-8')) if (folder/'histories.json').exists() else {}
        if not isinstance(universe,dict) or not isinstance(universe.get('companies'),list) or any(not isinstance(r,dict) for r in universe['companies']) or universe.get('schema_version') != 'naver-universe-0.1':
            return None
        if not isinstance(history,dict) or any(not isinstance(history.get(k,{}),dict) for k in ('histories','benchmarks')) or any(not isinstance(r,dict) or not isinstance(r.get('prices',[]),list) for k in ('histories','benchmarks') for r in history.get(k,{}).values()):return None
        # Apply newly recognized exclusions to old caches without rewriting source data.
        for row in universe.get('companies', []):
            if row.get('eligibility') == 'candidate':
                classification = classify(row)
                if classification['eligibility'] == 'excluded':
                    row.update(classification)
        quotes = {}
        try:
            saved=json.loads((folder/'latest-quotes.json').read_text(encoding='utf-8'))
            if not isinstance(saved,dict) or not isinstance(saved.get('quotes',{}),dict):return None
            if saved.get('schema_version')=='market-quotes-0.1':quotes=saved
        except (OSError, ValueError, TypeError):
            pass
        return dict(universe=universe, history=history, quotes=quotes)
    except (OSError, ValueError, TypeError):
        return None


class MarketCacheReader:
    """One source-versioned runtime entry. Full histories are read-only internally.

    Detail callers receive a private copy of only their requested histories;
    whole-market builders already copy derived rows and must not edit source bars.
    """
    def __init__(self):
        self.lock=RLock();self.version=None;self.value=None

    def get(self,root,snapshot,*,codes=None):
        if snapshot['meta']['data_mode']=='fixture':return None
        cfg=load_local(root);folder=cfg['data_dir']/cfg['profile']/'market-expansion'
        def version():
            parts=[str(folder.resolve())]
            for name in ('universe.json','histories.json','latest-quotes.json'):
                path=folder/name
                try:
                    s=path.stat();parts.append((name,s.st_mtime_ns,s.st_size,s.st_ino))
                except FileNotFoundError:parts.append((name,None))
            return tuple(parts)
        try:
            with self.lock:
                observed=version()
                if self.version!=observed:
                    value=load_market_cache(root,snapshot)
                    if version()!=observed:
                        # A provider replaced a file during the read. Never mark
                        # mixed input as a reusable version or serve old data.
                        self.version=None;self.value=None;return None
                    self.value=value;self.version=observed
                if self.value is None:return None
                result=dict(universe=deepcopy(self.value['universe']),quotes=deepcopy(self.value['quotes']))
                history=self.value['history']
                if codes is None:result['history']=history
                else:result['history']=deepcopy(dict(history,histories={c:history.get('histories',{}).get(c,{}) for c in set(codes)}))
                return result
        except (OSError,ValueError,TypeError):return None


_runtime_market_reader=MarketCacheReader()
def read_market_cache(root,snapshot,*,codes=None):
    return _runtime_market_reader.get(root,snapshot,codes=codes)


def technical(record, benchmark, calendar, suspended=False, include_series=True):
    cutoff = calendar.get('valid_through')
    result = dict(status='unknown', reason='네이버 완료 일봉 253개와 지수 관측일 일치 필요',
        price_trend_status='unknown', price_trend_reason='가격 이력 확인 필요',
        source_note=ADJUSTMENT_NOTE, history_count=0, as_of=cutoff, series=[],suspended=suspended,
        sma={}, close=None, high_52w_close=None, gap_to_52w_high_pct=None,
        contraction=None, breakout=None, rs126_pct=None, rs252_pct=None,
        price_strength=dict(status='unknown', reason='253일 연속 관측과 유효 표본 필요',
            score=None, weighted_return_pct=None, venue='KRX', source_note=ADJUSTMENT_NOTE))
    if not record or record.get('kind') != 'item' or not cutoff:
        return result
    bars = record.get('prices', [])
    dates = [b.get('date') for b in bars]
    sessions = calendar['sessions']
    if (not bars or any(not isinstance(d, str) for d in dates) or dates != sorted(set(dates))
            or dates[-1] != cutoff or len(dates) > len(sessions) or dates != sessions[-len(dates):]
            or any(b.get('final') is not True or b.get('venue') != 'KRX'
                   or b.get('adjustment_basis') != 'naver_chart_adjusted'
                   or not num(b.get('close')) or b['close'] <= 0 for b in bars)):
        result['reason'] = '네이버 일봉 누락·기준일·가격 기준 확인 필요'
        return result
    closes = [b['close'] for b in bars]
    totals = [0]
    for value in closes:
        totals.append(totals[-1]+value)
    def average(i, n):
        return (totals[i+1]-totals[i+1-n])/n if i+1 >= n else None
    result.update(history_count=len(bars), close=closes[-1],
        sma={str(n): average(len(bars)-1, n) for n in (20, 50, 150, 200)},
        series=[dict(date=bars[i]['date'], close=closes[i],
            volume=bars[i].get('volume'), **{'ma'+str(n): average(i, n) for n in (20, 50, 150, 200)})
            for i in range(max(0, len(bars)-253), len(bars))] if include_series else [])
    lower = (date.fromisoformat(cutoff)-timedelta(weeks=52)).isoformat()
    if dates[0] <= lower:
        high = max(b['close'] for b in bars if b['date'] > lower)
        result['low_52w_close']=min(b['close'] for b in bars if b['date'] > lower)
        result.update(high_52w_close=high, gap_to_52w_high_pct=(closes[-1]/high-1)*100,
                      high_52w_reason='네이버 지수 관측일과 일치하는 직전 52주 종가 최고')
    if include_series:
        result['suspended']=suspended
        result['trend_analysis']=diagnose(bars,result)
    if len(bars) < 253:
        return result
    if suspended or bars[-1].get('no_trade') or bars[-1].get('volume') == 0:
        result.update(status='fail', reason='거래정지 또는 마지막 관측일 거래 없음', price_trend_status='fail')
        return result
    # Same-source benchmark/calendar validated as a whole before this function.
    bm = {b['date']: b['close'] for b in benchmark['prices']}
    q = [(closes[-1-63*i]/closes[-1-63*(i+1)]-1)*100 for i in range(4)]
    weighted = (2*q[0]+sum(q[1:]))/5
    result['price_strength'].update(weighted_return_pct=weighted, quarter_returns_pct=q,
        as_of=cutoff, formula='(최근 63일 수익률 × 2 + 앞선 세 분기 수익률) / 5')
    for n in (126, 252):
        result['rs'+str(n)+'_pct'] = ((closes[-1]/closes[-1-n]-1)-(bm[cutoff]/bm[dates[-1-n]]-1))*100
    s = result['sma']
    passed = (closes[-1] > s['50'] > s['150'] > s['200']
        and s['200'] > mean(closes[-220:-20]) and closes[-1] > closes[-127]
        and result['rs126_pct'] > 0)
    result.update(price_trend_status='pass' if passed else 'fail',
        price_trend_reason='가격 배열·200일선 상승·6개월 수익률·지수 초과수익 조건 '+('충족' if passed else '미충족'),
        status='unknown' if passed else 'fail',
        reason='가격 추세 조건 충족 · 거래대금 이력 미확인' if passed else '가격 추세 조건 미충족 · 거래대금 이력 미확인')
    return result


def build_discovery(analysis, research, cache, *, include_series=True):
    if not cache or analysis['meta']['data_mode'] == 'fixture':
        return None
    bundle = cache['universe']; histories = cache.get('history') or {}
    if bundle.get('schema_version') != 'naver-universe-0.1' or not isinstance(bundle.get('companies'), list):
        raise ValueError('시장 캐시 형식 확인 필요')
    source_rows = bundle['companies']
    if len(source_rows) > 10000 or len({r['code'] for r in source_rows}) != len(source_rows):
        raise ValueError('시장 캐시 중복/행수 오류')
    try:
        calendar = benchmark_calendar(histories.get('benchmarks', {}))
    except (ValueError, KeyError, TypeError):
        calendar = {}
    originals = {r['code']: r for r in analysis['companies']}
    rows = []; facts = {}; coverage = dict(total=len(source_rows),
        classifications=dict(Counter(r.get('eligibility', 'unknown') for r in source_rows)),
        listing_complete=bundle.get('pagination_complete', False), errors=len(bundle.get('errors', [])),
        history_errors=len(histories.get('errors', [])), retrieved_on=bundle.get('retrieved_on'))
    for source in source_rows:
        if source.get('eligibility') != 'candidate':
            continue
        row = {k: deepcopy(source.get(k)) for k in ('code','name','market','industry','security_type','analysis_profile','eligibility','classification_note')}
        row['metrics'] = {k: v if num(v) else None for k,v in source.get('metrics', {}).items()}
        quote=(cache.get('quotes') or {}).get('quotes',{}).get(row['code'])
        row['metrics']['market_cap_eok']=discovery_cap(source,quote)
        row['discovery_allowed']=discovery_candidate(source,quote)
        if (isinstance(quote,dict) and (quote.get('name'),quote.get('market'))==(row['name'],row['market'])
                and num(quote.get('price')) and quote['price']>0):
            row['latest_quote']=deepcopy(quote)
        row['legacy_available'] = False
        row['metric_details'] = {k: dict(source=source.get('source'), period=None, basis=None,
            observed_on=source.get('observed_on'), reason=source.get('derived_metrics', {}).get(k, source.get('metric_basis')),
            status='reference_only', price_date=None) for k in METRICS}
        own = originals.get(row['code'])
        if own and (own['name'],own['market']) == (row['name'],row['market']):
            row['legacy_available'] = True
            old = research['rows'].get(row['code'], {}).get('fundamental', {})
            for k in METRICS:
                value = old.get('metrics', {}).get(k)
                if num(value):
                    row['metrics'][k] = value
                    row['metric_details'][k] = dict(source='인포맥스 우선 저장자료', period=old.get('period'),
                        basis=old.get('basis'), observed_on=analysis['meta'].get('as_of'),
                        reason='기존 인포맥스 검토 수치 우선', status='reviewed', price_date=analysis['meta']['price_date'])
        row['valuation_details'] = {k: dict(row['metric_details'][k], value=row['metrics'].get(k)) for k in ('per','pbr')}
        record = histories.get('histories', {}).get(row['code'])
        if record and record.get('symbol') != row['code']:
            record = None
        t = technical(record, histories.get('benchmarks', {}).get(row['market']), calendar,
            suspended=source.get('trading_status', {}).get('tradeStopYn') == 'Y', include_series=include_series)
        metric_facts = {k: row['metrics'].get(k) for k in METRICS}
        facts[row['code']] = dict(fundamental=dict(metrics=metric_facts, metric_details=row['metric_details'],
            period=None, basis=None, notes=['지표별 출처·기간을 확인하세요. 네이버 목록 재무 요약의 기간·연결/별도는 미명시.']),
            technical=t, events=research['rows'].get(row['code'], {}).get('events', []))
        rows.append(row)
    market_by_code = {r['code']: r['market'] for r in rows}
    population_by_market = Counter(r['market'] for r in rows)
    scores_by_market = {market: sorted(facts[code]['technical']['price_strength']['weighted_return_pct']
        for code in facts if market_by_code[code] == market
        and num(facts[code]['technical']['price_strength']['weighted_return_pct']))
        for market in ('KOSPI', 'KOSDAQ')}
    for code, f in facts.items():
        s = f['technical']['price_strength']; value = s['weighted_return_pct']
        market = market_by_code[code]; scores = scores_by_market[market]
        s.update(eligible_count=len(scores), universe_count=population_by_market[market], market=market)
        if num(value) and len(scores) >= 5:
            s.update(score=min(99.99, 100*(bisect_left(scores,value)+bisect_right(scores,value))/2/len(scores)),
                status='ready', reason=f'네이버 제공 조정 차트·{market} 지수 공통 관측일·동일 시장 순위 기준')
        if f['technical'].get('trend_analysis'):update_rank(f['technical']['trend_analysis'],s['score'])
    score_count = sum(map(len, scores_by_market.values()))
    coverage.update(candidates=len(rows), rs_ready=score_count,
        rs_ready_by_market={k: len(v) for k,v in scores_by_market.items()},
        metrics={k:sum(num(r['metrics'].get(k)) for r in rows) for k in METRICS},
        both_valuation=sum(all(num(r['metrics'].get(k)) and r['metrics'][k] > 0 for k in ('per','pbr')) for r in rows),
        price_trend_pass=sum(f['technical']['price_trend_status']=='pass' for f in facts.values()))
    coverage['discovery_candidates']=sum(r['discovery_allowed'] for r in rows)
    coverage['cap_excluded']=len(rows)-coverage['discovery_candidates']
    note = (f"네이버 공개 목록 {coverage['total']:,}개 중 시가총액 {MIN_DISCOVERY_CAP_EOK:,}억원 초과 탐색 대상 {coverage['discovery_candidates']:,}개 · 조회 {bundle.get('retrieved_on')} · "
            f"일봉 {calendar.get('valid_through', '미확보')} · 동일 시장 순위 유효 {score_count:,}개. "
            '재무 기간·연결/별도 미명시 수치는 발굴 참고용이며, 기존 인포맥스 수치가 있으면 우선합니다.')
    return dict(snapshot=dict(meta=dict(discovery=True, discovery_note=note, data_mode=analysis['meta']['data_mode'],
        price_date=calendar.get('valid_through'), retrieved_on=bundle.get('retrieved_on')), companies=rows),
        research=dict(rows=facts, rs_label=RS_LABEL), coverage=coverage)
