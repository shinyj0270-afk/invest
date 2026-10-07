"""Small, dated view models for reviewed company detail. No retrieval or writes."""
from datetime import date, timedelta
from .core import num
from .financial_table import valid_day
from .portfolio_risk import time_series


def chart_history(row, snapshot, cache=None):
    cutoff = snapshot['meta']['price_date']
    # Financial availability can be today while the last completed price is yesterday.
    # Use the independently validated common index session for chart completeness.
    if cache:
        from .market_history import benchmark_calendar
        try:
            calendar=benchmark_calendar((cache.get('history') or {}).get('benchmarks',{}))
            cutoff=min(cutoff,calendar['valid_through'])
        except (ValueError,KeyError,TypeError):pass
    record = ((cache or {}).get('history') or {}).get('histories', {}).get(row['code'])
    source = '저장 가격 이력'
    bars = row.get('trend_prices') or row.get('prices') or []
    if record and record.get('kind') == 'item' and record.get('symbol') == row['code']:
        bars = record.get('prices', [])
        source = '네이버 저장 수정 일봉 · KRX · 인포맥스 가격과 별도 출처'
    # Duplicates, ambiguous adjustment or invalid ordering invalidate the whole series.
    dates = [p.get('date') for p in bars]
    if (not bars or any(not valid_day(d) for d in dates) or dates != sorted(set(dates))
            or len({p.get('adjustment_basis') for p in bars}) != 1
            or any(p.get('final') is not True or not p.get('venue')
                   or p.get('adjustment_basis') in (None, '', 'unknown', 'unverified')
                   or not num(p.get('close')) or p['close'] <= 0 for p in bars)):
        return dict(bars=[], benchmark=[], source=source, reason='확정 가격·날짜·거래소·수정 기준이 확인된 이력 필요')
    result=[]
    for p in bars:
        if p['date'] > cutoff: continue
        ohlc = (all(num(p.get(k)) and p[k] > 0 for k in ('open','high','low'))
                and p['low'] <= min(p['open'],p['close']) <= max(p['open'],p['close']) <= p['high'])
        result.append(dict(date=p['date'],close=p['close'],
            **{k:p[k] if ohlc else None for k in ('open','high','low')},
            volume=p.get('volume') if num(p.get('volume')) and p['volume'] >= 0 else None))
    bm = ((cache or {}).get('history') or {}).get('benchmarks', {}).get(row['market'], {}).get('prices', [])
    if not bm:
        bm = snapshot.get('benchmarks', {}).get(row['market'], [])
    benchmark=[dict(date=p['date'],close=p['close']) for p in bm
               if valid_day(p.get('date')) and p['date'] <= cutoff and num(p.get('close')) and p['close'] > 0]
    bd=[p['date'] for p in benchmark]
    if bd != sorted(set(bd)): benchmark=[]
    lower=(date.fromisoformat(cutoff)-timedelta(weeks=52)).isoformat()
    window=[p['close'] for p in result if p['date'] > lower]
    # A range spanning 52 weeks still needs every observed benchmark session.
    expected=[d for d in bd if lower < d <= cutoff]
    actual=[p['date'] for p in result if lower < p['date'] <= cutoff]
    complete=bool(result and result[0]['date'] <= lower and result[-1]['date']==cutoff
                  and expected and expected==actual)
    return dict(bars=result,benchmark=benchmark,source=source,as_of=result[-1]['date'] if result else None,
        time_series=time_series(bars,bm,cutoff),
        low_52w=min(window) if complete else None, high_52w=max(window) if complete else None,
        reason='종가 기준 52주 범위' if complete else '52주 전체 이력 또는 기준일 가격 미확보')


def build_details(snapshot, tables, cache=None):
    result={}
    for r in snapshot['companies']:
        groups=tables[r['code']]['groups']
        # FinancialTable has already checked identity, availability, periods and duplicates.
        statement_groups=[dict(id=g['id'],basis=g['basis'],cadence=g['cadence'],columns=[
            dict(period_end=c['period_end'],available_at=c['available_at'],source=c['source'],
                 source_url=c.get('source_url'),receipt=c.get('receipt'),
                 filing_available_at=c.get('filing_available_at'),
                 values=c['statement_values'],cell_notes=c['cell_notes'],
                 **{k:c[k] for k in ('period_start','fiscal_year','fiscal_quarter','year_end_month','calendar_segment','currency','cell_provenance','dependencies','dependency_dates') if k in c}) for c in g['columns']]) for g in groups]
        dividends=[dict(period_end=a['period_end'],dps=a['dps'],source='저장 연간 자료')
            for a in r.get('annual',[]) if valid_day(a.get('period_end')) and a['period_end'] <= snapshot['meta']['price_date']
            and valid_day(a.get('available_at')) and a['available_at'] <= snapshot['meta']['price_date']
            and a.get('basis')==snapshot['meta']['financial_basis'] and num(a.get('dps'))
            and a['dps'] >= 0 and a.get('dps_basis')=='ordinary_split_adjusted' and a.get('special_dividend') is False]
        result[r['code']]=dict(code=r['code'],name=r['name'],market=r['market'],
            chart=chart_history(r,snapshot,cache),groups=statement_groups,dividends=dividends,
            notes=tables[r['code']]['notes'],
            financial_completeness=tables[r['code']].get('financial_completeness'),
            native_financial=tables[r['code']].get('native_financial'))
        from .market_insights import reconcile_prices
        record=((cache or {}).get('history') or {}).get('histories',{}).get(r['code'])
        result[r['code']]['price_audit']=reconcile_prices(r,record)
    return result
