# CURRENT HANDOFF

Updated: 2026-10-15T16:45:00+09:00
Handoff version: 2026-10-15-close-company-primary-official-first
Last agent: Claude (Haiku 5.5)
Last PC: company Primary (사용자 확인; 원본 config profile=work)
Last task: INVESTMENT CLOSE — 재무 공식 원문 우선 전환 이후 마감

Completed:
- 시작 2f750da... (원본 main=원격 main=작업 브랜치 일치, clean). 이번 세션은 코드 변경 없이 마감 점검만 수행했다.
- 마감 점검: tools/pc_check.py --phase finish 결과 clean, profile=work, 추적 중인 private 경로 0, 진행 중 Git 작업 0, scheduled_jobs_enabled=false. 작업 브랜치와 원본 main 모두 원격 main과 0/0 일치.
- 원격 확인: git ls-remote refs/heads/main = 2f750da1afc53b70ad28bb911dedee3031720e9b.
- 운영 서버 /health: restart_required=false, build_id=source_build_id=41fedfbc… (현재 파일과 일치).
- 이번 세션 직전까지 완료된 구현: 재무 공식 원문(DART) 우선 c88ee4d, 신규 상장 5개월 편입 규칙 8969df6, 보유 시장자료 일봉 보강 f7fe36f/74d98f0, 제외 목록·화면 1584139. 각 구현은 격리 검증 통과 후 원본 main 반영·안전 재시작·실제 화면 확인을 거쳤다.

Pending:
- 사용자 기존 탭은 새로고침해야 최신 코드(재무 공식 원문 우선, 제외 목록, 편입 규칙)를 받는다. 실제 갱신 여부는 미확인.
- 인포맥스 검토 스냅샷(2026-09-23) 자체 갱신은 미해결. 보유 화면의 "인포맥스 검토" 날짜는 그대로이며, ② Excel COM 자동화(이용 범위 확인 선행) 또는 ③ DATAFEED(계약 확인) 중 선택이 필요하다.
- 실제 보유 종목 화면은 동기화 차단 검증 브라우저에서 확인하지 못했다. 사용자 탭에서 보유 가격일(시장자료 2026-10-14)과 인포맥스 검토 2026-09-23 표시를 직접 확인해야 한다.
- 편입 대기 기업: 마키나락스(2026-10-20), 케이피항공산업(10-19) 등은 편입일 이후 발굴 후보가 된다. 편입일 이후 목록에서 추세·재무 자동 수집이 정상 동작하는지 확인이 필요하다.
- 멜콘(179880)·브릴스(468670)·기존 6개사는 사용자 제외 목록에 있다. 미확보 재무 목록은 제외 반영 후 다시 확인해야 한다(이전 172건은 제외 전 기준).
- test_dashboard_delivery.test_restart_requires_auth_saved_drafts_and_idle_collectors가 전체 검증 중 간헐적으로 소켓 연결 중단(WinError 10053)으로 실패한다. 변경 전 코드와 단독 실행에서는 재현되지 않았다. 원인 분석 후속 과제.
- 집 PC 수신·실행, 실제 휴대폰 접속, home Telegram, 연구설계 실증은 미확인.

Next task: 사용자 새 요청 우선. 없으면 (1) 사용자 탭 새로고침 후 보유 화면 날짜 표시 확인, (2) 인포맥스 검토 스냅샷 갱신 방식(②/③) 결정.

Next action:
1. INVESTMENT START에서 Git/PC/원격 main을 확인하고 PROJECT_STATE.md, 이 문서, AGENTS.md, SYNC_CONTRACT.md, docs/DUAL_PC_WORKFLOW.md를 읽는다.
2. 원본 회사 work를 실행 환경으로 유지하고 분리 워크트리(invest-rev)를 보존한다. 분리 워크트리에는 config/local.json과 .venv가 없는 것이 의도된 상태다.
3. 인포맥스 자동화 요청이 나오면 INFOMAX_CONNECTIVITY.md와 이용 범위 확인부터 계획한다. 실제 인포맥스 주문·잔고 조회는 금지.

Recommended next agent: Codex (구현·검증); 설계 판단이 필요하면 ChatGPT
Recommended model: 기존 사용자 설정 유지
Recommended reasoning: 기존 설정 유지; 반복 실패·식별 충돌·큰 구조 변경이면 high 검토
Escalation condition: 원본/원격 divergence·예상 밖 로컬 변경·수집 잠금·자료 식별 충돌이면 보존하고 해당 작업 보류
Branch: shinyj0270-afk/invest-rev (분리 개발, upstream 없음); 원본 main (통합 완료)
Commit: c88ee4d6b65085ecd25934e6c5b8f83a40e67797 (재무 공식 원문 우선 구현 기준; 이후 2f750da 인계 기록 포함)
Remote status: refs/heads/main 2f750da1afc53b70ad28bb911dedee3031720e9b pushed (verified, 2026-10-15 16:44 ls-remote 확인). 이 마감 기록 commit 자체의 전송은 최종 보고/다음 START의 실제 Git 조회로 확인한다. 집 PC 수신/실행 미확인.
Notes:
- 검증 증거는 공유 제외 validation/current/ (recheck/live-receipt.json, live-status.json, polish-validate.log, official-first-validate2.log 등)에 보존.
- 인증·PC 설정·보유/현금·DB·원자료·시세·로그는 코드 원격에 넣지 않았다. 입력 쓰기·보유 동기화는 검증 브라우저에서 차단. Wiki/예약/외부 AI 호출 없음.
- 서버·워크트리·개인 로컬 자료를 보존했다. 워크트리 삭제·운영 서버 종료는 마감에 포함하지 않았다.
