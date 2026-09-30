"""Source-backed interactive charts. No scoring or investment rule changes."""
import math
import altair as alt
import pandas as pd
import streamlit as st
from .core import num, safe_csv

METRICS = {'operating_margin_pct':'영업이익률 (%)','roe_pct':'ROE (%)',
           'revenue_growth_pct':'매출 증가율 (%)','debt_ratio_pct':'부채비율 (%)',
           'market_cap_eok':'시가총액 (억원)','per':'PER (배)','pbr':'PBR (배)'}
BLUE='#3182f6'


def styled(chart):
    return chart.configure_view(stroke=None).configure_axis(
        labelColor='#6b7684',titleColor='#4e5968',gridColor='#f2f4f6',domain=False,
        labelFontSize=12,titleFontSize=12,labelLimit=150).configure_legend(
        labelColor='#6b7684',titleColor='#4e5968',orient='bottom').configure(background='#ffffff')


def numeric(value):
    return num(value) and math.isfinite(value)


def metric_records(companies, key):
    return [dict(code=r['code'],name=r['name'],label=r['name']+' · '+r['code'],industry=r['industry'],value=r['metrics'][key])
            for r in companies if numeric(r['metrics'].get(key))]


def scatter_records(companies, xkey, ykey):
    return [dict(code=r['code'],name=r['name'],industry=r['industry'],
                 x=r['metrics'][xkey],y=r['metrics'][ykey]) for r in companies
            if numeric(r['metrics'].get(xkey)) and numeric(r['metrics'].get(ykey))]


def heatmap_records(companies, keys):
    rows=[]
    for key in keys:
        valid=[r['metrics'][key] for r in companies if numeric(r['metrics'].get(key))]
        low,high=(min(valid),max(valid)) if valid else (None,None)
        for r in companies:
            value=r['metrics'].get(key)
            score=(50 if high==low else 100*(value-low)/(high-low)) if numeric(value) else None
            rows.append(dict(code=r['code'],name=r['name'],label=r['name']+' · '+r['code'],metric=METRICS[key],value=value if numeric(value) else None,
                value_label=f'{value:,.1f}' if numeric(value) else '자료 없음',score=score))
    return rows


def bar_chart(rows,label):
    return styled(alt.Chart(alt.Data(values=rows)).mark_bar(cornerRadiusEnd=5,size=24).encode(
        y=alt.Y('label:N',sort='-x',title=None),x=alt.X('value:Q',title=label,scale=alt.Scale(zero=True)),
        color=alt.Color('value:Q',scale=alt.Scale(scheme='blues'),legend=None),
        tooltip=[alt.Tooltip('name:N',title='기업'),alt.Tooltip('code:N',title='코드'),
                 alt.Tooltip('value:Q',title=label,format=',.2f')]).properties(height=max(160,len(rows)*36)))


def scatter_chart(rows,xlabel,ylabel):
    pick=alt.selection_point(name='company_pick',fields=['code'],on='click',clear='dblclick',empty=True)
    chart=alt.Chart(alt.Data(values=rows)).mark_circle(size=180,stroke='white',strokeWidth=2).encode(
        x=alt.X('x:Q',title=xlabel,scale=alt.Scale(zero=False)),
        y=alt.Y('y:Q',title=ylabel,scale=alt.Scale(zero=False)),
        color=alt.Color('industry:N',title='업종',scale=alt.Scale(range=[BLUE,'#00b8a9','#8b5cf6','#f59e0b']),
                        legend=alt.Legend(orient='bottom',direction='horizontal',labelLimit=160)),
        opacity=alt.condition(pick,alt.value(.95),alt.value(.25)),
        tooltip=[alt.Tooltip('name:N',title='기업'),alt.Tooltip('code:N',title='코드'),
                 alt.Tooltip('x:Q',title=xlabel,format=',.2f'),alt.Tooltip('y:Q',title=ylabel,format=',.2f')])
    return styled(chart.add_params(pick).properties(height=300).interactive())


def heatmap_chart(rows):
    base=alt.Chart(alt.Data(values=rows)).encode(x=alt.X('metric:N',title=None,axis=alt.Axis(labelAngle=-45,labelLimit=110,labelOverlap=False)),
        y=alt.Y('label:N',title=None),tooltip=[alt.Tooltip('name:N',title='기업'),
        alt.Tooltip('metric:N',title='지표'),alt.Tooltip('value_label:N',title='원값'),alt.Tooltip('score:Q',title='선택범위 상대 위치',format='.1f')])
    rect=base.mark_rect(cornerRadius=5,stroke='white',strokeWidth=4).encode(
        color=alt.condition('isValid(datum.score)',alt.Color('score:Q',scale=alt.Scale(domain=[0,100],range=['#edf5ff',BLUE]),
            legend=alt.Legend(title='지표별 상대 위치',values=[0,50,100],orient='bottom')),alt.value('#e5e8eb')))
    labels=base.mark_text(fontSize=12).encode(text='value_label:N',color=alt.condition('datum.score > 65',alt.value('white'),alt.value('#333d4b')))
    # Streamlit fits axes and legend inside this height, including narrow screens.
    return styled((rect+labels).properties(height=max(300,len({r['code'] for r in rows})*44+160)))


def waterfall_records(positions):
    """Total cost + each position's P/L = total equity value. Cash is excluded."""
    if not positions or any(not numeric(r.get('value_krw')) or not numeric(r.get('cost_krw')) for r in positions):
        return []
    start=sum(r['cost_krw'] for r in positions)
    end=sum(r['value_krw'] for r in positions)
    if not numeric(start) or not numeric(end) or max(start,end)>2**53-1 or any(r['value_krw']<0 or r['cost_krw']<0 for r in positions):
        return []
    result=[dict(order=0,label='주식 원가',start=0,end=start,amount=start,kind='합계')]
    changes=sorted(positions,key=lambda r:abs(r['value_krw']-r['cost_krw']),reverse=True)
    drivers=[(r['name']+' · '+r['code'],r['value_krw']-r['cost_krw']) for r in changes[:10]]
    if len(changes)>10:
        drivers.append((f'그 외 {len(changes)-10}종목',sum(r['value_krw']-r['cost_krw'] for r in changes[10:])))
    cursor=start
    for i,(name,change) in enumerate(drivers,1):
        result.append(dict(order=i,label=name,start=cursor,end=cursor+change,amount=change,
                           kind='이익' if change>0 else '손실' if change<0 else '변동 없음'))
        cursor+=change
    result.append(dict(order=len(result),label='주식 평가액',start=0,end=end,amount=end,kind='합계'))
    return result


def waterfall_chart(rows):
    return styled(alt.Chart(alt.Data(values=rows)).mark_bar(cornerRadius=3).encode(
        x=alt.X('label:N',sort=alt.SortField('order'),title=None,axis=alt.Axis(labelAngle=-25,labelLimit=110)),
        y=alt.Y('start:Q',title='원',scale=alt.Scale(zero=True)),y2='end:Q',
        color=alt.Color('kind:N',title=None,scale=alt.Scale(domain=['합계','이익','손실','변동 없음'],
                        range=['#4e5968','#f04452',BLUE,'#b0b8c1'])),
        tooltip=[alt.Tooltip('label:N',title='항목'),alt.Tooltip('amount:Q',title='금액 (원)',format=',.0f'),
                 alt.Tooltip('end:Q',title='누적 (원)',format=',.0f')]).properties(height=280))


def render_waterfall(result):
    rows=waterfall_records(result['holdings_review']['rows']) if result else []
    st.markdown('#### 보유 손익 기여')
    if not rows:
        st.info('워터폴 대기 · 모든 입력 보유종목의 유효 가격과 매입 원가가 필요합니다.')
        return
    st.altair_chart(waterfall_chart(rows),width='stretch',theme=None)
    st.caption('주식 원가 + 종목별 평가손익 = 주식 평가액. 현금·배당·실현손익·수수료는 제외합니다. 가장 큰 절대 손익 10종목 외에는 합산합니다.')


def price_chart(row,cutoff):
    from .core import observed_close
    bars=[dict(date=p['date'],close=p['close']) for p in row.get('prices',[])
          if p['date']<=cutoff and observed_close(row,p['date']) is not None]
    if not bars:
        return None
    return styled(alt.Chart(alt.Data(values=bars)).mark_line(color=BLUE,point=True).encode(
        x=alt.X('date:T',title=None),y=alt.Y('close:Q',title='관측 종가 (원)',scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip('date:T',title='날짜',format='%Y-%m-%d'),alt.Tooltip('close:Q',title='원',format=',.0f')]
    ).properties(height=230).interactive(bind_y=False))


def render_viewer(snapshot):
    rows=snapshot['companies']
    suffix=snapshot['meta']['data_mode']
    prefix='viewer_'+suffix+'_'
    st.caption(f"가격 {snapshot['meta']['price_date']} · 재무 {snapshot['meta']['financial_period']} {snapshot['meta']['financial_basis']} · 선택 기업 안의 비교")
    if st.button('뷰어 초기화'):
        for key in list(st.session_state):
            if key.startswith(prefix):
                del st.session_state[key]
        st.rerun()
    left,right=st.columns([1,3])
    market=left.selectbox('뷰어 시장',['전체']+sorted({r['market'] for r in rows}),key=prefix+'market')
    options=[r['code'] for r in rows if market=='전체' or r['market']==market]
    names={r['code']:r['name'] for r in rows}
    codeskey=prefix+'codes'
    if st.session_state.get(prefix+'last_market')!=market:
        st.session_state[codeskey]=options[:30]
    elif codeskey in st.session_state:
        st.session_state[codeskey]=[c for c in st.session_state[codeskey] if c in options]
    st.session_state[prefix+'last_market']=market
    codes=right.multiselect('비교할 기업 (최대 30개)',options,max_selections=30,
                           format_func=lambda c:names[c]+' · '+c,key=codeskey)
    selected=[r for r in rows if r['code'] in codes]
    st.caption(f'표시 {len(selected)} / 시장 필터 {len(options)}개 · 아래 모든 그래프와 다운로드에 같은 기업 범위를 적용합니다.')
    if not selected:
        st.info('선택한 기업이 없습니다. 기업을 선택하거나 뷰어 초기화를 누르세요.')
        return
    a,b,c=st.columns(3)
    keys=list(METRICS)
    if st.session_state.get(prefix+'x') not in keys:
        st.session_state[prefix+'x']=keys[1]
    if st.session_state.get(prefix+'bar') not in keys:
        st.session_state[prefix+'bar']=keys[4]
    x=a.selectbox('산점도 X축',keys,index=None,format_func=METRICS.get,key=prefix+'x')
    y=b.selectbox('산점도 Y축',keys,index=0,format_func=METRICS.get,key=prefix+'y')
    metric=c.selectbox('데이터바 지표',keys,index=None,format_func=METRICS.get,key=prefix+'bar')
    left,right=st.columns([1,1.35])
    event=None
    with left,st.container(border=True,key='chart_bars'):
        st.markdown('#### 기업별 지표 크기')
        bars=metric_records(selected,metric)
        if bars:
            st.altair_chart(bar_chart(bars,METRICS[metric]),width='stretch',theme=None)
        else:
            st.info('이 지표의 유효한 값이 없습니다.')
        st.caption(f'유효 {len(bars)}/{len(selected)}개 · 축은 0 기준 · 색은 값의 크기이며 투자 등급이 아닙니다.')
    with right,st.container(border=True,key='chart_scatter'):
        st.markdown('#### 두 지표의 관계')
        points=scatter_records(selected,x,y)
        if points:
            event=st.altair_chart(scatter_chart(points,METRICS[x],METRICS[y]),width='stretch',theme=None,
                                  key=prefix+'scatter',on_select='rerun',selection_mode='company_pick')
        else:
            st.info('두 지표를 함께 가진 기업이 없습니다.')
        st.caption(f'짝이 있는 값 {len(points)}/{len(selected)}개 · 점 클릭으로 기업 상세 선택, 휠로 확대 · 소수 기업으로 시장 상관관계를 추정하지 않습니다.')
    with st.container(border=True,key='chart_heatmap'):
        st.markdown('#### 지표 한눈에 보기')
        heatkeys=['operating_margin_pct','roe_pct','revenue_growth_pct','debt_ratio_pct']
        st.altair_chart(heatmap_chart(heatmap_records(selected,heatkeys)),width='stretch',theme=None)
        st.caption('셀의 숫자는 원값(%). 파랑은 지표별 선택 기업 최솟값 0 → 최댓값 100의 상대 위치입니다. 동일 값은 50, 결측은 회색. 높은 부채비율도 진하게 표시되므로 좋고 나쁨의 점수가 아닙니다.')
    chosen=prefix+'detail'
    if st.session_state.get(chosen) not in codes:
        st.session_state[chosen]=codes[0]
    picks=event.selection.get('company_pick',[]) if event else []
    picked=picks[0].get('code') if picks else None
    if picked in codes and picked!=st.session_state.get(prefix+'last_pick'):
        st.session_state[chosen]=picked
    st.session_state[prefix+'last_pick']=picked
    code=st.selectbox('자세히 볼 기업',codes,format_func=lambda c:names[c]+' · '+c,key=chosen)
    row=next(r for r in selected if r['code']==code)
    with st.container(border=True,key='chart_detail'):
        st.subheader(row['name'])
        chart=price_chart(row,snapshot['meta']['price_date'])
        if chart is None:
            st.info('관측 가격 이력이 없어 추이 그래프를 표시하지 않습니다.')
        else:
            st.altair_chart(chart,width='stretch',theme=None)
            st.caption('보존된 관측 종가 · 가격 보정 기준은 기업분석에서 확인 · 수익률/조정주가 차트가 아닙니다.')
        st.dataframe(pd.DataFrame([{'지표':label,'값':row['metrics'].get(key)} for key,label in METRICS.items()]),hide_index=True)
    export=[dict(코드=r['code'],기업=r['name'],시장=r['market'],**{label:r['metrics'].get(k) for k,label in METRICS.items()}) for r in selected]
    st.download_button('현재 비교 데이터 CSV',safe_csv(export),'viewer_comparison.csv','text/csv',on_click='ignore')
