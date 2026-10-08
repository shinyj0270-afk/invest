"""Same-date observed market breadth, short RS and explicit price reconciliation."""
from bisect import bisect_left,bisect_right
from collections import defaultdict
from .core import num

WINDOWS={'1m':21,'3m':63,'6m':126}

def percentile(value,pool):
    if not num(value) or len(pool)<5:return None
    return min(99.99,100*(bisect_left(pool,value)+bisect_right(pool,value))/2/len(pool))

def enrich_market(discovery, cache):
    if not discovery:return None
    rows=discovery['snapshot']['companies'];facts=discovery['research']['rows'];histories=(cache or {}).get('history',{}).get('histories',{})
    pools=defaultdict(list);valid=[]
    rows=[r for r in rows if r['code'] in facts]
    for row in rows:
        t=facts[row['code']]['technical'];record=histories.get(row['code']) or {};ps=record.get('prices',[])
        t['price_health']=dict(status='ready' if num(t.get('close')) else 'stale' if ps else 'missing',
            observed_on=ps[-1]['date'] if ps else None,required_on=t.get('as_of'),
            reason='원천 완료 일봉·공통 관측일 대조' if num(t.get('close')) else '기준일·공통 관측일·가격 기준 미충족; 기존 자료 보존')
        usable=num(t.get('close')) and ps and not ps[-1].get('no_trade') and ps[-1].get('volume')!=0 and not t.get('suspended')
        t['short_rs']={}
        for key,n in WINDOWS.items():
            value=(ps[-1]['close']/ps[-1-n]['close']-1)*100 if usable and len(ps)>n else None
            t['short_rs'][key]=dict(return_pct=value,score=None,days=n,market=row['market'],as_of=t.get('as_of'))
            if value is not None:pools[(row['market'],key)].append(value)
        if usable:valid.append(row)
    pools={k:sorted(v) for k,v in pools.items()}
    for row in rows:
        for key,s in facts[row['code']]['technical']['short_rs'].items():
            pool=pools.get((row['market'],key),[]);s.update(score=percentile(s['return_pct'],pool),eligible_count=len(pool))
    markets=[]
    for market in ('KOSPI','KOSDAQ'):
        population=[r for r in rows if r['market']==market];vs=[r for r in valid if r['market']==market]
        above={}
        for n in ('50','200'):
            ts=[facts[r['code']]['technical'] for r in vs if num(facts[r['code']]['technical']['sma'].get(n))]
            above[n]=dict(count=sum(t['close']>t['sma'][n] for t in ts),eligible=len(ts),pct=100*sum(t['close']>t['sma'][n] for t in ts)/len(ts) if ts else None)
        adv=sum(histories[r['code']]['prices'][-1]['close']>histories[r['code']]['prices'][-2]['close'] for r in vs if len(histories[r['code']]['prices'])>1)
        decl=sum(histories[r['code']]['prices'][-1]['close']<histories[r['code']]['prices'][-2]['close'] for r in vs if len(histories[r['code']]['prices'])>1)
        bm=(cache or {}).get('history',{}).get('benchmarks',{}).get(market,{}).get('prices',[])
        last=bm[-1]['close'] if bm else None;ma200=sum(p['close'] for p in bm[-200:])/200 if len(bm)>=200 else None
        breadth=above['200']['pct']
        status='자료 대기' if breadth is None or ma200 is None else '양호' if last>ma200 and breadth>=50 else '주의' if last>ma200 or breadth>=50 else '방어 검토'
        markets.append(dict(market=market,as_of=discovery['snapshot']['meta']['price_date'],population=len(population),valid=len(vs),above=above,advancing=adv,declining=decl,status=status,
            definition='자체 참고 국면: 지수>200일선 및 관측기업 과반>200일선이면 양호; 둘 중 하나면 주의. 전체 시장·수급 판정 아님'))
    groups=defaultdict(list)
    for r in valid:
        if r.get('discovery_allowed'):groups[(r['market'],r['industry'])].append(r)
    sectors=[]
    for (market,industry),members in groups.items():
        shorts={}
        for key in WINDOWS:
            ms=[r for r in members if num(facts[r['code']]['technical']['short_rs'][key]['return_pct']) and num(r['metrics'].get('market_cap_eok')) and r['metrics']['market_cap_eok']>0]
            weight=sum(r['metrics']['market_cap_eok'] for r in ms)
            value=sum(r['metrics']['market_cap_eok']*facts[r['code']]['technical']['short_rs'][key]['return_pct'] for r in ms)/weight if weight else None
            shorts[key]=dict(return_pct=value,score=percentile(value,pools.get((market,key),[])) if len(ms)>=5 else None,count=len(ms),cap_eok=weight)
        sectors.append(dict(market=market,industry=industry,count=len(members),short_rs=shorts))
    return dict(markets=markets,sectors=sectors,definition='21/63/126 완료 거래일 수익률의 같은 거래소 저장 유효 기업 내 백분위. 업종은 시총1,500억원 초과 유효기업의 현재 시총 가중 수익률을 같은 분포에 대조; 5개 미만 업종 순위 대기. 투자 가능한 업종지수·총수익률 아님')

def reconcile_prices(row, record, references=()):
    ps={p['date']:p for p in (record or {}).get('prices',[])};checks=[]
    observations=[dict(date=p.get('date'),price=p.get('close'),venue=p.get('venue'),basis=p.get('adjustment_basis'),source='인포맥스/검토 저장 이력') for p in row.get('prices',[])]+list(references)
    for obs in observations:
        p=ps.get(obs.get('date'));price=obs.get('price')
        if not p or not num(price) or price<=0:continue
        same=bool(obs.get('venue') and obs.get('basis') and obs.get('venue')==p.get('venue') and obs.get('basis')==p.get('adjustment_basis'))
        gap=(p['close']/price-1)*100
        checks.append(dict(date=obs['date'],left_price=price,right_price=p['close'],difference_pct=gap,
            comparable=same,status='일치' if same and abs(gap)<1e-9 else '차이 확인' if same else '기준 대조 필요',
            left_source=obs.get('source'),left_venue=obs.get('venue'),left_basis=obs.get('basis'),
            right_source='네이버 공개 차트',right_venue=p.get('venue'),right_basis=p.get('adjustment_basis')))
    return dict(checks=checks[-8:],source=(record or {}).get('source'),note='같은 날짜라도 거래시장·시각·권리변동 보정 기준이 달라질 수 있습니다. 대조값으로 분석 종가를 자동 교체하지 않습니다. 고가와 최고종가는 별도 지표입니다.')
