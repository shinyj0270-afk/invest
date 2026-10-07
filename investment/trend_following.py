"""Chart-first trend workspace from validated saved prices; no retrieval or orders."""
from copy import deepcopy
from .portfolio_risk import checked, numeric, day
from .market_history import benchmark_calendar, ADJUSTMENT_NOTE
from .trend_diagnostics import diagnose
from .market_explanation import build_market_explanation
from .trend_checkpoints import summarize, compare_observations


def chart_series(bars, count=253):
    totals=[0.0]
    for p in bars:totals.append(totals[-1]+p['close'])
    return [dict(date=p['date'],close=p['close'],
        volume=p.get('volume') if numeric(p.get('volume')) and p['volume']>=0 else None,
        **{'ma'+str(n):(totals[i+1]-totals[i+1-n])/n if i+1>=n else None for n in (20,50,150,200)})
        for i,p in enumerate(bars) if i>=max(0,len(bars)-count)]


def build_trend_following(snapshot,research,cache=None):
    cutoff=snapshot['meta'].get('price_date')
    history=(cache or {}).get('history',{});benchmarks=history.get('benchmarks',{})
    calendar=None
    if benchmarks:
        try:calendar=benchmark_calendar(benchmarks)
        except (ValueError,KeyError,TypeError):pass
    market_bars={};markets=[]
    for market in ('KOSPI','KOSDAQ'):
        result=dict(market=market,status='pending',regime='자료 대기',series=[])
        try:
            if benchmarks and (not calendar or calendar['valid_through']!=cutoff):
                raise ValueError('양대 지수의 같은 완료 관측일 대기')
            raw=benchmarks.get(market,{}).get('prices') if benchmarks else snapshot.get('benchmarks',{}).get(market)
            bars=checked(raw,cutoff)
            if bars[-1]['date']!=cutoff or bars[0]['adjustment_basis']!='index_level':
                raise ValueError('평가일 가격지수 수준 확인 필요')
            market_bars[market]=bars
            series=chart_series(bars);last=series[-1]
            prior200=sum(p['close'] for p in bars[-221:-21])/200 if len(bars)>=221 else None
            ma50=last['ma50'];ma200=last['ma200'];close=last['close']
            regime='자료 대기' if prior200 is None else '상승 정렬' if close>ma50>ma200 and ma200>prior200 else '하락 정렬' if close<ma50<ma200 and ma200<prior200 else '혼조 · 전환 관찰'
            result.update(status='ready',regime=regime,series=series,as_of=cutoff,close=close,
                change_pct=(bars[-1]['close']/bars[-2]['close']-1)*100 if len(bars)>1 else None)
        except (ValueError,KeyError,TypeError) as exc:result['reason']=str(exc)
        markets.append(result)
    rows=[];previews={};raw_by_code={}
    for row in snapshot['companies']:
        t=research.get('rows',{}).get(row['code'],{}).get('technical',{})
        item=dict(code=row['code'],name=row['name'],market=row['market'],industry=row.get('industry','산업 미확인'),
            discovery_allowed=row.get('discovery_allowed'),
            cap_eok=row.get('metrics',{}).get('market_cap_eok'),rs=t.get('price_strength',{}).get('score'),
            rs1m=t.get('short_rs',{}).get('1m',{}).get('score'),ready=False,reason='완료 가격 이력 대기',
            technical={k:deepcopy(t.get(k)) for k in ('close','as_of','sma','price_strength','source_note','high_52w_close','gap_to_52w_high_pct')})
        try:
            record=history.get('histories',{}).get(row['code'])
            if record is not None:
                if record.get('kind')!='item' or record.get('symbol')!=row['code']:
                    raise ValueError('가격 이력 종목 식별 불일치')
                raw=record.get('prices')
            else:raw=row.get('trend_prices') or row.get('prices')
            bars=checked(raw,cutoff)
            if bars[0]['adjustment_basis']=='index_level':raise ValueError('종목 수정주가 기준 대기')
            bm=market_bars.get(row['market'],[])
            expected=[p['date'] for p in bm if p['date']>=bars[0]['date']]
            if not expected or [p['date'] for p in bars]!=expected or bars[-1]['date']!=cutoff:
                raise ValueError('완료 종가와 지수 관측일 불일치·누락')
            if not numeric(t.get('close')) or t['close']!=bars[-1]['close'] or t.get('as_of')!=cutoff:
                raise ValueError('분석 가격과 차트 기준일 대조 필요')
            # Use the established price-only 8-condition variant, including its RS population.
            diagnostic=diagnose(bars,t)
            item.update(ready=not diagnostic.get('blocked',False),reason='거래 없음 · 판정 보류' if diagnostic.get('blocked') else '',
                phase=diagnostic['phase'],analysis=diagnostic)
            raw_by_code[row['code']]=bars
        except (ValueError,KeyError,TypeError) as exc:
            item['reason']=str(exc);item['technical'].update(close=None,trend_analysis=None)
        rows.append(item)
    ranked=sorted((r for r in rows if r['discovery_allowed'] is not False and r['ready'] and numeric(r['rs']) and r['rs']>=70 and numeric(r['cap_eok']) and r['cap_eok']>=1000),key=lambda r:(-r['rs'],r['code']))
    # Bound initial payload. Other cards reuse lazy company views, no new data API.
    for row in ranked[:21]:previews[row['code']]=chart_series(raw_by_code[row['code']])
    data=dict(as_of=cutoff,mode=snapshot['meta']['data_mode'],markets=markets,rows=rows,previews=previews,
        default_cap_eok=1000,default_rs=70,preview_limit=21,
        source_note=ADJUSTMENT_NOTE if history else '저장 수정주가 · 완료 종가·거래소·지수 날짜 대조',
        market_definition='자체 지수 참고: 종가>50일선>200일선 및 200일선>21거래일 전이면 상승 정렬, 반대면 하락 정렬. 스탁이지 신호등·FTD 판정 아님')
    data['market_explanation']=build_market_explanation(cutoff,markets,rows,raw_by_code,market_bars,data['source_note'])
    if day(cutoff):
        data['changes']=compare_observations(summarize(data))
    else:
        data['changes']=dict(status='pending',as_of=None,comparison='완료 관측일 미확보 · 체크포인트 비교 대기',
            reason='같은 완료 관측일의 양대 지수와 종목 이력이 필요합니다.',new_qualified=[],dropouts=[],pending=[],near=[],breakouts=[],ma_fail=[])
    return data
