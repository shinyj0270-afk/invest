# INVESTMENT Session Skill

## 목적

회사 PC, 집 PC, Claude, Codex에서 같은 절차로 INVESTMENT 작업을 시작하고 마감한다.
이 스킬은 `SYNC_CONTRACT.md`와 `PROJECT_STATE.md`를 기준으로 동작한다.

## 호출어

다음 표현을 같은 명령으로 취급한다.

- `INVESTMENT START`
- `INVESTMENT 시작`
- `INVESTMENT CLOSE`
- `INVESTMENT 마감`

사용자가 위 표현을 쓰면 별도 설명을 반복하지 말고 해당 모드를 바로 실행한다.

---

## START 모드

### 1. 로컬 안전 점검

저장소 루트에서 먼저 기존 점검을 실행한다.

```powershell
.\scripts\pc-start.ps1
```

PowerShell 실행 정책이 스크립트를 차단하면 정책을 우회하지 말고 다음 대체 경로를 사용한다.

```powershell
.\.venv\Scripts\python.exe tools\pc_check.py --phase start
```

다음 중 하나라도 있으면 자동 수신을 중단하고 상태만 보고한다.

- 미커밋 변경
- merge/rebase/cherry-pick/revert 진행 중
- detached HEAD
- `main` 이외의 작업 branch인데 사용자가 해당 branch 작업을 요청하지 않음
- upstream 없음
- 로컬과 원격의 divergence
- 로컬 ahead 상태

자동 stash, `reset --hard`, `git clean`, force 작업으로 해결하지 않는다.

### 2. 원격 최신 확인

안전 점검이 통과한 clean `main`에서만 실행한다.

```powershell
git fetch origin main
git rev-list --left-right --count HEAD...origin/main
```

- `0 0`: 수신 불필요.
- `0 N`: `git pull --ff-only origin main`으로만 수신.
- `N 0`: 로컬 ahead이므로 자동 push/pull하지 말고 중단·보고.
- `N M`: divergence이므로 중단·보고.

수신 후 다음을 확인한다.

```powershell
git status -sb
git rev-parse HEAD
git rev-parse origin/main
```

### 3. 기준 문서 읽기

수신이 끝난 뒤 반드시 다음 순서로 읽는다.

1. `AGENTS.md`
2. `SYNC_CONTRACT.md`
3. `CLAUDE.md`
4. `PROJECT_STATE.md`
5. 현재 작업에 필요한 관련 문서

과거 대화나 오래된 Wiki 요약을 최신 상태보다 우선하지 않는다.

### 4. START 완료 보고

사용자에게 짧게 다음만 보고한다.

- profile: work/home
- branch
- HEAD short SHA
- origin/main short SHA
- clean 여부
- `PROJECT_STATE.md`의 최신 완료 작업
- 미해결 1~3개
- 이어서 할 다음 작업 1개

사용자가 이미 구체적인 오늘 작업을 지정했다면 그 작업을 다음 작업으로 사용한다.

---

## CLOSE 모드

### 1. 변경 상태 확인

먼저 실행한다.

```powershell
.\scripts\pc-finish.ps1
git status --short --branch
git diff --check
```

스크립트 실행이 정책에 막히면 `tools\pc_check.py --phase finish`를 사용한다.

진행 중 Git 작업, 예상하지 못한 private/local 파일, 충돌이 있으면 자동으로 정리하지 않고 중단·보고한다.

### 2. 검증

이번 세션에서 변경한 범위에 맞는 실제 테스트만 실행한다.

- 문서/지침만 변경: 최소 `git diff --check` + 관련 파일 내용 검토
- 코드/공유 동작 변경: 관련 단위 테스트 + 필요하면 `tools/verify_portable.py`
- 전체 검증이 필요한 변경: 기존 프로젝트 지침에 따라 `tools/verify_all.py`

과거 세션의 테스트 결과를 이번 실행 결과처럼 복사하지 않는다.
실행하지 않은 검증은 미실행이라고 기록한다.

### 3. PROJECT_STATE 갱신

`PROJECT_STATE.md` 맨 위에 이번 세션의 새 블록을 추가한다.

반드시 포함할 내용:

- 날짜와 작업명
- 시작 branch/기준 SHA
- 실제 변경
- 실제 실행한 검증과 결과
- 미해결 사항
- 다음 작업
- commit/push 여부

기존 과거 기록을 삭제하거나 덮어쓰지 않는다.

### 4. 공유 범위 점검

`config/share_candidates.json`과 `.gitignore`를 확인한다.
다음은 stage/push하지 않는다.

- `config/local.json`
- `config/runtime.local.json`
- `.env*`
- `private_data/`
- `data/`
- SQLite/DB/WAL/journal
- 인증정보/토큰/비밀번호
- 개인 보유내역/투자노트
- 로그/전체 세션
- `.venv/`, `node_modules/`

`git add .`, `git add -A`를 사용하지 않는다.
공유할 파일 경로를 명시적으로 stage한다.

### 5. commit/push

사용자가 작업 마감을 요청한 CLOSE 모드에서는 공유 가능한 변경과 검증이 정상일 때 commit/push까지 진행한다.

순서:

```powershell
git status --short
git diff --cached --check
git commit -m "<이번 작업을 설명하는 짧은 메시지>"
git fetch origin main
git rev-list --left-right --count HEAD...origin/main
```

commit 후 원격이 별도로 전진했거나 divergence가 생기면 push하지 않고 중단·보고한다.
정상일 때만:

```powershell
git push origin main
git rev-parse HEAD
git rev-parse origin/main
git ls-remote origin refs/heads/main
```

HEAD, origin/main, 실제 원격 main SHA가 일치해야 원격 인계 완료로 보고한다.

### 6. CLOSE 완료 보고

다음 형식으로 짧게 보고한다.

- 완료: 실제 변경 요약
- 검증: 이번에 실행한 검사
- commit: short SHA + message
- sync: HEAD = origin/main = remote main 여부
- 다음 시작점: 한 문장

push가 완료되지 않았으면 반드시
`로컬 저장 완료 / 원격 인계 미완료`
라고 명시한다.

---

## 공통 안전 원칙

- 한 시점에 한 PC·한 쓰기 세션을 기본으로 한다.
- 회사 PC와 집 PC의 로컬 설정/DB/원자료는 서로 복사하지 않는다.
- `PROJECT_STATE.md`는 현재 개발 상태의 단일 기준이다.
- LLM Wiki와 `/wiki-sync`는 장기 지식 보존용이며 Git 수신/전송을 대신하지 않는다.
- 자동 stash, force push, `reset --hard`, `git clean`, 충돌 자동 덮어쓰기를 하지 않는다.
- 실데이터 실패를 fixture 성공으로 대체해 보고하지 않는다.
- 주문·자동매매·잔고 조회는 별도 명시 요청 없이 실행하지 않는다.
