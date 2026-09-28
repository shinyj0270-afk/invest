import csv
import hashlib
import io
import json
import math
import operator
import re
from datetime import date
from statistics import median

OPS = {'gte': operator.ge, 'lte': operator.le, 'gt': operator.gt, 'lt': operator.lt, 'eq': operator.eq}

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()

def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)

def ratio(a, b, scale=1):
    return a / b * scale if num(a) and num(b) and b > 0 else None

def cagr(a, b, years):
    return (b/a)**(1/years)-1 if num(a) and num(b) and min(a,b)>0 and years>0 else None

def combine(states, logic='AND'):
    if logic not in ('AND','OR'): raise ValueError('AND/OR 필요')
    if not states: return 'pass'
    return ('fail' if 'fail' in states else 'unknown' if 'unknown' in states else 'pass') if logic=='AND' else ('pass' if 'pass' in states else 'unknown' if 'unknown' in states else 'fail')

def evaluate(row, rules, logic='AND'):
    states=[]
    for rule in rules:
        if rule.get('op') not in OPS or not num(rule.get('value')): raise ValueError('잘못된 조건')
        v=row['metrics'].get(rule['metric'])
        states.append('unknown' if not num(v) else 'pass' if OPS[rule['op']](v,rule['value']) else 'fail')
    return combine(states,logic),states

def eligible(row):
    return row['market'] in ('KOSPI','KOSDAQ') and row['security_type']=='ordinary' and row['analysis_profile']=='nonfinancial'

def percentile(v, values, minimum=5):
    a=[x for x in values if num(x)]
    return (sum(x<v for x in a)+0.5*sum(x==v for x in a))/len(a) if num(v) and len(a)>=minimum else None

def peers(snapshot, row, codes=None):
    return [r for r in snapshot['companies'] if eligible(r) and
        (r['code'] in codes if codes is not None else r['industry']==row['industry']) and
        r.get('financial_basis',snapshot['meta']['financial_basis'])==row.get('financial_basis',snapshot['meta']['financial_basis']) and
        r.get('financial_period',snapshot['meta']['financial_period'])==row.get('financial_period',snapshot['meta']['financial_period'])]

def validate_snapshot(s):
    def reject_secrets(obj):
        if isinstance(obj,dict):
            if any(k.lower() in ('password','api_key','appkey','secretkey','access_token','authorization','crtfc_key') for k in obj): raise ValueError('스냅샷에 인증정보 저장 금지')
            for v in obj.values(): reject_secrets(v)
        elif isinstance(obj,list):
            for v in obj: reject_secrets(v)
    reject_secrets(s)
    if s.get('schema_version')!='0.1' or not isinstance(s.get('companies'),list): raise ValueError('스냅샷 계약 0.1 필요')
    if len(s['companies'])>10000: raise ValueError('종목 수 제한')
    m=s['meta']
    if m.get('data_mode') not in ('fixture','user_input','live'): raise ValueError('자료 모드 필요')
    for k in ('price_date','flow_start','flow_end'): date.fromisoformat(m[k])
    if m['flow_start']>m['flow_end'] or m['flow_end']>m['price_date']: raise ValueError('시점 역전')
    if m['financial_basis'] not in ('CFS','OFS'): raise ValueError('회계 기준 필요')
    seen=set()
    for r in s['companies']:
        code=r.get('code','')
        if not re.fullmatch(r'\d{6}',code) or code in seen: raise ValueError('종목코드/중복 오류')
        seen.add(code)
        for k in ('name','market','industry','security_type','analysis_profile'):
            if not isinstance(r.get(k),str) or not r[k]: raise ValueError('종목 메타데이터 누락')
        if any(v is not None and not num(v) for v in r['metrics'].values()): raise ValueError('유한 숫자/null 필요')
        for k in ('financial_basis','financial_period'):
            if k in r and r[k]!=m[k]: raise ValueError('혼합 보고기간/회계 기준')
    digest(s)
    return s

def safe_csv(rows):
    if not rows: return '\ufeff'
    stream=io.StringIO(); writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
    writer.writeheader()
    for r in rows:
        writer.writerow({k: ("'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v) for k,v in r.items()})
    return '\ufeff'+stream.getvalue()

def select_vintage(records, as_of):
    """Only explicitly available records; latest known revision per period."""
    chosen={}
    for r in records:
        available=r.get('available_at')
        if not available or available>as_of or r['period_end']>as_of: continue
        key=(r['period_end'],r.get('basis','CFS'))
        if key not in chosen or available>chosen[key]['available_at']: chosen[key]=r
    return sorted(chosen.values(),key=lambda x:x['period_end'])

def quarterly(records, field, as_of, cumulative=False, balance=False):
    rows=select_vintage(records,as_of); result=[]; previous={}
    for r in rows:
        d=date.fromisoformat(r['period_end']); q=(d.month-1)//3+1
        v=r.get(field); key=(d.year,r.get('basis','CFS'))
        value=v
        if cumulative and not balance and q>1:
            p=previous.get(key)
            value=v-p[1] if p and p[0]==q-1 and num(v) and num(p[1]) else None
        previous[key]=(q,v)
        result.append(dict(r,**{field:value}))
    return result

def continuous(rows,n,annual=False):
    if len(rows)<n: return False
    a=rows[-n:]
    if any(r['period_end'][5:] not in (('12-31',) if annual else ('03-31','06-30','09-30','12-31')) for r in a): return False
    if len({r.get('basis','CFS') for r in a})!=1: return False
    ids=[date.fromisoformat(r['period_end']).year if annual else date.fromisoformat(r['period_end']).year*4+(date.fromisoformat(r['period_end']).month-1)//3 for r in a]
    return all(b-a==1 for a,b in zip(ids,ids[1:]))

def ttm(rows,field):
    return sum(r[field] for r in rows[-4:]) if continuous(rows,4) and all(num(r.get(field)) for r in rows[-4:]) else None

def valuation(snapshot,row,minimum=5):
    eps=row['metrics'].get('eps_ttm'); pool=peers(snapshot,row)
    values=sorted(r['metrics']['per'] for r in pool if r['code']!=row['code'] and num(r['metrics'].get('per')) and r['metrics']['per']>0 and r.get('valuation_basis')==row.get('valuation_basis') and row.get('valuation_basis'))
    if not num(eps) or eps<=0 or len(values)<minimum: return {'reason':'양의 검증 EPS·동일 기준 대상 제외 피어 5개 이상 필요','scenarios':None,'peer_count':len(values)}
    def quant(p):
        pos=(len(values)-1)*p; lo=int(pos); return values[lo]+(values[min(lo+1,len(values)-1)]-values[lo])*(pos-lo)
    return dict(scenarios=[eps*quant(p) for p in (.25,.5,.75)], multiples=[quant(p) for p in (.25,.5,.75)],peer_count=len(values),reason='상대가치 시나리오 · 미래 확률/목표가 아님')
