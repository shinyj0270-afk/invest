"""Versioned project hypotheses, not Hanwha formula reproduction or prediction."""
from statistics import median
import hashlib
from pathlib import Path
from .core import num,ratio,cagr,continuous,select_vintage,percentile,eligible,combine,digest

MODEL='korean-paths-0.4.1'
PATHS=('turnaround','domestic','substitution','technology','returns')
NAMES=dict(zip(PATHS,('턴어라운드','내수 성장','수입대체','기술(Long Hedge)','주주환원')))
REFERENCE_ID='HANWHA_100X_USER_MD_20260107'
REFERENCE_PATH=Path(__file__).resolve().parents[1]/'references/100배의_기술_한화리서치.md'
CONFIG={'weights':{'Q':.30,'G':.25,'C':.20,'V':.15,'B':.10},'path_order':PATHS,'rounds':2,'cross_quarters':13}

def status(v): return 'unknown' if v is None else 'pass' if v else 'fail'

def financial_signals(rows,as_of):
    a=select_vintage(rows,as_of)
    def sums(end,n):
        part=a[:end] if end is not None else a
        if not continuous(part,n): return None,None
        w=part[-n:]
        if not all(num(r.get('revenue')) and num(r.get('op')) for r in w): return None,None
        return sum(r['revenue'] for r in w),sum(r['op'] for r in w)
    r4,e4=sums(None,4); r12,e12=sums(None,12)
    p4,pe4=sums(-1,4); p12,pe12=sums(-1,12); y4,ye4=sums(-4,4)
    op1=ratio(e4,r4,100); op3=ratio(e12,r12,100)
    prev1=ratio(pe4,p4,100); prev3=ratio(pe12,p12,100); year1=ratio(ye4,y4,100)
    growth=ratio(r4,y4)
    return dict(opm1=op1,opm3=op3,g_sales=growth-1 if growth is not None else None,
        delta_opm=op1-year1 if op1 is not None and year1 is not None else None,
        cross_up=(op1>op3 and prev1<=prev3) if None not in (op1,op3,prev1,prev3) else None,
        profit_turn=(e4>0 and pe4<=0) if None not in (e4,pe4) else None,
        profit_positive=e4>0 if e4 is not None else None,
        quarter=a[-1]['period_end'] if a else None,available_at=a[-1]['available_at'] if a else None)

def annual_signals(rows,as_of):
    a=select_vintage(rows,as_of)
    out=dict(g_sales=None,g_op=None,g_dps=None,dividend_start=False,returns_signal=None)
    if not continuous(a,4,annual=True): return out
    x,y=a[-4],a[-1]
    for field,key in [('revenue','g_sales'),('op','g_op'),('dps','g_dps')]:
        if all(num(r.get(field)) for r in a[-4:]): out[key]=cagr(x[field],y[field],3)
    if not all(r.get('dps_basis') and r.get('dps_basis')==y.get('dps_basis') for r in a[-4:]): out['g_dps']=None
    out['dividend_start']=x.get('dps')==0 and num(y.get('dps')) and y['dps']>0
    gs,go,gd=(out[k] for k in ('g_sales','g_op','g_dps'))
    out['returns_signal']=gs>=0 and gs<go<gd and gd>0 if None not in (gs,go,gd) else None
    out['special_dividend']=y.get('special_dividend','unknown')
    return out

def evidence_status(row,path,as_of):
    items=[e for e in row.get('evidence',[]) if e.get('path')==path and
        all(e.get(k) and e[k]<=as_of for k in ('available_at','first_seen_at','reviewed_at')) and
        e['available_at']<=e['reviewed_at']]
    if any(e.get('review_status')=='counter' for e in items): return 'counter'
    if any(e.get('review_status')=='confirmed' and e.get('document') and e.get('location') and e.get('summary') and
           (path!='returns' or e.get('execution') in ('paid_dividend','executed_buyback','cancelled_shares')) for e in items): return 'confirmed'
    if any(e.get('review_status')=='inaccessible' for e in items): return 'inaccessible'
    return 'pending'

def quality_factors(row,as_of):
    a=select_vintage(row.get('annual',[]),as_of)
    factors=dict(Q=None,G=None,C=None,V=None,B=None)
    if continuous(a,4,annual=True):
        roics=[]; cash=[]
        for prev,cur in zip(a[-4:-1],a[-3:]):
            vals=[r.get(k) for r in (prev,cur) for k in ('equity','debt','cash')]
            tax=cur.get('effective_tax_rate')
            if all(num(v) for v in vals) and num(tax) and 0<=tax<=1 and cur.get('tax_verified') and num(cur.get('op')):
                avg=((prev['equity']+prev['debt']-prev['cash'])+(cur['equity']+cur['debt']-cur['cash']))/2
                v=ratio(cur['op']*(1-tax),avg)
                if v is not None: roics.append(v)
            c=ratio(cur.get('ocf'),cur.get('revenue'))
            if c is not None: cash.append(c)
        factors['Q']=median(roics) if len(roics)==3 else None
        factors['C']=median(cash) if len(cash)==3 else None
        factors['G']=cagr(a[-4].get('revenue'),a[-1].get('revenue'),3)
    eps=row['metrics'].get('eps_ttm'); price=row['metrics'].get('price')
    factors['V']=ratio(eps,price) if num(eps) and eps>0 and row.get('valuation_basis') else None
    debt=row['metrics'].get('net_debt_equity_pct')
    factors['B']=-debt/100 if num(debt) else None
    return factors

def analyze(snapshot):
    as_of=snapshot['meta']['price_date']; results=[]
    reference_hash=hashlib.sha256(REFERENCE_PATH.read_bytes()).hexdigest() if REFERENCE_PATH.exists() else None
    for row in snapshot['companies']:
        if not eligible(row): continue
        s=financial_signals(row.get('quarters',[]),as_of); a=annual_signals(row.get('annual',[]),as_of)
        gs,dm=s['g_sales'],s['delta_opm']
        signals=dict(turnaround=s['cross_up'],domestic=(gs>0 and dm>0) if None not in (gs,dm) else None,
                     substitution=gs>0 if gs is not None else None,technology=s['profit_turn'],returns=a['returns_signal'])
        paths={}
        for p in PATHS:
            ev=evidence_status(row,p,as_of); sig=status(signals[p])
            sort=(a['g_dps'],a['g_op']-a['g_sales'] if None not in (a['g_op'],a['g_sales']) else None) if p=='returns' else (gs,dm)
            paths[p]=dict(signal_status=sig,evidence_status=ev,eligible=sig=='pass' and ev=='confirmed' and all(num(x) for x in sort),sort=sort,
                reason='정식 연구 후보' if sig=='pass' and ev=='confirmed' else '수치 신호 / 경로 확인 대기' if sig=='pass' else '자료 부족' if sig=='unknown' else '수치 조건 미충족')
        stages=[e for e in row.get('stages',[]) if e.get('available_at','9999')<=as_of and e.get('first_seen_at','9999')<=as_of]
        results.append(dict(code=row['code'],name=row['name'],industry=row['industry'],signals=s,annual=a,paths=paths,
            factors=quality_factors(row,as_of),quality_score=None,S_long=None,stage_tags=stages,
            persistence=row.get('data_quality',[]),model=MODEL,snapshot_id=digest(snapshot),config_hash=digest(CONFIG),
            reference_id=REFERENCE_ID,reference_file_hash=reference_hash,as_of_date=as_of))
    weights={'Q':.30,'G':.25,'C':.20,'V':.15,'B':.10}
    for r in results:
        ps={k:percentile(r['factors'][k],[v['factors'][k] for v in results],1) for k in weights}
        r['quality_missing']=[k for k,v in r['factors'].items() if v is None]
        if all(v is not None for v in ps.values()): r['quality_score']=r['S_long']=100*sum(weights[k]*ps[k] for k in weights)
    return results

def balanced_list(results):
    pools={p:sorted([r for r in results if r['paths'][p]['eligible']],key=lambda r:(-r['paths'][p]['sort'][0],-r['paths'][p]['sort'][1],r['code'])) for p in PATHS}
    chosen=[]; seen=set()
    for _ in range(2):
        for p in PATHS:
            r=next((r for r in pools[p] if r['code'] not in seen),None)
            if r:
                seen.add(r['code']); chosen.append(dict(code=r['code'],name=r['name'],selected_path=p,tags=[k for k in PATHS if r['paths'][k]['eligible']]))
    return chosen
