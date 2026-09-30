# Advanced Visuals · 2026-09-30

기존 통합 HTML의 메뉴에서 Advanced Visuals를 선택한다. workspace_export/live_dashboard가 공급하는 discovery.snapshot + discovery.research를 사용하며, 분석 상세와 보유 엔진에는 원래 analysis_snapshot 및 iframe의 검토 입력만 유지한다. 새 의존성은 없다.

전체 후보를 샘플링 없이 ROE × PER 10×10 셀에 집계하고, 결측을 따로 센다. 끝 셀은 범위 밖 수치를 포함한다. 결과 수 / 원본 모집단 / 표시 수를 표시하고 종목 목록은 페이지당 25개다. 시장·업종·ROE·PER/PBR·가격 RS·52주 하락폭·가격 추세 필터는 DiscoveryEngine.filter를 재사용한다. RS 순위를 필터 모집단으로 다시 계산하지 않는다.

선택 기업은 기존 technical.series와 지표별 metric_details, 저장된 events만 표시한다. 뉴스 부재는 이벤트 위험 없음이 아니다. 공개 참고 수치와 검토 상세 연결을 구분하고 기간·CFS/OFS 미확인은 unknown으로 유지한다. 기존 간단 분석 버튼에서 원래 보완자료/원문 연결로 이동한다.

보유 화면은 iframe의 INVESTMENT_GET_HOLDINGS / INVESTMENT_GET_POLICY를 읽고 PortfolioEngine.reviewHoldings / propose의 결과를 표시한다. 비중·손익·판단 근거와 최대 5종목 구성안은 기존 엔진 결과다. 공분산 위험 기여도는 자료 미연결로 unknown이다. 매크로 맵은 관계 탐색 구조만 제공하며 연결 강도는 unavailable이다.

필터와 선택 코드만 sessionStorage에 저장한다. 보유·인증정보를 추가 저장하거나 서버에 보내지 않는다. 새로고침 후 탭·필터·선택을 복원한다. 보유 자체의 일반 새로고침 복원 정책은 기존 화면을 따른다.

검증: node tests/test_advanced_visuals.js, Python tests/test_advanced_visuals_ui.py. ADVANCED_SCALE_FIXTURE=1이면 2,455개 별도 가상 발굴 후보를 주입하며 기존 상세 8개와 분리한다. ADVANCED_ACTUAL_HTML은 실제 기존 내보내기 HTML 경로를 명시하면 읽기 전용으로 그 자료를 검증한다. 실자료를 Git에 포함하지 않는다.

이 PC에는 실제 2,455개 공개 캐시가 없다. 회사 PC에서 main 수신 후 기존 저장자료로 내보내기/서버를 다시 열고 실제 2,455개·일봉 2,454개·RS 2,290개 및 출처를 확인해야 실데이터 완료 기준을 충족한다. 이 수치를 상수로 화면에 만들어 넣지 않았다. 전체 데이터 및 포트폴리오 엔진 결과의 부족은 unknown/unavailable로 보존한다.
