"""Small local event panel; network access occurs only on explicit refresh."""
import json
import streamlit as st
from .market_events import EventStore, import_events, refresh_events


def render_events(root, store, codes, selection):
    with st.expander('공시·뉴스 · 출처 확인과 재검토'):
        st.caption('삼성전자 공식 뉴스룸 최신 RSS 및 설정된 DART 최근 30일 공시. '
                   '전체 언론·전체 종목을 포괄하지 않습니다. 새로고침은 수동입니다.')
        st.info('주요 이벤트 확인 전에는 보유 판단·포트폴리오 편입을 보류합니다. '
                '제목 키워드는 검토 대상 분류이며 호재·악재 판정이 아닙니다. '
                '보유·연구 입력은 화면 재실행 전에 JSON으로 내보내세요.')
        try:
            events = EventStore(store)
            if st.button('공시·뉴스 새로고침'):
                with st.spinner('공개 출처 확인 중…'):
                    refresh_events(root, store, codes)
                st.rerun()
            receipt = store.setting('market_events_refresh', {})
            if receipt:
                st.caption('최근 수집 시도 '+receipt['checked_at']+' · '+receipt['status'])
                for source, result in receipt['sources'].items():
                    st.text(f"{source}: {result['status']} · 수신 {result.get('received', 0)} · 추가 {result.get('added', 0)}")
                if receipt['status'] != 'complete':
                    st.warning('일부 출처 미확인 · 이전 저장 자료를 유지합니다. 자료 없음은 공시·뉴스 없음이라는 뜻이 아닙니다.')
            else:
                st.warning('아직 수집 결과가 없습니다. 최신 공시·뉴스 확인이 필요합니다.')
            uploaded = st.file_uploader('공시·뉴스 JSON 입력 (market-events-0.1)', type=['json'], key='event_upload')
            if uploaded and st.button('공시·뉴스 파일 적용'):
                if uploaded.size > 5*1024*1024:
                    raise ValueError('입력 크기 제한')
                added = import_events(json.loads(uploaded.getvalue()), events, codes)
                st.success(f'{added}건 추가 · 출처 내용을 검토하세요.')
            rows = events.list(selection)
            if not rows:
                st.write('선택 종목의 저장 이벤트 없음 · 미수집 가능')
            st.caption('뉴스룸은 발행 기업 기준 연결입니다. 기사별 대상 기업과 투자 관련성은 원문에서 확인하세요. '
                       '확인 표시는 현재 상태이며 과거 검토 이력을 재현하지 않습니다.')
            page = st.number_input('이벤트 페이지 (30건씩)', min_value=1,
                                   max_value=max(1, (len(rows)+29)//30), value=1, step=1)
            for event in rows[(page-1)*30:page*30]:
                st.text(event['title'])
                st.link_button('원문 열기', event['url'])
                st.caption(f"{event['source']} · 발표 {event['published_at'] or event['published_on']+' (시각 미제공)'} · "
                           f"첫 수집 {event['first_seen_at']} · {'정정 자료 · ' if event['correction'] else ''}"
                           f"{'주요 이벤트' if event['needs_review'] else '참고 뉴스'}")
                if event['needs_review']:
                    if st.button('확인 취소' if event['reviewed'] else '원문·투자 논리 검토 완료', key='event_'+event['version']):
                        events.mark_reviewed(event['version'], not event['reviewed'])
                        st.rerun()
            if len(rows) > 30:
                st.caption(f'저장 {len(rows)}건. 미확인 주요 이벤트가 남으면 판단을 보류합니다.')
        except Exception as error:
            st.warning('공시·뉴스 처리 미완료 · 기존 시장 자료 유지 · '+type(error).__name__)
