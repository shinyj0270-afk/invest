"""Read-only historical price risk. Never infer missing sessions or place orders."""
from datetime import date
from math import isfinite, sqrt
from statistics import mean, stdev

SESSIONS_PER_YEAR = 252
WINDOW = 253
MIN_RETURNS = 63
NOTE = ('과거 가격 시나리오 · 매일 목표 비중 재조정 가정 · 현금수익 0 · '
        '배당·수수료·세금 제외. 연율은 252거래일, 표본 표준편차. 미래 손실 한도 아님. '
        '제공자 수정주가·지수 관측일 기준이며 공식 거래소 확정·총수익률 검증과 구분.')
PRICE_NOTE = ('종목과 해당 시장 가격지수의 과거 가격 수익률. 배당·수수료·세금 제외. '
              '연율은 252거래일, 표본 표준편차. 최대 252개 수익률·직전 20수익률 변동성. '
              '제공자 수정주가·지수 관측일 기준; 공식 거래소 확정·총수익률 검증과 구분.')


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def day(value):
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def checked(prices, cutoff):
    if not day(cutoff):
        raise ValueError('평가일 확인 필요')
    if not isinstance(prices, list) or not prices or any(not isinstance(p, dict) or not day(p.get('date')) for p in prices):
        raise ValueError('가격 날짜 확인 필요')
    # Future observations are never used to evaluate an earlier recommendation.
    rows = [p for p in prices if p['date'] <= cutoff]
    dates = [p['date'] for p in rows]
    if not rows or dates != sorted(set(dates)):
        raise ValueError('가격 날짜 중복·정렬 확인 필요')
    if any(not numeric(p.get('close')) or p['close'] <= 0 or p.get('final') is not True
           or p.get('venue') != 'KRX'
           or p.get('adjustment_basis') not in ('split_adjusted', 'naver_chart_adjusted', 'index_level') for p in rows):
        raise ValueError('완료 종가·KRX·수정 기준 확인 필요')
    if len({p['adjustment_basis'] for p in rows}) != 1:
        raise ValueError('시계열 수정 기준 혼합')
    return rows


def path_metrics(dates, returns, benchmark_returns=None):
    wealth = peak = 1.0
    benchmark = 1.0
    points = [dict(date=dates[0],return_pct=0.0,drawdown_pct=0.0,
                   volatility20_pct=None,benchmark_return_pct=0.0 if benchmark_returns is not None else None,
                   excess_return_pp=0.0 if benchmark_returns is not None else None)]
    for i, value in enumerate(returns):
        wealth *= 1 + value
        if not numeric(wealth):
            raise ValueError('가격 수익률 계산 범위 확인 필요')
        peak = max(peak, wealth)
        if benchmark_returns is not None:
            benchmark *= 1 + benchmark_returns[i]
        points.append(dict(date=dates[i+1], return_pct=(wealth-1)*100,
            drawdown_pct=(wealth/peak-1)*100,
            volatility20_pct=stdev(returns[i-19:i+1])*sqrt(SESSIONS_PER_YEAR)*100 if i >= 19 else None,
            benchmark_return_pct=(benchmark-1)*100 if benchmark_returns is not None else None,
            excess_return_pp=(wealth-benchmark)*100 if benchmark_returns is not None else None))
    return dict(series=points,return_pct=points[-1]['return_pct'],
        annual_volatility_pct=stdev(returns)*sqrt(SESSIONS_PER_YEAR)*100,
        max_drawdown_pct=min(p['drawdown_pct'] for p in points),
        observations=len(returns),start_date=dates[0],as_of=dates[-1])


def time_series(prices, benchmark, cutoff):
    """Compare price returns on exact source index dates; do not bridge gaps."""
    try:
        rows=checked(prices,cutoff)
        if rows[0]['adjustment_basis']=='index_level':
            raise ValueError('종목 수정주가 기준 확인 필요')
        bm=checked(benchmark,cutoff)
        if any(p['adjustment_basis'] != 'index_level' for p in bm):
            raise ValueError('가격지수 기준 확인 필요')
        dates=[p['date'] for p in bm if p['date'] >= rows[0]['date']][-WINDOW:]
        if len(dates) < MIN_RETURNS+1 or dates[-1] != cutoff:
            raise ValueError('같은 평가일까지 최소 63개 일별 수익률 필요')
        selected=[p for p in rows if p['date'] >= dates[0]]
        if [p['date'] for p in selected] != dates:
            raise ValueError('지수 관측일 대비 누락·추가 거래일 또는 평가일 가격 대기')
        bp={p['date']:p['close'] for p in bm}
        values=[p['close'] for p in selected]
        returns=[b/a-1 for a,b in zip(values,values[1:])]
        breturns=[bp[b]/bp[a]-1 for a,b in zip(dates,dates[1:])]
        return dict(status='ready',state='SOURCE_RECORDED',definition=PRICE_NOTE,
                    **path_metrics(dates,returns,breturns))
    except (ValueError,TypeError,KeyError,OverflowError) as exc:
        return dict(status='pending',state='PENDING',reason=str(exc),definition=PRICE_NOTE)


def portfolio_risk(targets, cash_pct, cache, cutoff, *, observation_dates=None):
    result=dict(status='pending',state='PENDING',as_of=cutoff,definition=NOTE)
    try:
        weights=[t.get('weight_pct') for t in targets]
        if len(targets)>5 or len({t['code'] for t in targets})!=len(targets):
            raise ValueError('서로 다른 최대 5종목 필요')
        if not numeric(cash_pct) or not 0<=cash_pct<=100 or any(not numeric(w) or not 0<w<=100 for w in weights) or abs(sum(weights)+cash_pct-100)>1e-6:
            raise ValueError('종목·현금 비중 합계 100% 확인 필요')
        exposure=sum(weights)
        sectors={}
        for target in targets:
            label=target.get('industry') or '산업 미확인'
            sectors[label]=sectors.get(label,0)+target['weight_pct']
        result['concentration']=dict(cash_pct=cash_pct,equity_pct=exposure,
            largest_position_pct=max(weights,default=0),sector_weights=sectors,
            equity_hhi=sum((w/exposure)**2 for w in weights) if exposure else None,
            definition='HHI: 주식 부분 비중을 100%로 정규화한 제곱합. 현금 비중 별도 표시; 미확인 산업은 분산으로 간주하지 않음')
        if not targets:
            result.update(status='cash_only',state='SAFE_DEFAULT',reason='현금 100%; 주식 상관관계·과거 주식 위험 적용 대상 없음')
            return result
        history=(cache or {}).get('history',{})
        from .market_history import benchmark_calendar
        calendar=benchmark_calendar(history.get('benchmarks',{}))
        if not day(cutoff) or cutoff not in calendar['sessions']:
            raise ValueError('평가일의 양대 지수 완료 관측일 대기')
        histories=history.get('histories',{});series=[];bases=set()
        for target in targets:
            record=histories.get(target['code'],{})
            if record.get('kind')!='item' or record.get('symbol')!=target['code']:
                raise ValueError(target['code']+' 가격 식별정보·이력 대기')
            rows=checked(record.get('prices'),cutoff)
            if rows[0]['adjustment_basis']=='index_level':
                raise ValueError('종목에 지수 기준 적용 불가')
            bases.add(rows[0]['adjustment_basis']);series.append(rows)
        if len(bases)!=1:
            raise ValueError('종목 간 수정주가 기준 일치 확인 필요')
        first=max(s[0]['date'] for s in series)
        dates=[d for d in calendar['sessions'] if first<=d<=cutoff][-WINDOW:]
        if observation_dates is not None:
            if not isinstance(observation_dates,list) or not observation_dates or len(observation_dates)>WINDOW or observation_dates!=[d for d in calendar['sessions'] if observation_dates[0]<=d<=cutoff] or observation_dates[-1]!=cutoff or any(d<first for d in observation_dates):
                raise ValueError('동일 비교 관측 구간 확인 필요')
            dates=observation_dates
        if len(dates)<MIN_RETURNS+1:
            raise ValueError('공통 관측 구간 최소 63개 일별 수익률 필요')
        values=[]
        for target,rows in zip(targets,series):
            rows=[p for p in rows if p['date']>=dates[0]]
            if [p['date'] for p in rows]!=dates:
                raise ValueError(target['code']+' 누락·추가 거래일 또는 평가일 가격 대기; 보간하지 않음')
            values.append([b['close']/a['close']-1 for a,b in zip(rows,rows[1:])])
        w=[v/100 for v in weights]
        daily=[sum(w[j]*values[j][i] for j in range(len(w))) for i in range(len(dates)-1)]
        averages=[mean(v) for v in values]
        covariance=[[sum((a-averages[i])*(b-averages[j]) for a,b in zip(values[i],values[j]))/(len(daily)-1)
                     for j in range(len(w))] for i in range(len(w))]
        sigma=stdev(daily)
        correlations=[[max(-1.0,min(1.0,covariance[i][j]/sqrt(covariance[i][i]*covariance[j][j])))
                       if covariance[i][i]>0 and covariance[j][j]>0 else None for j in range(len(w))] for i in range(len(w))]
        contribution=[dict(code=t['code'],name=t['name'],
            volatility_contribution_pp=w[i]*sum(covariance[i][j]*w[j] for j in range(len(w)))/sigma*sqrt(SESSIONS_PER_YEAR)*100 if sigma>0 else None)
            for i,t in enumerate(targets)]
        # Market mix follows the target weights, including the same zero-return cash.
        breturns=[0.0]*len(daily)
        for target,weight in zip(targets,w):
            if target.get('market') not in ('KOSPI','KOSDAQ'):
                raise ValueError('시장별 비교 지수 연결 대기')
            bp={p['date']:p['close'] for p in checked(history['benchmarks'][target['market']]['prices'],cutoff)}
            for i,(a,b) in enumerate(zip(dates,dates[1:])):
                breturns[i]+=weight*(bp[b]/bp[a]-1)
        result.update(status='ready',state='SOURCE_RECORDED',
            **path_metrics(dates,daily,breturns),codes=[t['code'] for t in targets],
            names=[t['name'] for t in targets],correlations=correlations,
            risk_contributions=contribution,calendar_basis=calendar['calendar_basis'],
            sources=[dict(code=t['code'],source=histories[t['code']].get('source',{})) for t in targets],
            adjustment_basis=next(iter(bases)),benchmark_definition='목표 시장 비중의 KOSPI/KOSDAQ 혼합 가격지수 + 동일 현금 비중')
    except (ValueError,TypeError,KeyError,OverflowError) as exc:
        result['reason']=str(exc)
    return result


def common_window(targets, cache, cutoff):
    """One exact index calendar for every composition in a review universe."""
    from .market_history import benchmark_calendar
    history=(cache or {}).get('history',{})
    calendar=benchmark_calendar(history.get('benchmarks',{}))
    if not day(cutoff) or cutoff not in calendar['sessions']:
        raise ValueError('평가일의 양대 지수 완료 관측일 대기')
    first=None;bases=set()
    for target in {t['code']:t for t in targets}.values():
        record=history.get('histories',{}).get(target['code'],{})
        if record.get('kind')!='item' or record.get('symbol')!=target['code']:
            raise ValueError(target['code']+' 가격 식별정보·이력 대기')
        rows=checked(record.get('prices'),cutoff)
        if rows[0]['adjustment_basis']=='index_level':raise ValueError('종목 수정 기준 확인 필요')
        bases.add(rows[0]['adjustment_basis'])
        first=max(first or rows[0]['date'],rows[0]['date'])
    if len(bases)>1:raise ValueError('종목 간 수정 기준 일치 확인 필요')
    dates=[d for d in calendar['sessions'] if (first is None or d>=first) and d<=cutoff][-WINDOW:]
    if len(dates)<MIN_RETURNS+1:raise ValueError('공통 관측 구간 최소 63개 일별 수익률 필요')
    for target in {t['code']:t for t in targets}.values():
        rows=checked(history['histories'][target['code']]['prices'],cutoff)
        if [p['date'] for p in rows if p['date']>=dates[0]]!=dates:
            raise ValueError(target['code']+' 누락·추가 거래일 또는 평가일 가격 대기')
    return dates


def validate_policy(policy, cutoff):
    if policy is None:return dict(status='not_configured',limits={})
    if not day(cutoff) or not isinstance(policy,dict) or policy.get('state')!='USER_CONFIRMED' or not day(policy.get('effective_on')) or policy['effective_on']>cutoff or not isinstance(policy.get('provenance'),str) or not policy['provenance'].strip():
        return dict(status='pending',reason='사용자 확인·근거·효력일 확인 필요',limits={})
    limits={k:policy.get(k) for k in ('max_positions','max_position_pct','min_cash_pct')}
    if type(limits['max_positions']) is not int or not 1<=limits['max_positions']<=5 or not all(numeric(limits[k]) and 0<=limits[k]<=100 for k in ('max_position_pct','min_cash_pct')) or limits['max_position_pct']<=0:
        return dict(status='pending',reason='집중도·현금 한도 확인 필요',limits={})
    return dict(status='configured',state='USER_CONFIRMED',effective_on=policy['effective_on'],provenance=policy['provenance'],limits=limits)


def compare_portfolios(proposed, previous, cache, cutoff, policy=None, *, observation_dates=None, policy_as_of=None):
    """Compare both compositions on their combined universe, never different windows."""
    result=dict(status='pending',as_of=cutoff,policy_status='not_configured',deltas={},flags=[],definition=NOTE)
    policy_on=policy_as_of if policy_as_of is not None else proposed.get('created_on') if day(proposed.get('created_on')) else cutoff
    configured=validate_policy(policy,policy_on);result['policy']=configured;result['policy_status']=configured['status'];result['policy_assessed_on']=policy_on
    targets=proposed.get('targets',[]);old=(previous or {}).get('targets',[])
    if any(not t.get('industry') or t.get('industry')=='산업 미확인' for t in targets+old):result['flags'].append('unknown_industry')
    if configured['status']=='configured':
        limits=configured['limits'];violations=[]
        if len(targets)>limits['max_positions']:violations.append('max_positions')
        if any(not numeric(t.get('weight_pct')) or t['weight_pct']>limits['max_position_pct']+1e-8 for t in targets):violations.append('max_position_pct')
        if not numeric(proposed.get('cash_pct')) or proposed['cash_pct']<limits['min_cash_pct']-1e-8:violations.append('min_cash_pct')
        result['policy_violations']=violations
        result['policy_status']='violated' if violations else 'within_limits'
    if previous is None:
        result['proposed']=portfolio_risk(targets,proposed.get('cash_pct'),cache,cutoff,observation_dates=observation_dates)
        result['reason']='이전 추천안 없음; 작성 당시 위험을 별도 보존'
        return result
    try:
        dates=observation_dates if observation_dates is not None else common_window(targets+old,cache,cutoff)
        a=portfolio_risk(targets,proposed.get('cash_pct'),cache,cutoff,observation_dates=dates)
        b=portfolio_risk(old,previous.get('cash_pct'),cache,cutoff,observation_dates=dates)
        result.update(proposed=a,previous=b,window=dict(start_date=dates[0],as_of=dates[-1],observations=len(dates)-1))
        if a['status'] not in ('ready','cash_only') or b['status'] not in ('ready','cash_only'):
            raise ValueError(a.get('reason') or b.get('reason') or '比較資料 대기')
        def metric(r,k):return 0.0 if r['status']=='cash_only' else r[k]
        for k in ('annual_volatility_pct','max_drawdown_pct'):
            result['deltas'][k]=metric(a,k)-metric(b,k)
        for k in ('largest_position_pct','equity_hhi'):
            av=a['concentration'].get(k);bv=b['concentration'].get(k)
            result['deltas'][k]=av-bv if numeric(av) and numeric(bv) else None
        result['deltas']['cash_pct']=a['concentration']['cash_pct']-b['concentration']['cash_pct']
        sector_a=max(a['concentration']['sector_weights'].values(),default=0)
        sector_b=max(b['concentration']['sector_weights'].values(),default=0)
        result['deltas']['largest_sector_pct']=sector_a-sector_b
        if any(numeric(result['deltas'].get(k)) and result['deltas'][k]>1e-8 for k in ('largest_position_pct','equity_hhi','largest_sector_pct')):result['flags'].append('concentration_increased')
        if result['deltas']['annual_volatility_pct']>1e-8:result['flags'].append('volatility_higher')
        if result['deltas']['max_drawdown_pct']<-1e-8:result['flags'].append('drawdown_deeper')
        result['status']='ready'
    except (ValueError,TypeError,KeyError,OverflowError) as exc:
        result.update(reason=str(exc),deltas={});result['flags'].append('missing_price')
    return result
