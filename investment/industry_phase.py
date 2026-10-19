"""Own fixed price phases. Stored observations only; no collection or persistence."""
import json
from collections import Counter,defaultdict,deque
from datetime import date,timedelta
from pathlib import Path
from statistics import median
from .core import num

ROOT=Path(__file__).resolve().parents[1]
PHASES=('생','왕','쇠','사','미확인')

def load_config(path=None):
    c=json.loads(Path(path or ROOT/'config/industry_phase.json').read_text(encoding='utf-8'))
    if not isinstance(c,dict):raise ValueError('phase config object')
    if type(c.get('version')) is not int or c['version']!=1:raise ValueError('phase version')
    for k in ('ma_fast','ma_slow','breakout_days','high_weeks','alert_days','min_members'):
        if type(c.get(k)) is not int or not 1<=c[k]<=1000:raise ValueError(k)
    if not c['ma_fast']<c['ma_slow'] or c.get('priority') not in ('birth_first','risk_first'):raise ValueError('phase priority/windows')
    if not all(num(c.get(k)) for k in ('weak_drawdown_pct','dead_drawdown_pct')) or not 0<c['weak_drawdown_pct']<c['dead_drawdown_pct']<100:raise ValueError('drawdown')
    return c

def validated_prices(record,t,cutoff):
    ps=(record or {}).get('prices',[])
    if not ps or not num(t.get('close')) or t.get('as_of')!=cutoff or t.get('suspended') or t.get('price_health',{}).get('status')!='ready':return []
    try:
        dates=[p['date'] for p in ps]
        if dates!=sorted(set(dates)) or dates[-1]!=cutoff or ps[-1]['close']!=t['close']:return []
        for p in ps:
            if date.fromisoformat(p['date']).isoformat()!=p['date'] or not num(p.get('close')) or p['close']<=0 or p.get('final') is not True or p.get('venue')!='KRX' or p.get('adjustment_basis')!='naver_chart_adjusted':return []
        if ps[-1].get('no_trade') or ps[-1].get('volume')==0:return []
    except (ValueError,KeyError,TypeError):return []
    return ps

def classify(close,fast,slow,high,breakout,armed,c):
    drawdown=(high-close)/high*100
    birth=armed and breakout
    dead=drawdown>c['dead_drawdown_pct']+1e-10 or fast<slow
    weak=drawdown>=c['weak_drawdown_pct']-1e-10 or close<fast
    if birth and c['priority']=='birth_first':return '생'
    if dead:return '사'
    if weak:return '쇠'
    if birth:return '생'
    return '왕' if fast>slow and drawdown<=c['weak_drawdown_pct'] else '미확인'

def trajectory(ps,c,technical=None):
    if not ps:return []
    out=[];totals=[0];highs=deque();breaks=deque();armed=False
    for i,p in enumerate(ps):
        close=p['close'];day=date.fromisoformat(p['date']);lower=(day-timedelta(weeks=c['high_weeks'])).isoformat()
        totals.append(totals[-1]+close)
        while highs and ps[highs[0]]['date']<=lower:highs.popleft()
        while highs and ps[highs[-1]]['close']<=close:highs.pop()
        highs.append(i)
        while breaks and breaks[0]<i-c['breakout_days']:breaks.popleft()
        breakout=i>=c['breakout_days'] and breaks and close>ps[breaks[0]]['close']
        enough=i+1>=c['ma_slow'] and ps[0]['date']<=lower
        phase='미확인'
        if enough and not p.get('no_trade') and p.get('volume')!=0:
            fast=(totals[-1]-totals[i+1-c['ma_fast']])/c['ma_fast'];slow=(totals[-1]-totals[i+1-c['ma_slow']])/c['ma_slow']
            if i==len(ps)-1 and technical:
                fast=technical.get('sma',{}).get(str(c['ma_fast'])) if num(technical.get('sma',{}).get(str(c['ma_fast']))) else fast
                slow=technical.get('sma',{}).get(str(c['ma_slow'])) if num(technical.get('sma',{}).get(str(c['ma_slow']))) else slow
            phase=classify(close,fast,slow,ps[highs[0]]['close'],bool(breakout),armed,c)
            if phase=='사':armed=True
            elif phase=='생':armed=False
        else:armed=False
        out.append(dict(date=p['date'],phase=phase,close=close))
        while breaks and ps[breaks[-1]]['close']<=close:breaks.pop()
        breaks.append(i)
    return out

def episodes(path):
    """Completed known-phase growth runs → first weak/dead entry, in trading bars."""
    events=[];start=peak=None;previous='미확인'
    for i,p in enumerate(path):
        state=p['phase']
        if state in ('생','왕'):
            if previous not in ('생','왕'):
                start=i if previous in ('쇠','사') else None;peak=i
            if peak is not None and p['close']>=path[peak]['close']:peak=i
        elif previous in ('생','왕') and state in ('쇠','사') and start is not None and peak is not None:
            if peak>start:events.append(dict(start=path[start]['date'],peak=path[peak]['date'],entry=p['date'],rise_days=peak-start,fall_days=i-peak,entry_phase=state))
            start=peak=None
        elif state=='미확인':start=peak=None
        previous=state
    return events

def build(discovery,cache,config=None):
    try:c=config if config is not None else load_config()
    except (OSError,ValueError,TypeError,KeyError):return dict(status='invalid',reason='국면 설정 확인 필요',rows={},sectors=[],hypothesis_c={'status':'pending','count':0})
    result=dict(status='ready',config=c,definition='자체 고정 관측 규칙 · 학습 엔진 재현·주도산업 판정 아님',rows={},sectors=[])
    groups=defaultdict(list);all_events=[]
    if not discovery:return dict(result,status='pending',hypothesis_c={'status':'pending','count':0})
    cutoff=discovery['snapshot']['meta']['price_date'];facts=discovery['research']['rows']
    histories=(cache or {}).get('history',{}).get('histories',{})
    for r in discovery['snapshot']['companies']:
        if r.get('discovery_allowed') is not True:continue
        t=facts.get(r['code'],{}).get('technical',{});ps=validated_prices(histories.get(r['code']),t,cutoff)
        path=trajectory(ps,c,t);phase=path[-1]['phase'] if path else '미확인'
        entries=[p['date'] for i,p in enumerate(path) if i>=len(path)-c['alert_days'] and i>0 and p['phase']=='쇠' and path[i-1]['phase'] not in ('쇠','미확인')]
        member=dict(phase=phase,as_of=cutoff,reason='저장 완료 종가·이동평균의 자체 규칙' if phase!='미확인' else '가격 이력 부족·기준 미충족·조건 미해당',recent_weak=bool(entries),weak_entry_dates=entries)
        result['rows'][r['code']]=member;groups[r['market'],r.get('industry','산업 미분류')].append((r,member))
        all_events.extend(dict(e,market=r['market']) for e in episodes(path))
    for (market,industry),members in sorted(groups.items()):
        valid=[(r,p) for r,p in members if p['phase']!='미확인'];caps=[(r,p) for r,p in valid if num(r.get('metrics',{}).get('market_cap_eok')) and r['metrics']['market_cap_eok']>0]
        total=sum(r['metrics']['market_cap_eok'] for r,p in caps);g=dict(market=market,industry=industry,eligible=len(valid),missing=len(members)-len(valid),rankable=len(valid)>=c['min_members'],counts=dict(Counter(p['phase'] for r,p in valid)),cap_eligible=len(caps),recent_weak=sum(p['recent_weak'] for r,p in members))
        for key,states in (('growth',('생','왕')),('decline',('쇠','사'))):
            count=sum(p['phase'] in states for r,p in valid);weight=sum(r['metrics']['market_cap_eok'] for r,p in caps if p['phase'] in states)
            g[key]=dict(count=count,pct=count/len(valid)*100 if valid else None,cap_eok=weight,cap_total_eok=total,cap_pct=weight/total*100 if total else None)
        result['sectors'].append(g)
    def summarize(events):
        return dict(count=len(events),rise_median=median(e['rise_days'] for e in events) if events else None,
            fall_median=median(e['fall_days'] for e in events) if events else None,shorter_count=sum(e['fall_days']<e['rise_days'] for e in events))
    result['hypothesis_c']=dict(status='descriptive' if all_events else 'pending',**summarize(all_events),
        by_market={m:summarize([e for e in all_events if e['market']==m]) for m in ('KOSPI','KOSDAQ')},
        definition='관측 가능한 쇠/사→생/왕 구간 시작부터 구간 최고종가까지와 그 고점→첫 쇠/사까지의 거래일. 좌측 검열·미완료·상승기간0 제외. 반복 종목 사건이며 독립 표본·가설 입증 아님')
    return result
