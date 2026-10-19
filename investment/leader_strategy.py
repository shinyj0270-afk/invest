"""Stored public-company coordinates, not orders or portfolio weights."""
import json
from pathlib import Path
from collections import defaultdict,Counter
from statistics import mean,pstdev
from bisect import bisect_left,bisect_right
from .core import num
from .industry_phase import validated_prices

ROOT=Path(__file__).resolve().parents[1]
METRICS=('per','pbr','pcr','ev_ebitda')

def load_config(path=None):
    c=json.loads(Path(path or ROOT/'config/leader_strategy.json').read_text(encoding='utf-8'))
    if not isinstance(c,dict):raise ValueError('leader config object')
    if type(c.get('version')) is not int or c['version']!=1:raise ValueError('leader version')
    for k in ('window','momentum_lag','min_members'):
        if type(c.get(k)) is not int or not 1<=c[k]<=1000:raise ValueError(k)
    if not all(num(c.get(k)) for k in ('winsor_tail','size_floor','z_threshold','value_tail_pct')):raise ValueError('leader thresholds')
    if not 0<=c['winsor_tail']<.5 or not 0<c['size_floor']<=1 or not 0<c['z_threshold']<=10 or not 0<c['value_tail_pct']<50:raise ValueError('leader bounds')
    if c.get('size_adjustment') not in ('divide_raw','multiply_z','none'):raise ValueError('size method')
    if c['momentum_lag']<c['window']:raise ValueError('lag')
    return c

def raw_features(record,t,cutoff,c):
    ps=validated_prices(record,t,cutoff);w=c['window'];lag=c['momentum_lag']
    if len(ps)<lag+w:return {},'완료 가격·거래 이력 부족 또는 기준 불일치/정지'
    now=ps[-w:];prior=ps[-lag-w:-lag];previous=ps[-2*w:-w]
    required=now+prior+previous
    if any(not num(p.get('volume')) or p['volume']<=0 or p.get('no_trade') for p in required):return {},'비교 구간 거래량 미확보·0·거래 없음'
    def vwap(values):return sum(p['close']*p['volume'] for p in values)/sum(p['volume'] for p in values)
    exact=all(num(p.get('turnover')) and p['turnover']>0 for p in now+previous)
    def turnover(values):return sum(p['turnover'] if exact else p['close']*p['volume'] for p in values)
    return dict(momentum_pct=(vwap(now)/vwap(prior)-1)*100,turnover_change_pct=(turnover(now)/turnover(previous)-1)*100,
        turnover_method='stored_turnover' if exact else 'adjusted_close_volume_proxy'),''

def quantile(values,q):
    a=sorted(values);pos=(len(a)-1)*q;i=int(pos)
    return a[i]+(a[min(i+1,len(a)-1)]-a[i])*(pos-i)

def standardize(values,caps,c):
    if len(values)<c['min_members']:return [None]*len(values)
    lo,hi=min(caps),max(caps)
    sizes=[c['size_floor']+(1-c['size_floor'])*(cap-lo)/(hi-lo) if hi>lo else 1 for cap in caps]
    adjusted=[v/s if c['size_adjustment']=='divide_raw' else v for v,s in zip(values,sizes)]
    lower,upper=quantile(adjusted,c['winsor_tail']),quantile(adjusted,1-c['winsor_tail'])
    clipped=[max(lower,min(upper,v)) for v in adjusted];avg=mean(clipped);sigma=pstdev(clipped)
    if sigma<=1e-12:return [None]*len(values)
    return [(v-avg)/sigma*(s if c['size_adjustment']=='multiply_z' else 1) for v,s in zip(clipped,sizes)]

def band(value,threshold):return '미확인' if not num(value) else '상' if value>=threshold else '하' if value<=-threshold else '중'

def percentile(v,pool):return (bisect_left(pool,v)+bisect_right(pool,v))/2/len(pool)*100

def valuation_key(row,key,cutoff):
    value=row.get('metrics',{}).get(key);d=row.get('metric_details',{}).get(key,{})
    if not num(value) or value<=0 or d.get('status') not in ('calculated','estimated','reviewed','reference_with_tolerance'):return None
    if not d.get('period') or d.get('basis') not in ('CFS','OFS') or d.get('price_date')!=cutoff:return None
    return (row['market'],d['period'],d['basis'],d.get('currency','KRW'),cutoff)

def build(discovery,cache,config=None):
    try:c=config if config is not None else load_config()
    except (OSError,ValueError,KeyError,TypeError):return dict(status='invalid',reason='주도주 전략 설정 확인 필요',rows=[],markets=[])
    result=dict(status='ready',config=c,rows=[],markets=[],source_note='SK증권 2025-04-30 보고서(사용자 제공 자료, 공개 URL 미확인)',
        definition='저장 관측값의 자체 근사 분류 · 매수 추천·투자 판단 아님 · HRP/자동 주문 없음')
    if not discovery:return dict(result,status='pending',reason='시장 탐색 가격·재무 자료 미확보')
    cutoff=discovery['snapshot']['meta']['price_date'];result['as_of']=cutoff
    source=[r for r in discovery['snapshot']['companies'] if r.get('discovery_allowed') is True];facts=discovery['research']['rows']
    histories=(cache or {}).get('history',{}).get('histories',{});by_code={r['code']:r for r in source}
    for row in source:
        t=facts.get(row['code'],{}).get('technical',{});raw,reason=raw_features(histories.get(row['code']),t,cutoff,c)
        cap=row.get('metrics',{}).get('market_cap_eok')
        if not num(cap) or cap<=0:reason='양수 시가총액 미확보'
        result['rows'].append(dict(code=row['code'],name=row['name'],market=row['market'],industry=row.get('industry','산업 미분류'),
            market_cap_eok=cap,**raw,reason=reason,momentum_z=None,turnover_z=None,momentum_band='미확인',turnover_band='미확인',value_band='미확인',value_score=None,value_metrics=[],candidate=False))
    for market in ('KOSPI','KOSDAQ'):
        population=[r for r in result['rows'] if r['market']==market];valid=[r for r in population if not r['reason']]
        for raw_key,out_key in (('momentum_pct','momentum_z'),('turnover_change_pct','turnover_z')):
            zs=standardize([r[raw_key] for r in valid],[r['market_cap_eok'] for r in valid],c)
            for row,z in zip(valid,zs):row[out_key]=z
        for r in valid:
            r['momentum_band']=band(r['momentum_z'],c['z_threshold']);r['turnover_band']=band(r['turnover_z'],c['z_threshold'])
            if r['momentum_band']=='미확인' or r['turnover_band']=='미확인':r['reason']='시장별 유효 표본 부족 또는 상수 분포'
    pools=defaultdict(list);keys={}
    for r in result['rows']:
        original=by_code[r['code']]
        for key in METRICS:
            group=valuation_key(original,key,cutoff)
            if group:keys[r['code'],key]=group;pools[group+(key,)].append(original['metrics'][key])
    pools={k:sorted(v) for k,v in pools.items()}
    value_groups=defaultdict(list)
    for r in result['rows']:
        groups=defaultdict(list)
        for key in METRICS:
            group=keys.get((r['code'],key));pool=pools.get(group+(key,),[]) if group else []
            if len(pool)>=c['min_members']:groups[group].append((key,100-percentile(by_code[r['code']]['metrics'][key],pool)))
        eligible=[(g,vs) for g,vs in groups.items() if len(vs)>=2]
        if not eligible:continue
        group,vs=sorted(eligible,key=lambda x:(-len(x[1]),x[0]))[0]
        r['value_score']=mean(v for k,v in vs);r['value_metrics']=[k for k,v in vs];r['value_period']=group[1];r['value_basis']=group[2];r['value_currency']=group[3]
        value_groups[group].append(r)
    for group,rs in value_groups.items():
        if len(rs)<c['min_members']:continue
        pool=sorted(r['value_score'] for r in rs)
        for r in rs:
            rank=percentile(r['value_score'],pool);r['value_percentile']=rank
            r['value_band']='저평가' if rank>=100-c['value_tail_pct'] else '고평가' if rank<=c['value_tail_pct'] else '중립'
    for r in result['rows']:
        r['candidate']=not r['reason'] and r['momentum_band']=='상' and r['turnover_band']=='상' and r['value_band']=='중립'
        if not r['reason'] and r['value_band']=='미확인':r['reason']='비교 가능한 양수 가치지표 2개·동일 기간 표본 미확보'
    for market in ('KOSPI','KOSDAQ'):
        rs=[r for r in result['rows'] if r['market']==market];classified=[r for r in rs if r['momentum_band']!='미확인' and r['turnover_band']!='미확인']
        result['markets'].append(dict(market=market,population=len(rs),classified=len(classified),missing=len(rs)-len(classified),candidates=sum(r['candidate'] for r in rs),
            cells={a+'|'+b:sum(r['momentum_band']==a and r['turnover_band']==b for r in classified) for a in ('상','중','하') for b in ('상','중','하')},
            value_bands=dict(Counter(r['value_band'] for r in rs))))
    return result
