# Project Sync v2 사용법과 도입 조사

## 사용법

회사 PC(work, Primary)의 기존 INVESTMENT 작업본에서 Codex 또는 Claude에 `INVESTMENT START`를 요청한다. 안전한 수신 후 공통 문서와 CURRENT_HANDOFF의 Next action을 읽고 작업한다. 마칠 때 `INVESTMENT CLOSE`를 요청하면 실제 검증, 상태/단기 인계 갱신, 검토한 파일의 commit/push 및 원격 확인을 수행한다. `pc-start.ps1`/`pc-finish.ps1`만 실행하면 오프라인 점검만 끝난다.

집 PC(home, Secondary)는 회사 PC 사용이 어렵거나 야간/주말·비상 인계가 필요할 때 같은 호출을 사용한다. 먼저 이전 쓰기 세션 종료와 원격 반영을 확인한다. 회사 PC로 돌아오면 START로 수신한 뒤 필요한 최종 검증을 별도로 수행한다. 설정·인증·DB는 PC별로 유지한다.

절차의 단일 원본은 [기존 세션 스킬](../skills/investment-session/SKILL.md), 문서 책임·필수 인계 항목·전송 증거의 의미는 [SYNC_CONTRACT.md](../SYNC_CONTRACT.md)다. 별도 API/상주 프로세스/예약/잠금은 추가하지 않았다.

## AI별 진입점과 확인 범위

- Codex: 프로젝트 AGENTS.md가 공통 진입점이다. 공식 동작은 시작 시 전역 및 저장소→현재 폴더의 지침을 모으는 방식이다. 일반 Markdown 링크의 모든 대상이 자동으로 포함되는 것은 아니므로 AGENTS가 요구한 PROJECT_STATE/CURRENT_HANDOFF/SYNC_CONTRACT를 실제로 읽는다. 이 세션에는 프로젝트 AGENTS가 주입됐고 공통 파일은 도구로 별도 읽었다. [OpenAI 지침 문서](https://learn.chatgpt.com/docs/agent-configuration/agents-md).
- Claude Code: 이 저장소의 CLAUDE.md는 `@AGENTS.md`를 import한다. 공통 내용을 복사하지 않고 이 경로를 유지한다. 상태·인계 파일은 Claude 전용 보충 지시에 따라 실제로 읽는다. 필요하면 `/context`에서 로딩을 확인한다. 공식 문서는 이 import 방식의 재사용을 지원한다. 이번 작업에서 새 Claude 세션을 실행해 확인한 것은 아니다. [Claude 메모리 문서](https://code.claude.com/docs/en/memory).
- ChatGPT: 로컬 자동 읽기를 가정하지 않는다. 설계·판단·리뷰를 맡길 때 CURRENT_HANDOFF 전체와 관련 문서, 확인한 branch/commit/remote를 전달한다. 연결이 있으면 같은 원격 commit에서 다시 읽고, 없으면 원격 최신성 미확인으로 답한다.
- 권장 모델/Reasoning은 다음 세션을 위한 제안이다. 실제 선택 가능 여부와 실행 설정은 각 도구에서 확인하며 이번 문서 작업이 모델 설정을 바꾸지는 않는다.

## 2026-10-06 변경 전 조사

파일 수정 전 기존 문서, 스크립트, Git 상태를 조사했다. 시작 work/main은 clean, HEAD `e58d677efca9e235e6ee41a6232b945f356df847`이었다. 원격 fetch에서 0 ahead/2 behind를 확인했고, 5파일 차이(집 PC 출처 호환 수정·검증 기록)를 검토한 뒤 ff-only로 `699a13a56be5456d8e190e90dfb44a15a532e532`를 수신했다. 미커밋 작업·진행 Git 작업·추적 비공개 경로는 없었다. config/local.json의 profile은 이미 work여서 변경하지 않았다.

| 조사 대상 | 실제 확인과 조치 |
|---|---|
| PROJECT_STATE | 날짜별 긴 역순 기록. 완료/테스트/다음 작업이 혼재. 과거 내용은 그대로 두고 새 상태 요약과 단기 인계 참조를 앞에 추가 |
| AGENTS | 공통 규칙, DUAL-PC 블록, GLOBAL WORKFLOW 참조. 대등 PC 규칙을 사용자 최신 요청의 Primary/Secondary로 변경 |
| SYNC_CONTRACT | v1에 시작/마감·Wiki 역할이 있었으나 단기 인계 계층 없음. v2의 문서 책임·기록 계약으로 갱신 |
| CLAUDE | @AGENTS.md와 PROJECT_STATE 항상 갱신 문장. import 유지, Claude 보충과 새 갱신 기준 적용 |
| 시작/마감 | skills/investment-session/SKILL.md와 pc-start/pc-finish.ps1, tools/pc_check.py 존재. 기존 스킬에 통합, 오프라인 스크립트는 유지 |
| 자동 로딩 | 프로젝트 .claude/.codex 전용 지침 없음. 확인한 사용자 Codex AGENTS는 빈 파일, 프로젝트 override 없음. 일반 상태 파일 자동 주입은 가정하지 않음 |
| 중복 기록 | HANDOFF/START_ON_HOME_PC/DUAL_PC_WORKFLOW의 오래된 최신 상태·ZIP 안내. 삭제 없이 역사 표시와 현행 원본 링크 추가 |
| 오래된 PC 지침 | AGENTS/DUAL_PC_WORKFLOW의 work/home 대등, 기본 다음 집 PC 작업이라는 과거 기록. 운영 규칙은 work Primary, 과거 사실은 보존 |
| GLOBAL WORKFLOW | 연결된 personal-ai-wiki/main의 v1.0 실제 조회, 파일 blob 92727a09615c4b92ac965e2f48a63e14855c23f2. 프로젝트 예외 우선·상태/Wiki 분리 유지. 중앙 원본 수정 없음 |
| /wiki-sync | 회사 PC의 C:\AI\llm-wiki\.claude\commands\wiki-sync.md와 AGENTS/CLAUDE 지침을 읽음. python3 -m llmwiki sync → raw/sessions → ingest → pending synthesis를 수행하는 전체 세션 처리 명령 |

## 충돌 해소와 남는 경계

1. **두 PC 대등 vs 회사 Primary:** 2026-10-06 사용자 결정을 우선해 현행 운영 문서를 수정했다. PC별 독립 실행/로컬 데이터 분리는 유지한다.
2. **매번 PROJECT_STATE 추가 vs 역할 분리:** 큰 상태 변화만 PROJECT_STATE에, 매 CLOSE의 실행 인계는 CURRENT_HANDOFF에 기록한다. 예전 블록은 삭제하지 않는다.
3. **마감 별도 승인 vs CLOSE 전송:** 기존 스킬처럼 사용자의 CLOSE 요청에 검증된 공유 변경 전송을 포함한다. 오프라인 스크립트에는 전송 권한/기능을 추가하지 않는다.
4. **Wiki 경로·정의 미확인 vs 실제 존재:** 오래된 부재 기록을 당시 이력으로 표시했다. 확인한 명령은 장기 지식만 선별하는 명령이 아니므로 실행하지 않는다. 이 프로젝트의 중앙 Wiki 직접 수정·전체 세션 공유 금지와 양립하는 선별 경로는 미구현이다.
5. **Git 저장 문서의 자기 SHA/push 선기록:** 이미 존재하는 구현 commit의 검증 결과를 기록하고, 후속 기록 commit의 실제 전송은 Git 조회와 최종 보고로 검증한다. 상세는 SYNC_CONTRACT를 따른다.

완료 판정은 CURRENT_HANDOFF 생성, 문서 책임/PC 우선순위/양쪽 AI의 공통 흐름/기존 스킬 통합, 기존 테스트, diff 및 공유 내용 검토, 구체적인 다음 action으로 한다. 실제 실행 결과는 PROJECT_STATE의 이번 블록에 기록한다. 회사에서 실행한 격리 home 테스트를 실제 집 PC 검증으로 바꾸어 보고하지 않는다.
