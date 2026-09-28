"""Additional formulas only from sufficient, explicitly normalized observations."""
from .core import select_vintage,continuous,ttm,cagr,ratio,num

def current_history(row,snapshot):
    """Opt-in descriptive view of today's historical extract, not an as-of vintage."""
    history=row.get('observed_financial_history',{})
    if (snapshot['meta']['data_mode']!='user_input' or history.get('scope')!='current_observation'
        or history.get('basis')!='CFS' or history.get('income_basis')!='standalone_quarters'
        or not history.get('observed_on') or history['observed_on']>snapshot['meta']['as_of']):
        return None
    for kind in ('annual','quarters'):
        records=history.get(kind,[])
        if not records or any(r['period_end']>history['observed_on'] for r in records): return None
        if not continuous(records,len(records),annual=kind=='annual'): return None
    return history


def additional(row,snapshot,include_current_history=False):
    as_of=snapshot['meta']['price_date']; annual=select_vintage(row.get('annual',[]),as_of)
    quarters=select_vintage(row.get('quarters',[]),as_of)
    m={}; reasons={}
    for n in (3,5):
        key=f'revenue_cagr_{n}y_pct'
        v=cagr(annual[-n-1].get('revenue'),annual[-1].get('revenue'),n) if continuous(annual,n+1,True) else None
        m[key]=v*100 if v is not None else None
    for field,label in [('revenue','revenue_ttm_eok'),('op','op_ttm_eok'),('parent_income','parent_income_ttm_eok')]:
        v=ttm(quarters,field); m[label]=v/1e8 if v is not None else None
    latest=annual[-1] if annual else {}
    m['fcf_proxy_eok']=(latest['ocf']-latest['capex'])/1e8 if num(latest.get('ocf')) and num(latest.get('capex')) and latest['capex']>=0 else None
    history=current_history(row,snapshot) if include_current_history else None
    if history:
        # Current-history metrics are displayed with their own retrieval date in the app.
        observed_annual=history['annual']; observed_quarters=history['quarters']
        for n in (3,5):
            v=cagr(observed_annual[-n-1].get('revenue'),observed_annual[-1].get('revenue'),n) if continuous(observed_annual,n+1,True) else None
            m[f'revenue_cagr_{n}y_pct']=v*100 if v is not None else None
        for field,label in [('revenue','revenue_ttm_eok'),('op','op_ttm_eok'),('parent_income','parent_income_ttm_eok')]:
            v=ttm(observed_quarters,field); m[label]=v/1e8 if v is not None else None
    # 5/60-day flow contracts require explicit same-venue, finalized raw daily rows.
    dates=[d for d in snapshot.get('sessions',[]) if d<=as_of]
    prices={p['date']:p for p in row.get('prices',[]) if p['date']<=as_of}
    flows={p['date']:p for p in row.get('flows',[]) if p['date']<=as_of}
    for n in (5,60):
        window=dates[-n:]
        for prefix in ('foreign','institution'):
            k=f'{prefix}_net_{n}d_eok'; pct=f'{prefix}_net_turnover_{n}d_pct'; m[k]=m[pct]=None
            if len(window)!=n or not all(d in prices and d in flows for d in window): continue
            if not all(prices[d].get('final') and flows[d].get('final') and prices[d].get('venue') and prices[d]['venue']==flows[d].get('venue') for d in window): continue
            vals=[flows[d].get(prefix+'_net_won') for d in window]; ts=[prices[d].get('turnover') for d in window]
            if all(num(v) for v in vals):
                m[k]=sum(vals)/1e8
                if all(num(v) and v>=0 for v in ts): m[pct]=ratio(sum(vals),sum(ts),100)
    for k,v in m.items():
        if v is None: reasons[k]='동일 기준·공개 시점의 연속 원자료 또는 확정·거래소·단위 확인 부족'
    return m,reasons
