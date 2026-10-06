# INVESTMENT 공통 작업 지침

- 사용자가 `INVESTMENT START`/`INVESTMENT 시작` 또는 `INVESTMENT CLOSE`/`INVESTMENT 마감`이라고 하면 [skills/investment-session/SKILL.md](skills/investment-session/SKILL.md)의 해당 모드를 실행한다.
- 모든 PC·Claude/Codex·ChatGPT 간 상태 일치는 [SYNC_CONTRACT.md](SYNC_CONTRACT.md)를 따른다. 원격에서 확인한 `main`의 `PROJECT_STATE.md`는 전체 개발 상태, [CURRENT_HANDOFF.md](CURRENT_HANDOFF.md)는 바로 다음 세션의 작업 기준이다. 과거 대화/Wiki 요약만으로 최신 상태를 단정하지 않는다.

<!-- BEGIN DUAL-PC -->
- work는 Primary로 주요 개발·실데이터 작업·최종 검증의 기본 환경이다. home은 Secondary로 보조 개발·테스트·야간/주말·비상 인계를 맡는다. 사용자가 명시한 프로필만 config/local.json에 설정한다. 미확인 PC는 unknown으로 두고 PC별 작업본과 실행 환경은 독립적으로 보존한다.
- 모든 로컬 AI는 작업 시작 시 Git/PC 상태를 점검하고 PROJECT_STATE.md, CURRENT_HANDOFF.md, 이 파일, SYNC_CONTRACT.md, docs/DUAL_PC_WORKFLOW.md를 실제로 읽는다. Claude는 CLAUDE.md의 추가 규칙도 읽는다. 수신 후 다시 읽으며 세부 흐름은 기존 investment-session 스킬을 따른다. 기존 작업본/미완료 변경을 보존한다. 상위 저장소가 있으면 중첩 저장소를 만들지 않는다.
- SESSION CLOSE마다 CURRENT_HANDOFF.md를 항상 갱신한다. PROJECT_STATE.md는 전체 상태·주요 단계·검증·미해결이 실제로 달라질 때만 갱신하고 다음 실행 지점은 CURRENT_HANDOFF.md를 참조한다. 과거 테스트를 재실행 결과로 복사하지 않는다.
- 한 기준 저장소와 PC별 작업본을 사용한다. 영구 work/home 브랜치를 나누지 않고 기존 인계 브랜치/PR 규칙을 따른다. 한 시점에 한 PC·한 쓰기 세션 원칙은 운영 관례이며 기술적 잠금이 아니다.
- PC 로컬 설정, 인증, 원자료, DB와 WAL/journal, 보유내역, 투자노트, 출력물, 로그, 전체 세션을 자동 공유하지 않는다.
- 예외: 사용자가 2026-10-01 회사·집 보유내역의 GitHub 비공개 자동 동기화를 명시적으로 선택했다. 직접 반영한 보유·현금·관련 연구/가격·구성 설정만 전용 비공개 저장소로 동기화한다. 공개 코드 저장소와 공유 후보에 개인 입력을 넣지 않는다. 전송 전에 비공개 여부·쓰기 권한을 검사하고 충돌 시 보존한다. 인증키·DB·원자료·PC 설정은 이 예외에 포함되지 않는다. 기본 입력/실행은 직접 입력과 scripts/open-investment.cmd이며 사용법은 docs/HOLDINGS_SYNC.md를 따른다. .gitignore는 이미 추적된 파일/과거 커밋의 보안 검증을 대신하지 않는다.
- 사용자는 이 프로젝트의 일반 상장기업 데이터와 개인 관심 기록에 회사 감사·반출 승인 대상인 민감자료가 없다고 확인했다. 이를 회사 보안 승인 대기 사유로 삼지 않는다. 비밀번호·토큰, PC 로컬 설정·DB는 별도로 보관한다.
- 기본 시작/마감 스크립트는 오프라인 점검 전용이다. Git 수신·전송은 SYNC_CONTRACT.md와 기존 세션 스킬에 따라 별도로 실행한다.
- 수신은 clean 상태와 진행 중 작업 유무를 먼저 점검한 후 fetch, 차이 확인, pull --ff-only 순서다. divergence는 중단한다. 자동 stash, force push, reset --hard, git clean, 충돌 덮어쓰기를 하지 않는다.
- 전송 시 테스트→인증정보/로컬 파일 제외 확인→명시한 파일만 stage→commit→원격 재확인→충돌 없을 때 push→원격 커밋 확인. git add . / -A 금지. 원격 전송과 상대 PC 수신·실행은 별도로 보고한다.
- 공통 코드는 설정/상대 경로를 사용한다. 각 PC의 .venv를 사용하고 전역 환경은 수정하지 않는다. 로컬 서버는 127.0.0.1에 바인딩한다. 예약 등록/자동 시작은 별도 요청 없이는 실행하지 않는다.
- 가상 테스트 모드는 명시적으로 구분한다. 실데이터 조회 실패를 가상 성공으로 바꾸지 않는다. API 권한 미확인은 연결 대기다. 주문·자동매매·잔고 조회 금지.
- 인포맥스와 공식 재무 차이는 기존 사용자 결정(인포맥스 우선, 1억 미만 오차 무시)을 유지하며 출처·불확실성을 보존한다.
- 중앙 Wiki 직접 수정과 전체 세션 자동 수집 금지는 유지한다. 중요한 장기 결정이 생긴 경우에만 SYNC_CONTRACT.md의 Wiki 경계와 실제 /wiki-sync 정의를 확인한다. Git 인계와 별개이며 Wiki 없이 개발할 수 있다.
<!-- END DUAL-PC -->

## GLOBAL WORKFLOW 상속

[공통 파일 참조](GLOBAL_WORKFLOW_REFERENCE.md)에 지정된 GLOBAL_WORKFLOW.md를 읽고 공통 START/CLOSE 골격을 상속한다. 충돌 시 기존 INVESTMENT 규칙이 우선한다. 독립 investment-session 스킬, SYNC_CONTRACT, 상태 원본과 Git/데이터/인증/PC별 예외를 유지한다.


## 기존 AI 통합 구조 · 로컬 실행 레이어

- ChatGPT는 최상위 오케스트레이션·판단·계획·조율, Codex는 구현·코딩·테스트, Claude는 검토·문서화·보조 분석을 담당한다. 사용자의 현재 명시 지시가 우선한다.
- Remote Desktop Commander는 회사 PC의 파일·PowerShell·Git·기존 프로젝트에 접근하는 I/O 및 로컬 실행 통로다. 독립 에이전트·판단 주체·별도 통합축이나 작업 상태 저장소로 취급하지 않는다.
- GitHub와 LLM Wiki는 공용 상태·기억·인계 레이어다. 현재 개발 상태는 해당 프로젝트의 기존 상태/인계 문서, 장기 지식은 Wiki를 참조한다. 회사 PC와 집 PC는 각각 실행 환경이며 브리지 연결만으로 PC간 동기화가 완료되지 않는다.
- 공통 규칙 원본은 shinyj0270-afk/personal-ai-wiki의 main:GLOBAL_WORKFLOW.md, 프로젝트 연결 원본은 main:control/projects.json이다. 로컬 사본의 HEAD·미전송 변경·원격 최신성을 확인하고 오래된 로컬 사본을 최신 규칙으로 간주하지 않는다. 접근 불가 시 미확인을 보고하고 기존 프로젝트 규칙으로 가능한 작업을 계속한다.
- LLM Wiki 프로그램 저장소의 origin(Pratiyush/llm-wiki)은 개인 지식 인계 대상이 아니다. 기존 personal-ai-wiki와 선별 Wiki 보존 절차를 유지하고, 전체 세션 자동 수집·자동 /wiki-sync·임의 push를 실행하지 않는다.
- 기존 START/CLOSE·한 쓰기 세션·미완료 변경 보존 규칙을 유지한다. 브리지 시작/종료와 프로젝트 START/CLOSE는 별개다. 각 AI의 자동 호출·메시지 교환은 브리지 기능이 아니며, 실행 담당자는 요청 범위와 실제 검증 결과를 기존 인계 문서로 전달한다.
