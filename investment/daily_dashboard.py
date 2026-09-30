"""Daily readout of existing market, event and portfolio engines. Session-only input."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from .core import observed_close
from .market_events import EventStore
from tools.verify_portfolio_data import verify

OPINIONS = {'HOLD':'보유 검토','WAIT':'판단 보류','SELL':'매도 검토',
            'REDUCE':'비중 축소 검토','REVIEW':'재검토'}
STATES = {'SETTINGS_REQUIRED':'구성 설정 확인 필요','DATA_REQUIRED':'자료 보완 필요',
          'MODEL_PROPOSAL':'조건부 모의 구성안','CASH_ONLY':'조건상 현금 모의안'}
SOURCE_STATES = {'complete':'확인 완료','partial':'일부 미확인','unavailable':'확인 불가',
                 'setup_pending':'연결 설정 대기','failed':'실패','cached':'캐시 사용',
                 'unchanged':'변경 없음','retry_wait':'재확인 대기'}


def event_context(store, codes):
    """Read only local metadata; no refresh or network in the daily view."""
    events = EventStore(store)
    rows = [event for code in codes for event in events.list(code)]
    return dict(pending=events.pending(codes), rows=rows,
                receipt=store.setting('market_events_refresh', {}), error=None)


def market_rows(snapshot, pending):
    result = []
    for row in snapshot['companies']:
        price = observed_close(row, snapshot['meta']['price_date'])
        result.append(dict(코드=row['code'], 기업=row['name'],
            관측종가=price['close'] if price else None,
            가격일=price['date'] if price else None,
            주요이벤트=len(pending.get(row['code'], [])) if pending is not None else None))
    return result


def daily_model(snapshot, receipt, context, holdings=None, policy=None, as_of=None):
    pending = context['pending']
    rows = market_rows(snapshot, pending)
    analysis, error = None, None
    if snapshot['meta']['data_mode']=='user_input':
        try:
            analysis = verify(snapshot, holdings=holdings, policy=policy, events=pending, as_of=as_of)
        except Exception as exc:
            error = type(exc).__name__
    issues = []
    stale=(snapshot['meta']['price_date']<receipt['target_date'] if receipt and receipt.get('target_date')
           else receipt.get('stale') if receipt else None)
    if stale:
        issues.append('가격 자료가 오래되었습니다. Infomax에서 조회·저장한 뒤 데이터 새로고침을 실행하세요.')
    missing = sum(row['관측종가'] is None for row in rows)
    if missing:
        issues.append(f'{missing}개 종목의 기준일 관측 종가가 없습니다. 가격 이력을 포함한 저장자료가 필요합니다.')
    if pending is None:
        issues.append('공시·뉴스 검토 상태를 읽지 못했습니다. 기업분석에서 연결 상태를 확인하세요.')
    elif any(pending.values()):
        issues.append('미확인 주요 공시·뉴스가 있습니다. 원문과 투자 논리를 검토하세요.')
    if context['receipt'].get('status')!='complete':
        issues.append('공시·뉴스 일부 출처가 미확인입니다. 빈 목록을 이벤트 없음으로 해석하지 마세요.')
    if holdings is None:
        issues.append('보유·연구 JSON을 불러오면 실제 입력에 대한 보유 판단을 요약합니다.')
    if analysis and analysis['ready_count']<analysis['candidate_count']:
        issues.append('편입 조건 미충족 후보가 있습니다. 아래 기업별 부족 사유를 확인하세요.')
    return dict(market=rows, analysis=analysis, error=error, issues=issues)


def _inputs(snapshot, context, key):
    st.session_state.setdefault(key, None)
    policy_key=key+'_policy'
    st.session_state.setdefault(policy_key, {})
    with st.expander('보유·연구 입력과 구성 설정'):
        st.caption('입력은 이 브라우저 세션에만 유지합니다. DB에 자동 저장하지 않습니다. '
                   '상세 보유 화면에서 편집한 내용은 JSON으로 내보낸 뒤 여기서 다시 불러오세요.')
        uploaded=st.file_uploader('일일 요약용 보유·연구 JSON',type=['json'],key=key+'_upload')
        if uploaded:
            st.text('선택 파일: '+uploaded.name)
        if st.button('일일 요약에 입력 적용',disabled=uploaded is None):
            try:
                if uploaded.size>12*1024*1024:
                    raise ValueError('크기 제한')
                candidate=json.loads(uploaded.getvalue())
                if not isinstance(candidate,dict) or candidate.get('mode')!='user_input':
                    raise ValueError('실제 보유 입력 필요')
                verify(snapshot,holdings=candidate,events=context['pending'])
                st.session_state[key]=candidate
                st.success('검증된 입력을 일일 요약과 상세 보유 화면에 연결했습니다.')
            except Exception as error:
                st.error('입력 검증 실패 · 기존 입력 유지 · '+type(error).__name__)
        if st.session_state[key] is not None:
            st.download_button('입력 원본 보관',json.dumps(st.session_state[key],ensure_ascii=False,indent=2),
                               'holdings_private.json','application/json',on_click='ignore')
            if st.button('일일 요약 입력 비우기'):
                st.session_state[key]=None
                st.rerun()
        st.caption('구성 설정은 개발 가정입니다. 적합성이 검증된 투자 기준이 아닙니다.')
        saved=st.session_state[policy_key]
        with st.form('daily_policy'):
            cols=st.columns(3)
            p=dict(maxCompanies=cols[0].number_input('최대 기업 수',1,5,int(saved.get('maxCompanies',5))),
                   companyCapPct=cols[1].number_input('기업당 상한 (%)',1.0,100.0,float(saved.get('companyCapPct',25))),
                   minCashPct=cols[2].number_input('최소 현금 (%)',0.0,100.0,float(saved.get('minCashPct',20))))
            cols=st.columns(2)
            p['sectorCapPct']=cols[0].number_input('산업별 상한 (%)',1.0,100.0,float(saved.get('sectorCapPct',40)))
            p['groupCapPct']=cols[1].number_input('공통 위험군 상한 (%)',1.0,100.0,float(saved.get('groupCapPct',40)))
            p['stressShockPct']=cols[0].number_input('주식 동반 하락 가정 (%)',-100.0,-1.0,float(saved.get('stressShockPct',-30)))
            p['stressLossLimitPct']=cols[1].number_input('가정 시나리오 손실 기준 (%)',0.1,100.0,saved.get('stressLossLimitPct'))
            st.caption('시나리오 손실 기준은 실제 손실 한도나 보장이 아닙니다. 가격 기한 4일·연구 검토 기한 120일을 적용합니다.')
            confirmed=st.checkbox('이 설정과 가정의 한계를 확인했습니다',value=False)
            if st.form_submit_button('구성 설정 적용'):
                try:
                    p['policyConfirmed']=confirmed
                    verify(snapshot,holdings=st.session_state[key],policy=p,events=context['pending'])
                    st.session_state[policy_key]=p
                except Exception as error:
                    st.error('설정 검사 실패 · 이전 설정 유지 · '+type(error).__name__)
    return st.session_state[key],st.session_state[policy_key]


def render_daily(snapshot, receipt, context):
    today=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    st.caption(f'{today} · 한국 시간 · 조건검색 필터와 독립')
    st.caption('기업가격·뉴스는 저장 스냅샷 범위, 보유·편입 판단은 불러온 연구와 저장 종목을 함께 사용합니다.')
    if snapshot['meta']['data_mode']=='fixture':
        st.info('가상 테스트 모드입니다. 실제 보유·뉴스 캐시를 연결하지 않습니다. 아래 상세 탭에서 기존 기능을 시험할 수 있습니다.')
        st.dataframe(pd.DataFrame(market_rows(snapshot,{})),hide_index=True)
        return None,{}
    holdings,policy=_inputs(snapshot,context,'daily_holdings_user_input')
    model=daily_model(snapshot,receipt,context,holdings,policy)
    result=model['analysis']
    pending_count=(sum(e['needs_review'] and not e['reviewed'] for e in context['rows'])
                   if context['pending'] is not None else None)
    cols=st.columns(4)
    cols[0].metric('가격 기준일',snapshot['meta']['price_date'])
    cols[1].metric('편입 조건 충족',f"{result['ready_count']} / {result['candidate_count']}" if result else '미확인')
    review_rows=result['holdings_review']['rows'] if result else []
    cols[2].metric('보유 검토 대기',f"{sum(r['opinion']!='HOLD' or r['overweight'] for r in review_rows)} / {len(review_rows)}" if holdings is not None and result else '미입력' if holdings is None else '미확인')
    cols[3].metric('미확인 주요 이벤트',str(pending_count) if pending_count is not None else '미확인')
    st.caption('편입 조건 충족은 구성안 확정과 다릅니다. 보유 검토 대기는 판단 보류·재검토·축소·매도 검토 및 기업 비중 초과를 포함합니다.')
    if model['issues']:
        st.info(model['issues'][0])
    with st.expander(f"확인할 항목 · {len(model['issues'])}개"):
        for item in model['issues']:
            st.write('• '+item)
        if not model['issues']:
            st.write('현재 입력에서 추가 확인 항목이 없습니다. 수집 범위 밖 사건은 별도로 확인하세요.')
        if receipt:
            st.caption(f"시장자료 최근 확인 {receipt.get('checked_at','미확인')} · 상태 {SOURCE_STATES.get(receipt.get('status'),'미확인')} · "
                       f"마지막 정상 자료 사용 {'예' if receipt.get('fallback') else '아니오'}")
        if model['error']:
            st.warning('보유·구성안 계산 미완료 · '+model['error']+' · 데이터·뉴스 확인은 계속할 수 있습니다.')
    st.markdown('#### 저장 기업과 가격')
    frame=pd.DataFrame(model['market'])
    frame['관측종가']=pd.to_numeric(frame['관측종가'])
    frame['가격일']=frame['가격일'].fillna('미확인')
    st.dataframe(frame.style.format({'관측종가':'{:,.0f}'},na_rep='—'),hide_index=True,
                 column_config={'관측종가':st.column_config.NumberColumn('관측 종가 (원)'),
                                '주요이벤트':st.column_config.NumberColumn('미확인 주요 이벤트 (최대 100)')})
    st.caption('관측 종가가 없는 칸은 결측입니다. 기업분석 탭에서 가격 이력과 출처를 확인하세요.')
    from .visuals import metric_records,bar_chart,render_waterfall
    with st.container(border=True):
        st.markdown('#### 저장 기업의 수익성 비교')
        bars=metric_records(snapshot['companies'],'roe_pct')
        if bars:
            st.altair_chart(bar_chart(bars,'ROE (%)'),width='stretch',theme=None)
            st.caption(f'저장 기업 {len(bars)}개의 유효 ROE · 현재 재무기간·회계기준 · 기업 순위나 매수 의견이 아닙니다.')
        else:
            st.info('ROE 자료가 없어 비교 그래프를 표시하지 않습니다.')
        st.caption('좌측 인터랙티브 뷰어에서 지표·기업을 바꾸거나 산점도의 점을 선택해 탐색하세요.')
    left,right=st.columns(2)
    with left:
        st.markdown('#### 보유종목 판단')
        if holdings is None:
            st.info('보유 입력 대기 · 위 입력 영역에서 보유·연구 JSON을 불러오세요.')
        elif result and not review_rows:
            st.info('입력한 보유목록이 비어 있습니다.')
        elif result:
            total=result['holdings_review']['book']['total_krw']
            st.metric('입력 보유 평가액 + 현금',f'{total:,.0f}원' if total is not None else '산출 대기')
            st.dataframe(pd.DataFrame([dict(기업=r['name'],판단=OPINIONS[r['opinion']],수량=r['quantity'],
                평가액=r['value_krw'],확인사항=' / '.join(r['reasons']),비중검토=r['portfolio_action']) for r in review_rows]),hide_index=True)
            st.caption('입력 범위의 평가액입니다. 일부 가격·현금이 없으면 총액·비중을 산출하지 않습니다.')
    with right:
        st.markdown('#### 최대 5기업 포트폴리오')
        if result:
            st.write(STATES[result['portfolio_status']])
            if result['selected']:
                st.dataframe(pd.DataFrame([dict(기업=r['name'],목표비중=r['weight_pct']) for r in result['selected']]),hide_index=True)
            if result['cash_pct'] is not None:
                st.metric('모의 목표 현금',f"{result['cash_pct']:g}%")
            else:
                st.caption('목표 비중·현금 산출 대기. 부족한 자료를 현금 100% 권고로 바꾸지 않습니다.')
            st.caption(result['message'])
            with st.expander('후보별 편입 준비와 부족 사유'):
                st.dataframe(pd.DataFrame([dict(기업=r['name'],준비='충족' if r['ready'] else '확인 필요',
                    사유=' / '.join(r['reasons'])) for r in result['candidates']]),hide_index=True)
    with st.expander('보유 평가액을 만든 손익 · 워터폴',expanded=holdings is not None):
        render_waterfall(result)
    st.markdown('#### 공시·뉴스 확인')
    er=context['receipt']
    st.caption(f"최근 수집 확인 {er.get('checked_at','없음')} · {SOURCE_STATES.get(er.get('status'),'미수집')} · 삼성 뉴스룸 및 설정된 DART 범위")
    if er.get('status')!='complete' or context['error']:
        st.warning('일부 출처 미확인 · 수집된 목록만 표시합니다. 기업분석 탭에서 새로고침과 원문 검토를 진행하세요.')
    rows=sorted(context['rows'],key=lambda e:(not e['reviewed'] and e['needs_review'],e['published_on']),reverse=True)
    names={r['code']:r['name'] for r in snapshot['companies']}
    if rows:
        st.dataframe(pd.DataFrame([dict(기업=names.get(e['code'],e['code']),제목=e['title'],발표일=e['published_on'],
            출처=e['source'],검토='확인 완료' if e['reviewed'] else '검토 필요' if e['needs_review'] else '참고',원문=e['url']) for e in rows[:10]]),
            hide_index=True,column_config={'원문':st.column_config.LinkColumn('원문',display_text='열기')})
        st.caption(f'검토 필요 우선, 발표일 내림차순 · 최근 최대 10건 / 저장 {len(rows)}건. 전체 목록은 기업분석 탭에서 확인하세요.')
    else:
        st.info('표시할 저장 이벤트 없음 · 미수집 가능')
    return holdings,policy
