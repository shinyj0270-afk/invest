# CURRENT HANDOFF

Updated: 2026-10-07 15:00 KST
Handoff version: 2026-10-07-close-1
Last agent: Codex
Last PC: work (company Primary)
Last task: 추세추종 및 포트폴리오 위험·시계열 공유 마감

Completed:
- 기업 찾기에 추세추종 → 조건검색 → 산업별 후보 탭. 기본 시총1,000억원 이상·RS70, 시장/산업/종목 차트와 확대·8조건·거래량/수축 참고 점검.
- 최대5종목 추천의 집중도·상관·변동성·drawdown·위험 기여, 선택 기업의 수익률/상대성과·변동성·낙폭 시계열. 작성 당시 기록과 최신 재점검 분리.
- 이번 CLOSE: 공유269개 경고0, 격리 portable16명령(단위검사 포함)/실자료 없는 home AppTest/합성 UI6개 PASS. 실제 자료 검산은 앞선 PROJECT_STATE 기록이며 이번 재실행은 아님.

Pending:
- home 수신/실행과 현재 운영 서버의 새 코드 로딩 미확인.
- 대시보드 P2: 동일 기간 재무 병합 시 DART 부족 계정 소실, 자동 재로드 후 미저장 추천 사유 소실, 안내18:30/실제20:30 불일치.
- 비12월 결산6개/정기공시 조회 미제공6개/USD1개 및 기존기업 일부 계정/기간·가격084180 후속: docs/FINANCIAL_COMPLETION.md.
- ETF/기관/촉매/FTD/분산일·자동 베이스 패턴, 개인 위험 한도·권리변동 전체 보정·공식 달력은 검증 대기.

Next task: 다음 PC에서 수신·화면 확인 후 대시보드 P2 세 건 수정
Next action:
- 집 PC에서는 INVESTMENT START로 clean main 안전 점검 후 ff-only 수신한다. PROJECT_STATE/CURRENT_HANDOFF/AGENTS/SYNC_CONTRACT와 docs/TREND_FOLLOWING.md, docs/PORTFOLIO_RISK.md를 읽는다. 실행 중인 기존 서버가 있으면 종료 후 scripts/open-investment.cmd로 새 코드를 실행하고 추세추종·위험 화면을 확인한다.
- 개발은 work/Primary 한 쓰기 세션에서 진행한다. live_dashboard의 기업조회/전체화면/추천생성 병합을 financial_table.merge_financials의 계정별 보완으로 통일(인포맥스 우선·1억원 미만 오차 무시·종목/연결별도/기간/출처 보존), workspace 재로드의 미저장 사유 복원, 종가 안내20:30 일치. 합성 회귀와 실제 저장자료 읽기 대조를 완료 판정 근거로 남긴다.
Recommended next agent: Codex
Recommended model: 현재 선택 모델 유지
Recommended reasoning: 금융·자료 계약 변경에 충분한 검토 수준
Escalation condition: 다른 쓰기 세션·divergence·예상 밖 로컬 변경은 보존 후 자동 통합 중단. 대규모 구조/자료 계약 변경은 High 검토. 미확인 환율·권리변동·개인 한도는 추정 금지.
Branch: main
Commit: be1c1e1ce36f12195900e1f2836b6407de2e83cd (마감 시작 기준; 구현 commit 생성 전)
Remote status: origin/main; verification pending. 이번 공유 변경의 commit/push는 아직 완료하지 않음.

Notes:
- 소스 저장, 원격 반영, 집 PC 수신/실행, 운영 서버 재시작은 각각 확인한다. CLOSE는 서버 종료 명령이 아니다.
- Orca 격리 통합 PASS는 사용자 확인 USER_CONFIRMED. 정량 모델 비용/성공률/재작업/품질 비교와 우선순위 조정은 자료 없음을 유지한다.
- 주문·원자료/DB·보유·PC 설정·인증·예약 변경 없음. 중앙 Wiki/전체 세션 자동 수집은 실행하지 않는다.
