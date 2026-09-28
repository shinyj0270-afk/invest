import math
from statistics import mean,pstdev
from .core import num,percentile,eligible,combine

MODEL='trend-research-0.4.1'

def calculate(row,benchmark,sessions,as_of,min_turnover=1e9):
    bars=[b for b in (row.get('trend_prices') or row.get('prices',[])) if b['date']<=as_of]
    bm={b['date']:b for b in benchmark if b['date']<=as_of}
    expected=[d for d in sessions if d<=as_of]
    result=dict(code=row['code'],name=row['name'],status='unknown',reason='253개 동일 거래일·조정 OHLCV·벤치마크 필요',rs126=None,rs252=None,score=None,model=MODEL,contraction=None,breakout=None)
    if row.get('suspended'): return dict(result,status='fail',reason='거래정지')
    if row.get('trend_prices') and (not bars or bars[-1]['date']!=as_of):
        return dict(result,reason='추세 시세가 현재 가격일보다 오래됨 · 재조회 필요')
    if len(bars)<253 or len(expected)<253 or [b['date'] for b in bars[-253:]]!=expected[-253:]: return result
    bars=bars[-253:]
    if any(b['date'] not in bm for b in bars): return result
    price_venue=row.get('trend_price_venue') if row.get('trend_prices') else row.get('price_venue')
    if any(b.get('adjustment_basis')!='split_adjusted' or b.get('venue')!=price_venue or not b.get('venue') for b in bars): return result
    if any(bm[b['date']].get('adjustment_basis')!='split_adjusted' for b in bars): return result
    if not all(num(b.get(k)) and b[k]>0 for b in bars for k in ('close','high','low','volume')): return result
    if not all(num(b.get('turnover')) and b['turnover']>=0 for b in bars[-20:]): return result
    if not all(num(bm[b['date']].get('close')) and bm[b['date']]['close']>0 for b in bars): return result
    p=[b['close'] for b in bars]; volumes=[b['volume'] for b in bars]
    sma={n:mean(p[-n:]) for n in (50,150,200)}
    returns={n:p[-1]/p[-1-n]-1 for n in (126,252)}
    rs={n:returns[n]-(bm[bars[-1]['date']]['close']/bm[bars[-1-n]['date']]['close']-1) for n in (126,252)}
    flags=[p[-1]>sma[50]>sma[150]>sma[200],sma[200]>mean(p[-220:-20]),returns[126]>0,rs[126]>0,mean(b['turnover'] for b in bars[-20:])>=min_turnover]
    logret=[math.log(y/x) for x,y in zip(p,p[1:])]; vol60=pstdev(logret[-60:]); volratio=pstdev(logret[-20:])/vol60 if vol60>0 else None
    span=(max(b['high'] for b in bars[-20:])-min(b['low'] for b in bars[-20:]))/p[-1]
    vr=mean(volumes[-5:])/mean(volumes[-50:])
    contraction=volratio<.7 and span<.15 and vr<.7 if volratio is not None else None
    breakout=p[-1]>max(b['high'] for b in bars[-21:-1]) and volumes[-1]/mean(volumes[-21:-1])>=1.5
    return dict(result,status='pass' if all(flags) else 'fail',reason='조건 충족' if all(flags) else '추세/상대수익/거래대금 조건 미충족',
        sma=sma,r126=returns[126],rs126=rs[126],rs252=rs[252],contraction=contraction,breakout=breakout,
        volatility_ratio=volratio,range_ratio=span,volume_ratio=vr)

def analyze(snapshot,min_turnover=1e9):
    rows=[calculate(r,snapshot.get('benchmarks',{}).get(r['market'],[]),
        snapshot['meta'].get('trend_sessions',snapshot.get('sessions',[])) if r.get('trend_prices') else snapshot.get('sessions',[]),
        snapshot['meta']['price_date'],min_turnover) for r in snapshot['companies'] if eligible(r)]
    for r in rows:
        ps=[percentile(r[k],[v[k] for v in rows],1) for k in ('rs126','rs252')]
        if all(v is not None for v in ps): r['score']=100*(.6*ps[0]+.4*ps[1])
    return sorted(rows,key=lambda r:(r['score'] is None,-(r['score'] or 0),r['code']))
