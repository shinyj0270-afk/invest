# INVESTMENT 공통 작업 지침

- 사용자가 `INVESTMENT START`/`INVESTMENT 시작` 또는 `INVESTMENT CLOSE`/`INVESTMENT 마감`이라고 하면 [skills/investment-session/SKILL.md](skills/investment-session/SKILL.md)의 해당 모드를 실행한다.
- 모든 PC·Claude/Codex·ChatGPT 간 상태 일치는 [SYNC_CONTRACT.md](SYNC_CONTRACT.md)를 따른다. 현재 개발 상태의 단일 기준은 `origin/main`의 `PROJECT_STATE.md`이며, 과거 대화/Wiki 요약만으로 최신 상태를 단정하지 않는다.

<!-- BEGIN DUAL-PC -->
- work와 home은 대등한 독립 실행 PC다. 사용자가 명시한 프로필만 config/local.json에 설정한다. 미확인 PC는 unknown으로 둔다.
- 시작 시 이 파일, PROJECT_STATE.md, docs/DUAL_PC_WORKFLOW.md와 Git 상태를 읽는다. 기존 작업본/미완료 변경을 보존한다. 상위 저장소가 있으면 중첩 저장소를 만들지 않는다.
- 종료 시 변경사항, 이번에 실제 실행한 테스트, 미해결 사항, 다음 실행 지점을 PROJECT_STATE.md에 기록한다. 과거 테스트를 재실행 결과로 복사하지 않는다.
- 한 기준 저장소와 PC별 작업본을 사용한다. 영구 work/home 브랜치를 나누지 않고 기존 인계 브랜치/PR 규칙을 따른다. 한 시점에 한 PC·한 쓰기 세션 원칙은 운영 관례이며 기술적 잠금이 아니다.
- PC 로컬 설정, 인증, 원자료, DB와 WAL/journal, 보유내역, 투자노트, 출력물, 로그, 전체 세션을 자동 공유하지 않는다. .gitignore는 이미 추적된 파일/과거 커밋의 보안 검증을 대신하지 않는다.
- 사용자는 이 프로젝트의 일반 상장기업 데이터와 개인 관심 기록에 회사 감사·반출 승인 대상인 민감자료가 없다고 확인했다. 이를 회사 보안 승인 대기 사유로 삼지 않는다. 비밀번호·토큰, PC 로컬 설정·DB는 별도로 보관한다.
- 기본 시작/마감 스크립트는 오프라인 점검 전용이다. 초기 적용에서는 외부 업로드를 하지 않았다. 확인된 원격과 실제 인계 대상이 정해지면 작업을 이어간다.
- 수신은 clean 상태와 진행 중 작업 유무를 먼저 점검한 후 fetch, 차이 확인, pull --ff-only 순서다. divergence는 중단한다. 자동 stash, force push, reset --hard, git clean, 충돌 덮어쓰기를 하지 않는다.
- 전송 시 테스트→인증정보/로컬 파일 제외 확인→명시한 파일만 stage→commit→원격 재확인→충돌 없을 때 push→원격 커밋 확인. git add . / -A 금지. 원격 전송과 상대 PC 수신·실행은 별도로 보고한다.
- 공통 코드는 설정/상대 경로를 사용한다. 각 PC의 .venv를 사용하고 전역 환경은 수정하지 않는다. 로컬 서버는 127.0.0.1에 바인딩한다. 예약 등록/자동 시작은 별도 요청 없이는 실행하지 않는다.
- 가상 테스트 모드는 명시적으로 구분한다. 실데이터 조회 실패를 가상 성공으로 바꾸지 않는다. API 권한 미확인은 연결 대기다. 주문·자동매매·잔고 조회 금지.
- 인포맥스와 공식 재무 차이는 기존 사용자 결정(인포맥스 우선, 1억 미만 오차 무시)을 유지하며 출처·불확실성을 보존한다.
- C:\AI\llm-wiki를 수정하거나 /wiki-sync를 실행하지 않는다. Wiki와 Git 인계는 별개이며 Wiki 없이 개발할 수 있다.
<!-- END DUAL-PC -->
