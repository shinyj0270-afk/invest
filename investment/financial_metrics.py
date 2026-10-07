"""One dated metric contract shared by discovery and company summaries."""
from copy import deepcopy
from datetime import date
from .core import num, ratio
from .financial_table import valid_day

KEYS=('operating_margin_pct','revenue_growth_pct','roe_pct','debt_ratio_pct','per','pbr')


def metric_provenance(dependencies):
    cells=[]
    for column,field in dependencies:
        provenance=column.get('cell_provenance',{}).get(field)
        if provenance is None:
            provenance=dict(source=column.get('source'),available_at=column.get('available_at'),source_url=column.get('source_url'),receipt=column.get('receipt'))
        observed=provenance.get('available_at')
        cells.append(dict(field=field,period=column['period_end'],source=provenance.get('source'),
            available_at=observed if valid_day(observed) else None,publication_status='recorded' if valid_day(observed) else 'unknown',
            source_url=provenance.get('source_url'),receipt=provenance.get('receipt')))
    known=[c['available_at'] for c in cells if c['available_at']]
    unknown=any(c['publication_status']=='unknown' for c in cells)
    return dict(observed_on=None if unknown or not known else max(known),publication_status='unknown' if unknown or not known else 'recorded',
        dependencies=cells,filing_dependency_dates=sorted(set(known)),sources=sorted({c['source'] for c in cells if c.get('source')}))

def contiguous(columns):
    if len(columns)!=4:return False
    if any(c.get('calendar_segment') for c in columns):
        from .fiscal_contract import contiguous_quarters
        return contiguous_quarters(columns)
    months=[]
    for c in columns:
        d=date.fromisoformat(c['period_end'])
        import calendar
        if d.month not in (3,6,9,12) or d.day!=calendar.monthrange(d.year,d.month)[1]:return False
        months.append(d.year*12+d.month)
    return all(b-a==3 for a,b in zip(months,months[1:]))

def common_metrics(row, table, technical=None, basis='CFS'):
    qs=next((g['columns'] for g in table.get('groups',[]) if g['basis']==basis and g['cadence']=='quarter'),[])
    if not qs and basis=='CFS':
        basis='OFS'
        qs=next((g['columns'] for g in table.get('groups',[]) if g['basis']==basis and g['cadence']=='quarter'),[])
    if not qs:
        return deepcopy((table.get('native_financial') or {}).get('common_financial'))
    latest=qs[-1];end=latest['period_end'];v=latest['statement_values']
    from .native_financial import prior_quarter
    prior=prior_quarter(latest,qs)
    book='parent_equity' if basis=='CFS' else 'equity';profit='parent_net' if basis=='CFS' else 'net_income'
    four=qs[-4:];complete=contiguous(four)
    ttm={k:sum(c['statement_values'][k] for c in four) if complete and all(num(c['statement_values'].get(k)) for c in four) else None for k in ('revenue','operating_profit',profit,'ocf')}
    avg=(v[book]+prior['statement_values'][book])/2 if prior and num(v.get(book)) and num(prior['statement_values'].get(book)) else None
    metrics=dict(operating_margin_pct=ratio(v.get('operating_profit'),v.get('revenue'),100),
        revenue_growth_pct=ratio(v.get('revenue')-prior['statement_values']['revenue'],prior['statement_values']['revenue'],100) if prior and num(v.get('revenue')) and num(prior['statement_values'].get('revenue')) else None,
        roe_pct=ratio(ttm[profit],avg,100),debt_ratio_pct=ratio(v.get('liabilities'),v.get('equity'),100),per=None,pbr=None)
    # Rounded market capitalization is not verified ordinary share count.
    quote=row.get('latest_quote') or {};cap=quote.get('market_cap_eok');quote_price=quote.get('price')
    close=(technical or {}).get('close');price_date=(technical or {}).get('as_of')
    cap_date=(quote.get('retrieved_at') or '')[:10]
    age=(date.fromisoformat(cap_date)-date.fromisoformat(price_date)).days if valid_day(cap_date) and valid_day(price_date) else None
    if latest.get('currency','KRW')=='KRW' and all(num(x) and x>0 for x in (cap,quote_price,close)) and age is not None and 0<=age<=3:
        estimated_cap=cap/quote_price*close
        metrics.update(per=ratio(estimated_cap,ttm[profit]),pbr=ratio(estimated_cap,v.get(book)))
    details={}
    for k,value in metrics.items():
        approximate=k in ('per','pbr')
        details[k]=dict(value=value,period=end,basis=basis,price_date=price_date if approximate else None,
            observed_on=latest.get('available_at') or latest.get('filing_available_at'),source=latest['source'],shares_date=cap_date if approximate else None,
            status='missing' if value is None else 'estimated' if approximate else 'calculated',
            reason=('시총/제공가격으로 추정한 주식수('+cap_date+') · 완료 종가 적용 · 주식수 불변 가정/권리변동 미검증 · '+('지배주주 기준 근사' if basis=='CFS' else '별도 순이익·자본 기준 근사') if approximate else
                ('TTM 지배순이익 / 전년동기·현재 평균 지배자본' if basis=='CFS' else '별도 TTM 순이익 / 전년동기·현재 평균 자본') if k=='roe_pct' else '단독분기 전년동기 대비' if k=='revenue_growth_pct' else ('같은 기간 연결 재무 원자료 계산' if basis=='CFS' else '같은 기간 별도 재무 원자료 계산')) if value is not None else '같은 기간 원자료·4개 연속분기·지배주주 계정 또는 동일 날짜 가격/시총 대기')
    dependencies={
        'operating_margin_pct':[(latest,k) for k in ('operating_profit','revenue')],
        'revenue_growth_pct':[(c,'revenue') for c in [latest]+([prior] if prior else [])],
        'roe_pct':[(c,profit) for c in four]+[(c,book) for c in [latest]+([prior] if prior else [])],
        'debt_ratio_pct':[(latest,k) for k in ('liabilities','equity')],
        'per':[(c,profit) for c in four], 'pbr':[(latest,book)]}
    for key,used in dependencies.items():
        details[key].update(metric_provenance(used),currency=latest.get('currency','KRW'))
    if latest.get('cell_notes',{}).get('revenue'):
        for key in ('operating_margin_pct','revenue_growth_pct'):details[key]['reason']+=' · '+latest['cell_notes']['revenue']
    for key,columns,fields in [('roe_pct',four+[latest]+([prior] if prior else []),[profit,book]),
                               ('per',four,[profit]),('pbr',[latest],[book])]:
        notes=sorted({c.get('cell_notes',{}).get(field) for c in columns for field in fields
                      if c.get('cell_notes',{}).get(field)})
        if notes and metrics[key] is not None:
            details[key]['within_tolerance']=True
            if details[key]['status']=='calculated':details[key]['status']='reference_with_tolerance'
            details[key]['reason']+=' · '+' · '.join(notes)
    amounts={k:v.get(k) for k in ('revenue','operating_profit','net_income','total_borrowings','balance_debt')}
    return dict(basis=basis,period=end,currency=latest.get('currency','KRW'),
        **{k:latest[k] for k in ('fiscal_year','fiscal_quarter','year_end_month','calendar_segment') if k in latest},
        metrics=metrics,metric_details=details,amounts=amounts,ttm_complete=complete,ttm_ocf=ttm['ocf'],financial_completeness=table.get('financial_completeness'),source_urls=sorted(set(c.get('source_url') for c in four+[latest]+([prior] if prior else []) if c.get('source_url'))))

def apply_common(row, facts, common):
    """Reviewed provider metrics only retain priority at the exact common basis/date."""
    if not common:return
    f=facts.setdefault('fundamental',{});existing=f.get('metric_details',{})
    result=deepcopy(common)
    for k,d in result['metric_details'].items():
        old=existing.get(k) or row.get('metric_details',{}).get(k,{})
        if old.get('status')=='reviewed' and old.get('currency','KRW')==result.get('currency','KRW') and str(old.get('period',''))[:10]==result['period'] and old.get('basis')==result['basis'] and (k not in ('per','pbr') or old.get('price_date')==d['price_date']):
            value=row.get('metrics',{}).get(k)
            if num(value):result['metrics'][k]=value;result['metric_details'][k]=dict(old,value=value)
    row.setdefault('metrics',{}).update(result['metrics']);row.setdefault('metric_details',{}).update(result['metric_details'])
    row['common_financial']=result
    f.setdefault('metrics',{}).update(result['metrics']);f.setdefault('metric_details',{}).update(result['metric_details']);f.update(period=result['period'],basis=result['basis'])
    row['valuation_details']={k:dict(result['metric_details'][k],value=result['metrics'][k]) for k in ('per','pbr')}
