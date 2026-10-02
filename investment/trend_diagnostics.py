"""Explainable price diagnostics. Research thresholds, never order signals."""
from math import log
from statistics import mean, pstdev
from .core import num


def diagnose(bars, technical):
    prices=[b['close'] for b in bars];price=prices[-1];s=technical['sma']
    def average(n,offset=0):
        end=len(prices)-offset
        return mean(prices[end-n:end]) if end>=n else None
    old200=average(200,21)
    high=technical.get('high_52w_close');low=technical.get('low_52w_close')
    checks=[]
    def check(key,label,value,condition,unit=''):
        checks.append(dict(id=key,label=label,value=value,unit=unit,status='unknown' if value is None else 'pass' if condition else 'fail'))
    def gap(a,b):return (a/b-1)*100 if num(a) and num(b) and b>0 else None
    check('price_long','종가 > 150·200일선',price if all(num(s.get(k)) for k in ('150','200')) else None,
          all(num(s.get(k)) and price>s[k] for k in ('150','200')),'원')
    check('long_stack','150일선 > 200일선',gap(s.get('150'),s.get('200')),num(s.get('150')) and num(s.get('200')) and s['150']>s['200'],'%')
    check('long_rising','200일선 > 21거래일 전',gap(s.get('200'),old200),num(old200) and s['200']>old200,'%')
    check('short_stack','50일선 > 150·200일선',s.get('50'),all(num(s.get(k)) and s['50']>s[k] for k in ('150','200')) if num(s.get('50')) else False,'원')
    check('price50','종가 > 50일선',gap(price,s.get('50')),num(s.get('50')) and price>s['50'],'%')
    check('above_low','52주 최저종가 대비 +30% 이상',gap(price,low),num(low) and price>=low*1.30,'%')
    check('near_high','52주 최고종가 대비 -25% 이내',gap(price,high),num(high) and price>=high*.75,'%')
    check('rs','자체 RS 70 이상',technical.get('price_strength',{}).get('score'),False,'점')
    pivot=max(prices[-21:-1]) if len(prices)>=21 else None
    prior_pivot=max(prices[-22:-2]) if len(prices)>=22 else None
    volume_ratio=None;dry_ratio=None
    volumes=[b.get('volume') for b in bars]
    volume_ok=len(volumes)>=51 and all(num(v) and v>=0 for v in volumes[-51:]) and mean(volumes[-51:-1])>0
    if volume_ok:
        volume_ratio=volumes[-1]/mean(volumes[-51:-1])
        dry_ratio=mean(volumes[-5:])/mean(volumes[-50:]) if mean(volumes[-50:])>0 else None
    returns=[log(b/a) for a,b in zip(prices,prices[1:])]
    volatility_ratio=pstdev(returns[-10:])/pstdev(returns[-60:]) if len(returns)>=60 and pstdev(returns[-60:])>0 else None
    ranges=[(max(prices[-offset-10:len(prices)-offset if offset else None])/min(prices[-offset-10:len(prices)-offset if offset else None])-1)*100 for offset in (20,10,0)] if len(prices)>=30 else []
    contraction=(ranges[2]<ranges[1]<ranges[0] and volatility_ratio<.7 and dry_ratio<.7) if len(ranges)==3 and num(volatility_ratio) and num(dry_ratio) else None
    distance=gap(price,pivot)
    failed=bool(prior_pivot and prices[-2]>prior_pivot and price<=prior_pivot)
    if failed:phase='돌파 후 되밀림'
    elif num(pivot) and price>pivot:phase='거래량 동반 돌파' if num(volume_ratio) and volume_ratio>=1.5 else '가격 돌파 · 거래량 보강 필요' if num(volume_ratio) else '가격 돌파 · 거래량 확인 대기'
    elif num(distance) and -3<=distance<=0:phase='돌파선 3% 이내'
    elif num(s.get('50')) and price<s['50']:phase='50일선 아래 조정'
    elif num(high) and price<high*.75:phase='고점에서 큰 폭 조정'
    else:phase='추세·횡보 관찰'
    result=dict(checks=checks,phase=phase,pivot=pivot,pivot_gap_pct=distance,volume_multiple=volume_ratio,
        volume_dry_ratio=dry_ratio,volatility_ratio=volatility_ratio,ranges_pct=ranges,contraction=contraction,
        extension50_pct=gap(price,s.get('50')),low_52w_close=low,high_52w_close=high,
        above_low_pct=gap(price,low),drawdown_pct=gap(price,high),ma200_change_pct=gap(s.get('200'),old200),
        mmt_high_pass=None if high is None else high<=price*1.25)
    if technical.get('suspended') or bars[-1].get('no_trade') or bars[-1].get('volume')==0:
        result.update(blocked=True,phase='거래 없음 · 판정 보류')
    update_rank(result,technical.get('price_strength',{}).get('score'))
    return result


def update_rank(analysis,score):
    for check in analysis['checks']:
        if check['id']=='rs':check.update(value=score,status='unknown' if not num(score) else 'pass' if score>=70 else 'fail')
    statuses=[c['status'] for c in analysis['checks']]
    analysis.update(passed=statuses.count('pass'),total=len(statuses),status='unknown' if analysis.get('blocked') else 'fail' if 'fail' in statuses else 'unknown' if 'unknown' in statuses else 'pass')
    # StockEasy's published high <= close * 1.25 is a 20% drawdown limit.
    price_ids={'long_stack','long_rising','short_stack','price50'}
    mmt=[c['status'] for c in analysis['checks'] if c['id'] in price_ids]
    mmt.append('unknown' if analysis['mmt_high_pass'] is None else 'pass' if analysis['mmt_high_pass'] else 'fail')
    analysis['mmt_status']='unknown' if analysis.get('blocked') else 'fail' if 'fail' in mmt else 'unknown' if 'unknown' in mmt else 'pass'
