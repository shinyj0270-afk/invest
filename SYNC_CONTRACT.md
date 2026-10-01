# INVESTMENT Project Sync v1

## 목적

회사 PC, 집 PC, Claude/Codex, ChatGPT가 같은 INVESTMENT 상태를 기준으로 작업하도록 한다. 대화 기억이나 오래된 Wiki 요약이 아니라 GitHub의 기준 저장소와 `PROJECT_STATE.md`를 현재 상태의 단일 기준으로 사용한다.

## 단일 기준

- 코드 기준: `shinyj0270-afk/invest`의 `main`
- 상태 기준: 같은 저장소의 `PROJECT_STATE.md`
- 작업 지침: `AGENTS.md`, `CLAUDE.md`, `docs/DUAL_PC_WORKFLOW.md`
- 장기 지식/인덱스: `shinyj0270-afk/personal-ai-wiki`
- LLM Wiki와 `/wiki-sync`는 지식 보존용이며 코드/상태의 PC 간 전송 수단으로 사용하지 않는다.

## 로컬 Claude/Codex 시작 절차

1. 기존 INVESTMENT 작업 폴더에서 `git status -sb`와 현재 branch를 확인한다.
2. 진행 중 로컬 변경이 없고 `main`이면 `git fetch origin` 후 차이를 확인하고 `git pull --ff-only`로만 수신한다.
3. divergence, 미커밋 변경, 다른 작업 세션이 있으면 자동 정리하지 말고 중단·보고한다.
4. 수신이 끝난 뒤 `AGENTS.md`, `CLAUDE.md`, `PROJECT_STATE.md`를 다시 읽고 작업을 시작한다.
5. 로컬 설정·인증·DB·원자료·보유내역은 공개 코드 Git 인계로 동기화하지 않는다. 사용자가 선택한 보유내역의 전용 비공개 자동 동기화는 docs/HOLDINGS_SYNC.md에 따라 별도로 수행한다.

## 로컬 Claude/Codex 종료 절차

1. 실제 변경과 실제 실행한 검증만 `PROJECT_STATE.md` 맨 위에 기록한다.
2. 공유 가능한 변경 파일만 명시적으로 stage한다. `git add .`, `git add -A`는 사용하지 않는다.
3. 테스트와 민감/로컬 파일 제외를 확인한 뒤 commit한다.
4. 원격을 다시 확인하고 충돌이 없을 때 일반 push한다.
5. `git rev-parse HEAD`와 `git ls-remote origin refs/heads/main`이 같은지 확인한다.
6. push가 끝나지 않았으면 “로컬 저장 완료 / 원격 인계 미완료”로 표시한다.

## ChatGPT 시작 절차

INVESTMENT의 현재 상태, 마지막 작업, 다음 단계 또는 구현 판단을 묻는 경우 GitHub 연결을 사용할 수 있으면 먼저 다음 원본을 다시 읽는다.

1. `shinyj0270-afk/invest/main:PROJECT_STATE.md`
2. 필요하면 `AGENTS.md`와 관련 문서
3. 최근 `main` commit

과거 대화 기억만으로 “최신 상태”를 단정하지 않는다. GitHub를 읽지 못한 세션에서는 확인하지 못했다고 명시한다.

## Personal AI Wiki 역할

`shinyj0270-afk/personal-ai-wiki/control/projects.json`은 프로젝트 원본의 위치를 연결한다. 개발 상태를 복제해 두 번째 최신본을 만들지 않는다. Wiki에는 장기 결정·근거·재사용 지식을 보존하고, 현재 개발 상태는 항상 INVESTMENT 저장소에서 다시 읽는다.

## 동시 작업 규칙

- 한 시점에 한 PC·한 쓰기 세션을 기본으로 한다.
- 다른 에이전트는 같은 branch에 동시에 쓰지 않고 읽기·검토를 맡는다.
- 병렬 구현이 필요하면 명시적으로 별도 branch/worktree를 만든다.
- 자동 stash, force push, reset --hard, git clean, 충돌 자동 덮어쓰기를 하지 않는다.

## 사용자에게 보이는 기준

앞으로 “INVESTMENT 최신 상태 확인”은 위 원본을 실제로 조회한 뒤 답한다. 회사 PC와 집 PC는 로컬 환경만 다르고, 공유 코드와 PROJECT_STATE는 같은 `origin/main`을 기준으로 맞춘다.
