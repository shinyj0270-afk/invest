"""Transparent research allocation within explicit user concentration bounds."""
from math import sqrt,nextafter
from statistics import stdev, mean
from .portfolio_risk import common_window, checked, numeric

RECOMMENDATION_POLICY=dict(state='USER_CONFIRMED',effective_on='2026-10-07',
    provenance='2026-10-07 사용자 정정: 최대 5종목, 종목당 최대 40%, 현금 최소 5%',
    max_positions=5,max_position_pct=40,min_cash_pct=5)


def capped_weights(inverse, invested, cap):
    remaining=list(range(len(inverse)));weights=[0.0]*len(inverse);budget=invested
    while remaining:
        denominator=sum(inverse[i] for i in remaining)
        proposed={i:budget*inverse[i]/denominator for i in remaining}
        capped=[i for i,w in proposed.items() if w>cap]
        if not capped:
            for i,w in proposed.items():weights[i]=w
            break
        for i in capped:weights[i]=cap;budget-=cap;remaining.remove(i)
    weights=[min(cap,round(w,8)) for w in weights]
    if weights and sum(weights)>invested:
        largest=max(range(len(weights)),key=lambda i:weights[i])
        weights[largest]-=sum(weights)-invested
        while sum(weights)>invested:weights[largest]=nextafter(weights[largest],0.0)
    return weights


def choose_and_allocate(shortlist, cache, cutoff, policy=None):
    """Score qualifies first; correlation diversity selects, inverse volatility sizes.

    No risk limit, expected return, or backtested optimum is implied. Missing
    histories retain score order with a labelled equal-weight safe default.
    """
    policy=policy or RECOMMENDATION_POLICY
    count=policy['max_positions'];cap=policy['max_position_pct'];cash=policy['min_cash_pct']
    picked=shortlist[:count];state='SAFE_DEFAULT';status='pending';reason='동일 기간 가격 미확보; 점수순 동일비중 참고안'
    dates=None;returns={};unavailable=[];priced=[]
    for target in shortlist:
        try:common_window([target],cache,cutoff);priced.append(target)
        except (ValueError,KeyError,TypeError,OverflowError) as exc:unavailable.append(dict(code=target['code'],reason=str(exc)))
    try:
        if not priced:raise ValueError('검증 가격 후보 없음')
        dates=common_window(priced,cache,cutoff)
        for target in priced:
            rows=checked(cache['history']['histories'][target['code']]['prices'],cutoff)
            prices=[r['close'] for r in rows if r['date']>=dates[0]]
            returns[target['code']]=[b/a-1 for a,b in zip(prices,prices[1:])]
        def correlation(a,b):
            x=returns[a['code']];y=returns[b['code']];sx=stdev(x);sy=stdev(y)
            mx=mean(x);my=mean(y)
            return sum((i-mx)*(j-my) for i,j in zip(x,y))/(len(x)-1)/sx/sy if sx>0 and sy>0 else 1.0
        picked=[];remaining=list(priced)
        while remaining and len(picked)<count:
            if not picked:chosen=remaining[0]
            else:
                chosen=min(remaining,key=lambda r:(
                    max(max(0.0,correlation(r,p)) for p in picked),
                    len(picked)+1 if not r.get('industry') or r.get('industry')=='산업 미확인' else sum(p.get('industry')==r.get('industry') for p in picked),
                    -r['score'],r['code']))
            picked.append(chosen);remaining.remove(chosen)
        inverse=[1/stdev(returns[t['code']]) if stdev(returns[t['code']])>0 else None for t in picked]
        if all(numeric(v) for v in inverse):state='SOURCE_RECORDED';status='ready';reason='공통 관측기간의 양의 상관·산업 중복 참고 선택, 역변동성 비중과 40% 상한'
        else:inverse=[1.0]*len(picked);reason='변동성 0으로 역변동성 산정 불가; 동일비중 참고안'
    except (ValueError,KeyError,TypeError,OverflowError):inverse=[1.0]*len(picked)
    invested=min(100-cash,cap*len(picked))
    weights=capped_weights(inverse,invested,cap) if picked else []
    targets=[dict(t,weight_pct=w) for t,w in zip(picked,weights)]
    return dict(targets=targets,cash_pct=100-sum(weights),status=status,state=state,reason=reason,
        policy=dict(policy),risk_unavailable_candidates=unavailable,risk_qualified=len(priced),window=dict(start_date=dates[0],as_of=dates[-1],observations=len(dates)-1) if dates else None,
        observation_dates=dates,method='재무·추세 통과 점수 상위15개 중 최대5개. 첫 종목 점수순, 이후 기존 선택과 최대 양의 상관이 낮은 순/산업중복/점수순. 같은 구간 역변동성 비중, 종목40% 상한·현금5% 하한. 검증된 최적화·기대수익률 아님')
