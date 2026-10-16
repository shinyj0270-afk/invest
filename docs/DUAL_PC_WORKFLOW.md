# 두 PC 운영

현재 기준 작업본은 이 문서의 상위 프로젝트다. work는 Primary(기본 개발·실데이터·최종 검증), home은 Secondary(보조·야간/주말·비상 인계)이며 각자 로컬로 실행한다. 기존 대시보드를 새 사본으로 교체하지 않는다. 역할·동기화 계약은 [SYNC_CONTRACT.md](../SYNC_CONTRACT.md), 다음 작업은 [CURRENT_HANDOFF.md](../CURRENT_HANDOFF.md)를 따른다.

## 과거 도입 기록 (현재 상태가 아님)

아래는 도입 당시 기록을 보존한 것이다. 최신 프로젝트 상태는 PROJECT_STATE.md를 읽는다. 특히 아래 Wiki 경로 부재/명령 미확인은 과거 관측이며 2026-10-06 실제 조사 결과는 [Project Sync v2](PROJECT_SYNC_V2.md)에 있다.

- 회사 PC 작업본: work, 기존 폴더에 Git `main`을 연결했다. 원격은 사용자가 확인한 `https://github.com/shinyj0270-afk/invest.git`이다.
- 원격 인계: 회사 PC 최초 인계 후 집 PC의 공통 코드·문서 변경 35개 파일을 `main`에 전송했다. 집 PC 코드 커밋 `ec406467888cecdc382429bff9ca765ee0e9653f`의 원격 SHA 일치를 확인했다. 최신 상태는 `PROJECT_STATE.md`와 `git ls-remote origin refs/heads/main`으로 확인한다. 회사 감사·반출 승인은 이 프로젝트의 대기 조건이 아니다(사용자 확인).
- 집 PC 수신/실행: 회사 PC 최초 코드를 받아 실데이터 연결과 검증을 마쳤다. 집 PC에서 다시 전송한 코드를 첫 PC가 수신·실행했는지는 미확인이다.
- Wiki: 이번 PC에서 C:\AI\llm-wiki 경로가 없음. /wiki-sync 정의·설정은 확인되지 않았고 실행하지 않음. Git과 독립이다.

## 설정과 실행

config/profile.example.json을 참고하여 각 PC에서 config/local.json을 직접 설정한다. profile은 work/home, project_root는 `.` 또는 그 PC의 실제 프로젝트 경로, data_dir는 그 PC의 비공개 데이터 경로(상대 경로 허용)다. 수동으로 저장한 스냅샷을 자동으로 읽으려면 `manual_snapshot_file`을 이 PC의 실제 파일 경로로 설정한다. 경로를 비우면 파일 자동 읽기는 비활성화되며 앱 업로드 기능은 그대로 사용할 수 있다. 프로젝트 경로 불일치는 실행을 막는다. 저장소는 data_dir/profile/mode 아래로 나뉜다. 로컬 설정 파일 자체와 DB를 복사하지 않는다.

enabled_data_adapters의 kiwoom/dart는 별도 runtime.local.json의 같은 프로필과 공급자 설정도 필요하다. infomax_manual은 이 PC에 이미 존재하는 수동 입력 파일 읽기만 허용하며 자동 수집은 하지 않는다. scheduled_jobs_enabled는 로컬 운영 의사를 기록하며 false가 기본이다. 이 값만으로 작업이 등록되지 않는다. 수동 배치는 별도 실행 가능하다.

프로젝트 폴더에서 PowerShell:
```powershell
.\scripts\pc-start.ps1
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
.\scripts\pc-finish.ps1 -RunTests
```
실행 정책이 스크립트를 차단하면 정책을 우회하지 말고 `.\.venv\Scripts\python.exe tools\pc_check.py --phase start`로 점검한다. `-RunTests`의 Python 대체는 `tools/validate_share_candidates.py --ui`다. portable 검증은 이 도구가 만든 격리 사본에서 실행한다. 가상 테스트는 실제 연결 실패의 대체가 아니다. 설치/브라우저/로컬 자산별 경계는 [PC 실행·이전 안내](PC_MIGRATION.md)를 따른다.

새 PC에서 작업본을 확보한 뒤 그 PC의 Python으로 `python -m venv .venv`, `.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt`를 실행한다. .venv/node_modules는 복제하지 않는다.

## 시작과 마감

두 보조 스크립트는 기본적으로 로컬 Git만 점검한다. 네트워크/commit/push/pull을 수행하지 않는다. `-RunTests`는 격리 home 사본에서 portable와 합성 UI 검증을 실행하고 원래 작업본에는 공유 제외 검증 로그만 남긴다. 출력의 clean_cached_refs는 과거 로컬 참조 상태이며 원격 최신 확인이 아니다. Git 미설정/dirty/진행 중 merge·rebase/divergence에서는 자동 수신을 보류한다.

수신·문서 갱신·전송 명령의 단일 실행 절차는 [investment-session](../skills/investment-session/SKILL.md)이다. `INVESTMENT START`와 `INVESTMENT CLOSE`를 사용한다. CLOSE 요청은 검증된 공유 변경의 commit/push를 포함하지만 pc-finish 스크립트 단독 실행은 전송하지 않는다. CURRENT_HANDOFF는 매 CLOSE 갱신하며 PROJECT_STATE는 상태가 실제 바뀔 때 갱신한다.

tracked_private_paths는 경로 기반 경고일 뿐 비밀 탐지 인증이 아니다. 소스/문서에 들어간 값과 전송할 전체 커밋의 내용·이력은 별도 검토한다. 비밀 발견 시 전송을 중단하고 값 없이 위치만 보고한다. 임의 이력 재작성/키 폐기는 하지 않는다.

## 작업 워크트리 · 2026-10-16 사용자 결정

두 폴더를 구분한다.

- **원본(바탕화면 실제 폴더)**: 회사 PC는 `바탕화면\신영재\한국\INVESTMENT`. Git의 메인 워크트리(`main`)이며 운영 서버(127.0.0.1:8767)가 이 코드로 돈다. `config/local.json`·`.venv`·`data/`가 여기 있다. 여기서 파일을 고치면 즉시 `restart_required`가 켜지고 작업 중인 코드가 운영에 노출되므로 직접 고치지 않는다.
- **작업 워크트리(Orca 폴더)**: Orca가 같은 저장소에서 만들어 관리하는 폴더(예: `C:\Users\<사용자>\orca\workspaces\INVESTMENT\invest-rev`). 개발·검증은 여기서 한다. 하나를 계속 재사용하고 설정·`.venv`·데이터는 없다.
- **세션**: 작업 워크트리 안에서 여는 AI 대화. 폴더와 별개이며 사용량은 세션 길이에 따라 늘어난다. 작업 단위마다 새로 열고 CLOSE 후 닫는다. 이어 갈 내용은 CURRENT_HANDOFF.md가 넘긴다.

문서만 바꾸는 경우도 같은 흐름을 기본으로 한다.

1. 시작: Orca의 작업 공간에서 새 세션을 열고 START한다. 원본 main이 clean이고 원격 main과 일치하는지 확인한 뒤, 작업 워크트리를 `pull --ff-only`로 main까지 따라잡는다. 작업 워크트리가 없으면 Orca에서 작업 공간을 만든다. Orca 밖에서 임의로 워크트리를 만들지 않는다.
2. 개발·검증: 워크트리에는 `config/local.json`과 `.venv`가 없다. 설정·DB를 복사하지 않고 원본의 `.venv` Python으로 테스트와 `tools/validate_share_candidates.py --ui`를 실행한다. 검증 기록은 워크트리의 `validation/current/`(Git 제외)에 둔다.
3. 반영: 워크트리 브랜치를 commit한 뒤 원본 main에서 `git merge --ff-only <작업 브랜치>`로 반영한다. 빨리감기가 안 되면(원격이나 main이 먼저 전진) 자동 병합하지 않고 중단·보고한다. 반영 후 기존 안전 재시작 경로로 운영 서버를 재시작하고 build/source 일치와 실제 화면을 확인한 다음 원격 main에 push한다.
4. 정돈: push와 원격 SHA 확인이 끝나면 작업 워크트리가 clean이고 원격 main과 같은지 확인하고 세션을 닫는다. 워크트리는 다음 세션에서 재사용하므로 지우지 않는다. 작업 공간을 없앨 때는 Orca에서 지우고 브랜치는 `git branch -d`로만 지운다(`-d`가 거부하면 보고). 빈 폴더·오래된 브랜치·파일 복사 백업을 작업 공간에 쌓아 두지 않으며, 남길 검증 기록은 원본의 `validation/archive/`(Git 제외)로 옮긴다.

1단계는 `INVESTMENT START`, 3단계는 `합쳐줘`(MERGE), 3·4단계 전체는 `INVESTMENT CLOSE`가 [investment-session 스킬](../skills/investment-session/SKILL.md)로 실행한다. 작업용 워크트리는 동시에 하나만 둔다. 다른 PC나 다른 세션이 원격 main을 먼저 전진시켰다면 기존 수신 규칙(`pull --ff-only`)으로 따라잡은 뒤 진행한다. 이 흐름은 운영 관례이며 기술적 잠금이 아니다.

## 공유 후보와 제외 대상

코드·테스트·의존성 목록·공통 지침·PROJECT_STATE.md·CURRENT_HANDOFF.md의 공유 가능한 상태/인계를 공유할 수 있다. 실행 후보의 정확한 파일 목록은 config/share_candidates.json을 따른다. 인증정보와 PC 로컬 설정·DB는 분리한다.

제외: config/local.json, runtime.local.json, .env, private_data/, data/, SQLite와 sidecar, 보유내역/투자노트, validation/current/, 로그·전체 세션·기존 dist/. 기존 ZIP과 과거 감사/상태 문서에는 실제 수치나 로컬 경로가 포함될 수 있어 외부 공유 승인본으로 간주하지 않는다. PROJECT_STATE.md도 기존 역사 기록을 포함하므로 전송 전 내용 검토가 필요하다.

## 보유내역 자동 동기화 · 사용자 선택 2026-10-01

보유 직접 입력을 기본으로 하고 GitHub 전용 비공개 저장소의 같은 보유내역을 두 PC에서 사용한다. scripts/open-investment.cmd가 연결 앱을 연다. 각 PC의 GitHub CLI 인증은 따로 준비한다. 보유·현금·연구/가격 입력·구성 설정의 저장과 복원은 코드 수신과 별도다. 충돌 시 덮어쓰지 않고 입력을 보관한다. 실제 사용법과 최초 이전은 [HOLDINGS_SYNC.md](HOLDINGS_SYNC.md)를 따른다. 집 PC 실제 실행은 해당 PC에서 별도로 확인한다.

## 다른 PC에서 할 일

필요할 때 Secondary PC에서 기존 작업본으로 `INVESTMENT START`를 요청한다. 안전 점검·원격 확인·수신은 위 공통 스킬을 따른다. 실제 자료가 있는 작업본의 fixture 배치를 직접 실행하는 대신 `.\.venv\Scripts\python.exe tools\validate_share_candidates.py`로 격리 home 사본의 portable 검증과 실자료 없는 화면을 확인한다. 이것은 실제 집 PC 수신·실행 증거가 아니다.

받은 커밋과 그 PC 앱/가상 데이터 검증을 각각 기록한다. 로컬 변경이나 원격 분기가 있으면 보존하고 수신을 멈춘다. 설정·키·DB를 가져오지 않는다. 작은 문서 변경으로 양방향 왕복을 별도 검증하기 전까지 두 PC 인계 완료라고 하지 않는다. 한 PC·한 쓰기 세션 규칙은 기술적으로 강제되지 않는다.
