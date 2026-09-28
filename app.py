r"""Run: .venv\Scripts\python.exe -m streamlit run app.py"""
import json
import copy
from pathlib import Path
from statistics import median
import pandas as pd
import streamlit as st
from investment.core import validate_snapshot,evaluate,eligible,peers,percentile,safe_csv,num,digest
from investment.store import Store
from investment.fixture import make_fixture
from investment import research,trend
from investment.report import onepager
from investment.metrics import additional
from investment.local_config import load_local

ROOT=Path(__file__).resolve().parent
LABELS={'market_cap_eok':'시가총액 (억원)','operating_margin_pct':'영업이익률 (%)','roe_pct':'ROE (%)','debt_ratio_pct':'부채비율 (%)','net_debt_equity_pct':'순차입금/자본 (%)','interest_coverage_x':'이자보상배율 (배)','current_ratio_pct':'유동비율 (%)','revenue_growth_pct':'매출 증가율 (%)','foreign_net_20d_eok':'외국인 20일 순매수 (억원)','institution_net_20d_eok':'기관 20일 순매수 (억원)','foreign_net_turnover_20d_pct':'외국인 순매수/거래대금 (%)','institution_net_turnover_20d_pct':'기관 순매수/거래대금 (%)','avg_trading_value_20d_eok':'20일 평균 거래대금 (억원)','eps_ttm':'TTM EPS (원)','price':'가격 (원)','per':'PER (배)','pbr':'PBR (배)'}
STATUS={'pass':'충족','fail':'미충족','unknown':'자료 부족'}
st.set_page_config(page_title='INVESTMENT 연구 대시보드',layout='wide')
st.title('INVESTMENT · 기업 탐색과 연구')
local=load_local(ROOT)
profile=local.get('profile','unknown')
st.sidebar.caption(f'현재 PC 프로필: {profile} · 자동 수집/주문 없음')
mode_label=st.sidebar.selectbox('데이터 모드',['실제 저장자료','가상 테스트'])
mode='fixture' if mode_label=='가상 테스트' else 'user_input'
store=Store(local['data_dir'],profile,mode)
manual_path=local.get('manual_snapshot_file')
source_key='snapshot_'+mode
if source_key not in st.session_state:
    saved=store.latest()
    st.session_state[source_key]=saved or (make_fixture() if mode=='fixture' else json.loads(manual_path.read_text(encoding='utf-8')) if profile!='unknown' and 'infomax_manual' in local['enabled_data_adapters'] and manual_path is not None and manual_path.is_file() else None)
uploaded=st.sidebar.file_uploader('동일 모드 스냅샷 JSON',type=['json'])
if uploaded and st.sidebar.button('입력 적용'):
    try:
        candidate=validate_snapshot(json.loads(uploaded.getvalue()))
        if candidate['meta']['data_mode']!=mode: raise ValueError('선택한 데이터 모드와 파일이 다릅니다')
        st.session_state[source_key]=candidate
        st.sidebar.success('입력 검증 통과')
    except (ValueError,KeyError,TypeError): st.sidebar.error('입력 검증 실패 · 기존 자료 보존')
snapshot=st.session_state[source_key]
if not snapshot:
    st.info('실제 저장자료가 없습니다. 파일을 입력하거나 가상 테스트 모드를 직접 선택하세요.')
    st.stop()
validate_snapshot(snapshot)
if st.sidebar.button('현재 스냅샷을 이 PC에 저장'):
    store.save_snapshot(snapshot); st.sidebar.success('SQLite 저장 완료')
snapshot=copy.deepcopy(snapshot)
for row in snapshot['companies']:
    extra,missing=additional(row,snapshot)
    row['metrics'].update(extra)
    row.setdefault('metric_missing_reasons',{}).update(missing)
for n in (3,5): LABELS[f'revenue_cagr_{n}y_pct']=f'매출 {n}년 CAGR (%)'
LABELS.update(revenue_ttm_eok='TTM 매출 (억원)',op_ttm_eok='TTM 영업이익 (억원)',parent_income_ttm_eok='TTM 지배주주 순이익 (억원)',fcf_proxy_eok='FCF 프록시 (억원)')
for n in (5,60):
    for prefix,name in [('foreign','외국인'),('institution','기관')]:
        LABELS[f'{prefix}_net_{n}d_eok']=f'{name} {n}일 순매수 (억원)'
        LABELS[f'{prefix}_net_turnover_{n}d_pct']=f'{name} {n}일 순매수/거래대금 (%)'
meta=snapshot['meta']; all_rows=[r for r in snapshot['companies'] if eligible(r)]
if not all_rows: st.info('적격 비금융 보통주 없음'); st.stop()
st.warning(('가상 테스트 · 실제 기업/시장 관측 아님' if mode=='fixture' else '실제 저장자료 · 부분 모집단 · 새 API 조회 없음')+f" | 가격 {meta['price_date']} | 재무 {meta['financial_period']} {meta['financial_basis']}")
st.caption(f"적재 {len(snapshot['companies'])}개 · 적격 {len(all_rows)}개 · 전체시장 수 {meta.get('universe_total') if meta.get('universe_total') is not None else '미확인'} · 실제 공급자 정의·과거 빈티지 미검증")
res=research.analyze(snapshot); by_code={r['code']:r for r in res}; trends=trend.analyze(snapshot)
selection=st.sidebar.selectbox('분석할 기업',[r['code'] for r in all_rows],format_func=lambda code:next(r['name']+' · '+code for r in all_rows if r['code']==code))
company=next(r for r in all_rows if r['code']==selection)
tabs=st.tabs(['조건검색','기업분석','산업비교','A4 One-Pager','장기성장 연구','추세 연구','기존 보유·포트폴리오','데이터 상태'])
with tabs[0]:
    st.subheader('사용자 지정 조건검색')
    default={'logic':'AND','rules':[{'metric':'operating_margin_pct','op':'gte','value':10}]}
    saved=store.setting('screen',default)
    rule_text=st.text_area('조건 JSON',json.dumps(saved,ensure_ascii=False,indent=2),key='rules_'+mode,height=170)
    markets=['전체','KOSPI','KOSDAQ']; industries=['전체']+sorted({r['industry'] for r in all_rows})
    defaults={'market':saved.get('market') or '전체','industry':saved.get('industry') or '전체','path':saved.get('path','없음'),'order':saved.get('sort_metric','market_cap_eok'),'ascending':saved.get('ascending',False)}
    for key,value in defaults.items(): st.session_state.setdefault(key+'_'+mode,value)
    if st.button('조건 JSON 적용'):
        try:
            incoming=json.loads(rule_text)
            evaluate(all_rows[0],incoming['rules'],incoming['logic'])
            if any(r['metric'] not in LABELS for r in incoming['rules']): raise ValueError('지표 오류')
            im=incoming.get('market') or '전체'; ii=incoming.get('industry') or '전체'
            ip=incoming.get('path','없음'); io=incoming.get('sort_metric','market_cap_eok')
            if im not in markets or ii not in industries or ip not in ['없음']+list(research.PATHS) or io not in LABELS: raise ValueError('필터 오류')
            for key,value in dict(market=im,industry=ii,path=ip,order=io,ascending=bool(incoming.get('ascending',False))).items(): st.session_state[key+'_'+mode]=value
            st.success('조건 JSON 적용 완료')
        except (ValueError,KeyError,TypeError): st.error('조건 JSON 적용 실패 · 기존 필터 보존')
    c1,c2,c3=st.columns(3)
    market=c1.selectbox('시장',markets,key='market_'+mode); industry=c2.selectbox('산업',industries,key='industry_'+mode); show=c3.selectbox('판정',['전체','충족','미충족','자료 부족'])
    path=st.selectbox('성장 경로 추가 필터',['없음']+list(research.PATHS),format_func=lambda p:research.NAMES.get(p,p),key='path_'+mode)
    order=st.selectbox('정렬 지표',list(LABELS),format_func=lambda k:LABELS[k],key='order_'+mode)
    ascending=st.checkbox('오름차순',key='ascending_'+mode)
    try:
        settings=json.loads(rule_text); rules=settings['rules']; logic=settings['logic']
        if len(rules)>30 or any(r['metric'] not in LABELS for r in rules): raise ValueError('조건 형식')
        output=[]
        for r in all_rows:
            if (market!='전체' and r['market']!=market) or (industry!='전체' and r['industry']!=industry): continue
            state,individual=evaluate(r,rules,logic)
            if path!='없음':
                p=by_code[r['code']]['paths'][path]
                extra=p['signal_status'] if p['evidence_status']=='confirmed' else 'unknown' if p['signal_status']!='fail' else 'fail'
                from investment.core import combine
                state=combine([state,extra])
            if show!='전체' and STATUS[state]!=show: continue
            output.append(dict(코드=r['code'],기업=r['name'],판정=STATUS[state],조건별=' / '.join(STATUS[v] for v in individual),정렬값=r['metrics'].get(order)))
        output.sort(key=lambda r:(r['정렬값'] is None,(r['정렬값'] or 0)*(1 if ascending else -1),r['코드']))
        st.write(f'검색 결과 {len(output)}개 · 조건을 자동 완화하지 않습니다.')
        st.dataframe(pd.DataFrame(output),hide_index=True)
        settings.update(market='' if market=='전체' else market,industry='' if industry=='전체' else industry,path=path,sort_metric=order,ascending=ascending)
        if st.button('조건 저장'):
            store.save_setting('screen',settings); st.success('조건 저장 완료 · 재실행 후 복원')
        st.download_button('조건 JSON 내보내기',json.dumps(settings,ensure_ascii=False,indent=2),'screen_conditions.json','application/json',on_click='ignore')
        st.download_button('결과 CSV 내보내기',safe_csv(output),'screen_results.csv','text/csv',on_click='ignore')
    except (ValueError,KeyError,TypeError): st.error('조건 형식 오류 · metric/op/value, AND/OR를 확인하세요.')
with tabs[1]:
    st.subheader(company['name'])
    st.dataframe(pd.DataFrame([{'지표':LABELS.get(k,k),'값':v,'부족 사유':company.get('metric_missing_reasons',{}).get(k,'')} for k,v in company['metrics'].items()]),hide_index=True)
    st.caption('거래 유동성(거래대금)과 재무 유동성(유동비율)은 별개입니다.')
    history=company.get('annual',[])
    if history:
        st.line_chart(pd.DataFrame(history).set_index('period_end')[['revenue','op']])
    else: st.info('완료 연도 재무 원계정 미확보 · 연간 추이/ROIC/CAGR 계산 대기')
    prices=company.get('prices',[])
    if prices: st.line_chart(pd.DataFrame(prices).set_index('date')[['close']])
    else: st.info('연구용 정규화 OHLCV 미연결')
    st.write('경로 상태',by_code[selection]['paths'])
    for note in company.get('data_quality',[]): st.caption(note)
with tabs[2]:
    st.subheader('동일 산업 비교 · 검색 결과와 독립')
    custom=st.multiselect('사용자 피어 코드 (비우면 공급자 업종)',[r['code'] for r in all_rows],default=store.setting('peers_'+selection,[]))
    if st.button('피어집합 저장'): store.save_setting('peers_'+selection,custom); st.success('피어집합 저장 완료')
    pool=peers(snapshot,company,custom or None)
    st.caption(f'공급자 업종 / 사용자 피어 · GICS 아님 · 모집단 {len(pool)}개 · 동일 재무기간·회계기준')
    comparison=[]
    for key,label in LABELS.items():
        vals=[r['metrics'].get(key) for r in pool if num(r['metrics'].get(key))]
        pct=percentile(company['metrics'].get(key),vals)
        comparison.append({'지표':label,'기업':company['metrics'].get(key),'중앙값':median(vals) if vals else None,'유효 표본':len(vals),'상대 백분위':pct*100 if pct is not None else None})
    st.dataframe(pd.DataFrame(comparison),hide_index=True)
    st.caption('유효 표본 5개 미만이면 백분위는 표시하지 않습니다. 전체 시장 산업 통계가 아닙니다.')
with tabs[3]:
    st.subheader('A4 One-Pager')
    html=onepager(snapshot,company,by_code[selection])
    st.iframe(html,height=850)
    st.download_button('인쇄용 HTML 다운로드',html,f'{selection}_onepager.html','text/html',on_click='ignore')
    st.caption('HTML을 브라우저에서 열어 인쇄 → A4 / 배율 100%. 출처가 많은 경우 요약 개수를 표시합니다.')
with tabs[4]:
    st.subheader('한국형 장기성장 연구 · 100-Bagger 참고 모형')
    st.info('자료 내용 / 프로젝트 구현 가설 / 관측 데이터를 분리합니다. 100배 수익이나 성공 확률을 예측하지 않습니다.')
    view=st.radio('연구 보기',['기존 품질','다섯 경로','주간 목록','성장 단계·지속성','자료·가설'],horizontal=True)
    if view=='기존 품질':
        st.dataframe(pd.DataFrame([dict(기업=r['name'],S_quality=r['quality_score'],부족=', '.join(r['quality_missing']),**r['factors']) for r in res]),hide_index=True)
        st.caption('시장 적격 모집단의 중간순위 백분위. Q/G/C/V/B 가중치 30/25/20/15/10%. 결측 기업 가중치 재배분 없음.')
    elif view=='다섯 경로':
        st.dataframe(pd.DataFrame([dict(기업=r['name'],경로=research.NAMES[p],수치=STATUS[v['signal_status']],근거=v['evidence_status'],후보=v['eligible'],사유=v['reason']) for r in res for p,v in r['paths'].items()]),hide_index=True)
        st.json(by_code[selection]['signals'])
    elif view=='주간 목록':
        balanced=research.balanced_list(res); st.write(f'경로 균형 연구 목록 {len(balanced)}개 · 최대 두 차례 순회 · 최대 10개')
        st.dataframe(pd.DataFrame(balanced),hide_index=True)
    elif view=='성장 단계·지속성':
        st.write(by_code[selection]['stage_tags'] or '투자·매출·이익률·환원 단계 근거 미입력')
        st.write(by_code[selection]['persistence'])
    else:
        st.markdown((ROOT/'RESEARCH_MODEL.md').read_text(encoding='utf-8'))
with tabs[5]:
    st.subheader('추세추종 연구 · 매매 실행 없음')
    st.caption('SMA50/150/200, 200일선 20일 상승, R126·RS126 양수. 수축 프록시와 돌파 관찰을 별도 표시합니다.')
    st.dataframe(pd.DataFrame([{k:r.get(k) for k in ('code','name','status','reason','score','rs126','rs252','contraction','breakout')} for r in trends]),hide_index=True)
    st.write('조건 충족 상위 최대 10개',[r['name'] for r in trends if r['status']=='pass' and r['score'] is not None][:10])
    if company.get('prices'):
        frame=pd.DataFrame(company['prices']).set_index('date')
        for n in (50,150,200): frame[f'SMA{n}']=frame['close'].rolling(n).mean()
        st.line_chart(frame[['close','SMA50','SMA150','SMA200']]); st.bar_chart(frame[['volume']])
with tabs[6]:
    st.caption('보존한 기존 수동 보유·포트폴리오 앱. 별도 입력 계약이며 계좌 자동 수집 없음.')
    st.iframe(ROOT/'INVESTMENT_Dashboard.html',height=900)
with tabs[7]:
    st.subheader('연결과 검증 상태')
    manual_status=('현재 가상 모드 · 실제 자료 연결 판정 안 함' if mode=='fixture' else
                   '이 PC 수동 파일 있음 · 자동 연동/외부 저장 권한 미확인' if 'infomax_manual' in local['enabled_data_adapters'] and manual_path is not None and manual_path.is_file() else
                   '이 PC 수동 파일 미설정 · 자동 연동/외부 저장 권한 미확인')
    st.table(pd.DataFrame([['키움 REST','인증·공식 TR 단위/범위 및 조회 권한 설정 대기'],['OpenDART','API 키 및 회사 고유번호 설정 대기'],['인포맥스',manual_status]],columns=['공급자','상태']))
    st.write('스냅샷 ID',digest(snapshot)); st.write('프로필/저장소',profile+'/'+mode)
    st.json(meta)
