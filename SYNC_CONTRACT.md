# INVESTMENT Project Sync v2

## 기준과 책임

승인된 코드 원격은 `https://github.com/shinyj0270-afk/invest.git`, 기준 branch는 `main`이다. GitHub의 실제 commit을 코드 인계 기준으로 삼는다. `origin/main`은 fetch 이전에는 캐시다. 로컬 미전송 변경과 원격 최신본을 구분하며 AI끼리 기억을 직접 공유한다고 가정하지 않는다.

| 파일/위치 | 책임 | 갱신 기준 |
|---|---|---|
| PROJECT_STATE.md | 전체 프로젝트의 현재 상태·주요 진행 단계·검증·미해결 | 실제 상태가 달라질 때, 기존 역사 보존 |
| CURRENT_HANDOFF.md | 바로 다음 세션의 작업과 마지막 인계 증거 | 매 SESSION CLOSE, 무변경도 갱신 |
| AGENTS.md | 모든 로컬 AI의 공통 작업 규칙과 필수 문서 진입점 | 규칙 변경 시 |
| CLAUDE.md | @AGENTS.md 재사용과 Claude 전용 보충 | Claude 고유 규칙 변경 시 |
| SYNC_CONTRACT.md | PC·AI·Git·Wiki 사이 역할과 동기화 계약 | 이 계약 변경 시 |
| skills/investment-session/SKILL.md | 공통 START/CLOSE의 실행 순서·명령·중단 조건 | 절차 변경 시 |
| docs/DUAL_PC_WORKFLOW.md | PC별 설치·로컬 설정·실행·제외 대상 | 실행 환경 지침 변경 시 |
| docs/PROJECT_SYNC_V2.md | 사용법·자동 로딩의 한계·도입 조사 근거 | 사용법 변경 시 |
| LLM Wiki / personal-ai-wiki | 장기 결정·개념·배경지식, 프로젝트 원본 연결 | 장기 가치가 있는 새 지식만 |

현재 실행 순서/전송 상태는 CURRENT_HANDOFF에만 유지한다. PROJECT_STATE의 과거 다음 작업은 당시 이력이다. HANDOFF.md와 START_ON_HOME_PC.md는 과거 기록으로 보존하며 최신 지침으로 쓰지 않는다. 단기 인계를 Wiki나 도구별 메모리에 복제하지 않는다.

## PC와 쓰기 세션

- work = Primary: 회사 PC가 정상 사용 가능한 동안 주요 개발·실데이터 작업·최종 검증의 기본 환경.
- home = Secondary: 보조 개발·테스트·야간/주말·비상 인계. 상시 병렬 개발 환경으로 운영하지 않는다.
- 같은 작업 branch는 한 시점에 한 PC의 한 쓰기 세션만 수정한다. 읽기/검토는 가능하지만 기술적 잠금으로 보장되는 규칙은 아니다.
- 사용자가 확인한 PC만 config/local.json에 설정하고 unknown을 추측하지 않는다. 영구 work/home branch를 만들지 않는다.
- 집 PC 검증과 회사 PC 최종 검증을 구분한다. Git 원격 반영과 상대 PC 수신·실행은 별도 증거가 필요하다.

## SESSION START / SESSION CLOSE

두 AI 모두 기존 [investment-session 스킬](skills/investment-session/SKILL.md)을 실행한다. 새로운 병렬 시작/마감 시스템을 만들지 않는다.

START는 PC → Git status/branch/HEAD/진행 작업/remote 관계 → 안전한 경우 fetch 및 ff-only 수신 → PROJECT_STATE → CURRENT_HANDOFF → AGENTS → SYNC_CONTRACT → Claude 추가 규칙 → 다음 action 순서다. 지침은 사전 점검에도 적용하며 수신 후 변경된 문서를 다시 읽는다. 원격 URL 확인 시 인증정보는 노출하지 않는다.

미커밋 변경·진행 Git 작업·다른 쓰기 세션·divergence·예상 밖 branch·detached HEAD·upstream 부재·로컬 ahead이면 자동 수신을 보류한다. 자동 stash/reset/merge/rebase, force push, git clean, 충돌 덮어쓰기는 하지 않는다. fetch 실패는 최신 확인 실패이지 0/0이 아니다.

CLOSE는 실제 변경 검증 → 필요한 PROJECT_STATE 갱신 → CURRENT_HANDOFF 항상 갱신 → diff/공유 범위 검토 → 명시 경로 stage → commit → 원격 재확인 → 충돌 없을 때 push → 실제 remote SHA 확인 → 필요한 장기 지식 검토 → 최종 branch/commit/remote 보고다. CLOSE 요청은 검증된 공유 변경의 commit/push를 포함한다. 원격이 별도 전진하면 자동 통합하지 않고 보존·중단한다.

기존 pc-start/pc-finish 스크립트는 오프라인 점검만 한다. 실행만으로 문서 인계·commit·push가 끝나지 않는다. PowerShell 실행 정책 차단 시 프로젝트 .venv의 tools/pc_check.py를 사용하고 정책을 우회하지 않는다.

## CURRENT_HANDOFF 작성 계약

전체 이력을 누적하지 않고 한 세션의 다음 실행 지점으로 교체한다. 이전 버전은 Git 이력으로 보존한다. 필수 항목:

- Updated (KST), Last agent, Last PC, Last task.
- Completed, Pending: 이번 완료와 다음 작업에 영향을 주는 미완료만 간결하게 기록.
- Next task, Next action: 작업 PC·읽을 파일·수행 작업·산출물·완료 판정을 구체적으로 기록.
- Recommended next agent, Recommended model, Recommended reasoning, Escalation condition.
- Branch, Commit (무슨 기준 SHA인지 표시), Remote status (대상 ref·확인한 SHA/시점·push 상태).
- Notes: 이번 검증, 로컬 변경 보존, 상대 PC 미확인, 필요한 주의사항.

ChatGPT 추천은 설계·판단·리뷰에 한정한다. 모델/Reasoning은 권장값이며 실행 환경을 실제로 전환했다는 뜻이 아니다. divergence/로컬 충돌/강한 PC 경로 결합/대규모 구조 변경이 있으면 구현을 멈춰 근거를 정리하고 High 수준의 검토로 올린다.

### commit과 push 기록

자기 자신을 포함할 commit의 SHA와 미래 push 성공은 미리 알 수 없다. Commit에는 시작 기준 또는 **이미 생성된 구현 commit**의 전체 SHA를 쓰고 의미를 명시한다. Remote status는 같은 SHA를 대상으로 `not pushed`, `verification pending`, `pushed (verified)`를 구분한다. 마지막으로 확인한 push가 없으면 없다고 쓴다.

push 후 HEAD/원격 추적 ref/실제 remote ref가 일치한 구현 commit을 CURRENT_HANDOFF에 기록할 수 있다. 이 증거만 바꾸는 후속 기록 commit을 만들면 그 문서에는 검증된 구현 SHA를 유지하고, **기록 commit 자체의 전송은 최종 보고 및 다음 START의 실제 Git 조회로 검증**한다고 표시한다. 자기 SHA를 쓰기 위한 무한 commit/amend를 하지 않는다. 후속 기록도 diff 검토·원격 재확인·일반 push·실제 SHA 검증을 거친다.

commit은 됐지만 push 실패/미실행이면 `local commit 완료 / remote handoff 미완료`로 쓰고 원인과 재개 단계를 남긴다. commit도 실패했으면 `로컬 파일 저장만 완료 / commit 미완료 / remote handoff 미완료`다. 원격 기록 갱신이 불가능하면 로컬 기록과 최종 보고에 이를 밝힌다.

## ChatGPT 인계

ChatGPT가 로컬 파일을 자동으로 읽는다고 가정하지 않는다. 연결 가능하면 승인 저장소 main의 실제 commit을 먼저 확인하고 같은 commit의 PROJECT_STATE.md와 CURRENT_HANDOFF.md, 필요한 AGENTS/SYNC_CONTRACT를 읽는다. 연결이 없으면 사용자에게 인계 본문·관련 문서·branch/commit/remote 확인 결과를 전달할 수 있게 작성하고, 원격 최신성 미확인을 명시한다. 과거 대화는 최신 원본 증거가 아니다.

## Wiki 경계

`shinyj0270-afk/personal-ai-wiki/control/projects.json`은 프로젝트 원본 위치를 연결하며 개발 상태의 두 번째 최신본을 만들지 않는다. GLOBAL_WORKFLOW는 GLOBAL_WORKFLOW_REFERENCE.md의 원본을 읽고 프로젝트 예외를 우선한다.

중요한 장기 결정이 생긴 경우에만 /wiki-sync의 실제 정의와 전송 범위를 확인한다. 2026-10-06 회사 PC에서 확인한 정의는 전체 세션을 raw/sessions로 변환하고 Wiki ingest 및 pending synthesis까지 수행한다. 이는 장기 결정만 선별 보존하는 요청과 다르므로 현재 INVESTMENT에서는 실행하지 않는다. 중앙 Wiki 직접 수정·전체 세션 자동 공유 금지를 유지하며 선별 동기화 경로가 마련되기 전에는 Git의 결정 근거를 보존하고 Wiki 미반영을 보고한다. 이번 구현은 그 명령이나 중앙 Wiki를 변경하지 않는다.

## 공유 제외와 기존 예외

인증·비밀번호·토큰·PC 로컬 설정·원자료·DB/WAL/journal·로그·전체 세션·개인 보유/투자노트를 코드 원격에 넣지 않는다. .gitignore와 경로 검사만으로 내용 안전성을 보장하지 않는다. 명시한 파일만 stage하고 전송 commit의 내용을 검토한다. 기존 보유내역의 전용 비공개 자동 동기화 예외는 [HOLDINGS_SYNC.md](docs/HOLDINGS_SYNC.md)를 그대로 따르며 이번 인계와 분리한다.

실데이터 실패를 가상 성공으로 보고하지 않는다. 주문·자동매매·잔고 조회 금지, 인포맥스 우선/1억원 미만 오차 무시, 각 PC .venv와 127.0.0.1, 예약 별도 요청 원칙은 AGENTS.md를 따른다.
