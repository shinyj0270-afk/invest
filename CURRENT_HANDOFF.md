# CURRENT HANDOFF

Updated: 2026-10-06 KST
Last agent: Codex
Last PC: work (Primary)
Last task: 회사 PC Portability Phase 1A–1C 완료

Completed:
- 감사 A01–A08의 회사 PC 조치 완료: 실행기 위임/작업본 식별, UI4개 브라우저 선택, Playwright 기준 통일, 마감 검증 격리.
- .local/DB/sidecar/로그 공유 차단, legacy ZIP 범위 표시, Windows/로컬 자산 및 과거 문서 안내 정리.
- 실행기/브라우저/격리/PowerShell 회귀13개와 기존 두 PC 안전13개 통과.
- 실제 pc-finish -RunTests의 공유257개 검사, 격리 portable15명령·실자료 없는 화면·합성 UI4개 최종 통과.

Pending:
- 실제 home PC 최신 코드 수신·실행 검증은 해당 PC에서 필요.
- 별도 Claude 세션의 공통 지침/인계 읽기 확인은 미실행.
- 중앙 Wiki 선별 보존 경로는 기존 범위 밖이며 /wiki-sync는 전체 세션 수집이므로 미실행.

Next task: 필요 시 home Secondary에서 최신 코드 수신 및 실제 실행 확인
Recommended next agent: Codex (또는 Claude)
Recommended model: GPT-6 Astra (Codex 선택 시)
Recommended reasoning: Medium

Next action:
- 실제 집 PC에서 사용자 확인 후 home 프로필을 확인하고 기존 작업본에서 INVESTMENT START를 실행한다. 회사 PC 설정을 home으로 바꾸지 않는다.
- 로컬 변경/진행 작업/다른 쓰기 세션을 먼저 확인하고 승인 원격에서 안전하게 최신 main을 수신한다. CURRENT_HANDOFF, PROJECT_STATE, 공통 규칙과 docs/PC_MIGRATION.md를 읽는다.
- 해당 PC의 .venv/Node/브라우저를 확인한 뒤 scripts/pc-finish.ps1 -RunTests로 격리 검증한다. 정책 차단 시 문서의 Python 대체 경로를 사용한다.
- 기본 실행기로 앱을 열어 현재 작업본/포트/화면/자료 상태를 확인한다. 보유 pending/충돌은 기존 HOLDINGS_SYNC 절차로 보존하며 캐시/DB를 덮어쓰지 않는다.
- 실제 받은 SHA와 home 실행 결과를 구분해 인계한다. 별도 Claude 사용 시 @AGENTS.md와 CURRENT_HANDOFF 로딩을 확인한다.

Escalation condition:
- Git divergence/로컬 충돌/동시 쓰기 발견 시 보존 후 자동 수신 중단.
- 데이터 이전·인증 복제·광범위 구조 변경이 필요하면 범위를 분리하고 High 검토.

Branch: main
Commit: 9663dc82cdc75bcdd48f88683b498a3a64c2aeac (이번 작업 시작 기준)
Remote status:
- verification pending: 이번 Phase 1 변경의 commit/push 확인 전.

Notes:
- 회사 PC의 이식성 후속 구현은 완료. 실제 home/별도 Claude/Wiki 반영을 완료했다고 주장하지 않는다.
- 분석·Infomax·포트폴리오 로직/실데이터/보유/인증/PC 설정/운영 서버/예약 변경 없음.
- 패키지는 설치하지 않았다. PyYAML 기반 외부 스킬 형식 검사기는 미실행이며 스킬은 직접 검토했다.
- 기존 재무 미확보·가격 기준·성과 누적은 별도 데이터 작업 범위이며 이번 이식성 작업에서 해결한 것이 아니다.
