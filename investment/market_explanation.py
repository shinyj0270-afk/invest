"""Shared observed index direction, stock participation and volatility explanation."""
from math import sqrt
from statistics import stdev
from .portfolio_risk import numeric


def build_market_explanation(cutoff, markets, rows, bars_by_code, market_bars, source_note):
    cards = []
    for market in ('KOSPI', 'KOSDAQ'):
        index = next((m for m in markets if m['market'] == market), {})
        population = [r for r in rows if r['market'] == market]
        usable = [r for r in population if r.get('ready') and r['code'] in bars_by_code]
        above = {}
        for n in (50, 200):
            eligible = [r for r in usable if len(bars_by_code[r['code']]) >= n]
            count = sum(bars_by_code[r['code']][-1]['close'] >
                        sum(p['close'] for p in bars_by_code[r['code']][-n:]) / n for r in eligible)
            above[str(n)] = dict(count=count, eligible=len(eligible),
                                pct=count / len(eligible) * 100 if eligible else None)
        pairs = [bars_by_code[r['code']][-2:] for r in usable if len(bars_by_code[r['code']]) >= 2]
        advances = sum(b[-1]['close'] > b[-2]['close'] for b in pairs)
        declines = sum(b[-1]['close'] < b[-2]['close'] for b in pairs)
        breadth = above['200']['pct']
        participation = '자료 대기' if breadth is None else '참여 양호' if breadth >= 50 else '참여 약화'
        bars = market_bars.get(market, [])
        returns = [b['close'] / a['close'] - 1 for a, b in zip(bars, bars[1:])]
        vol = stdev(returns[-20:]) * sqrt(252) * 100 if len(returns) >= 20 else None
        prior = stdev(returns[-40:-20]) * sqrt(252) * 100 if len(returns) >= 40 else None
        direction = index.get('regime', '자료 대기')
        if index.get('status') != 'ready' or breadth is None:
            reason = '같은 완료 관측일의 지수 또는 참여 분모가 부족하여 합산 판단을 보류합니다.'
        elif direction == '상승 정렬' and breadth < 50:
            reason = '지수는 상승 정렬이지만 관측기업 과반은 200일선 아래입니다. 지수 수준과 개별기업 참여 범위가 달라 혼합 신호입니다. 지수 상승만으로 폭넓은 상승을 확인할 수 없습니다.'
        elif direction == '하락 정렬' and breadth >= 50:
            reason = '지수는 하락 정렬이지만 관측기업 과반은 200일선 위입니다. 지수 수준과 개별기업 참여 범위가 달라 혼합 신호입니다.'
        else:
            reason = f'지수 방향은 {direction}, 관측기업 참여는 {participation}입니다. 변동성은 움직임의 크기이며 상승·하락 방향 판정과 별도입니다.'
        cards.append(dict(market=market, as_of=cutoff, state='SOURCE_RECORDED',
            index=dict(status=index.get('status', 'pending'), label=direction,
                       close=index.get('close'), reason=index.get('reason'),
                       definition='종가>50일선>200일선, 200일선>21거래일 전이면 상승 정렬; 반대면 하락 정렬'),
            breadth=dict(label=participation, population=len(population), valid=len(usable),
                         above=above, advancing=advances, declining=declines,
                         unchanged=len(pairs)-advances-declines, change_eligible=len(pairs),
                         definition='같은 기준일·지수 관측일·수정 기준을 대조한 저장 관찰기업. 200일선 위 비율 50% 이상이면 참여 양호'),
            volatility=dict(annual20_pct=vol, prior20_pct=prior, returns=min(20, len(returns)),
                            start_date=bars[-21]['date'] if len(bars) >= 21 else None,
                            label='자료 대기' if vol is None else '직전 구간 대비 확대' if numeric(prior) and vol > prior else '직전 구간 대비 축소·동일' if numeric(prior) else '20일 변동성 관측',
                            definition='직전20개 일수익률 표본 표준편차 × √252. 비교는 그 이전20개 수익률; 위험 한도 아님'),
            explanation=reason, source_note=source_note,
            verification='저장자료 관측 · 자체 산식 · 공식 시장신호·전체시장·수급 독립 검증 아님'))
    return dict(as_of=cutoff, markets=cards, universe='저장 관찰기업; 전체 상장시장 아님',
                definition='지수 방향 / 기업 참여 / 변동성을 분리합니다. 화면 필터는 시장 참여 분모를 바꾸지 않습니다.')
