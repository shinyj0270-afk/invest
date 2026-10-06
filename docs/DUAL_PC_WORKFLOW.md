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
실행 정책이 스크립트를 차단하면 정책을 우회하지 말고 `.\.venv\Scripts\python.exe tools\pc_check.py --phase start`로 점검한다. 가상 테스트는 앱에서 직접 선택한다. 실제 연결 실패의 대체가 아니다. 선별 인계본에는 `tools/verify_all.py` 대신 `tools/verify_portable.py`를 사용한다.

새 PC에서 작업본을 확보한 뒤 그 PC의 Python으로 `python -m venv .venv`, `.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt`를 실행한다. .venv/node_modules는 복제하지 않는다.

## 시작과 마감

두 보조 스크립트는 기본적으로 로컬 Git만 점검한다. 네트워크/commit/push/pull을 수행하지 않는다. `-RunTests`도 검증만 실행한다. 출력의 clean_cached_refs는 과거 로컬 참조 상태이며 원격 최신 확인이 아니다. Git 미설정/dirty/진행 중 merge·rebase/divergence에서는 자동 수신을 보류한다.

수신·문서 갱신·전송 명령의 단일 실행 절차는 [investment-session](../skills/investment-session/SKILL.md)이다. `INVESTMENT START`와 `INVESTMENT CLOSE`를 사용한다. CLOSE 요청은 검증된 공유 변경의 commit/push를 포함하지만 pc-finish 스크립트 단독 실행은 전송하지 않는다. CURRENT_HANDOFF는 매 CLOSE 갱신하며 PROJECT_STATE는 상태가 실제 바뀔 때 갱신한다.

tracked_private_paths는 경로 기반 경고일 뿐 비밀 탐지 인증이 아니다. 소스/문서에 들어간 값과 전송할 전체 커밋의 내용·이력은 별도 검토한다. 비밀 발견 시 전송을 중단하고 값 없이 위치만 보고한다. 임의 이력 재작성/키 폐기는 하지 않는다.

## 공유 후보와 제외 대상

코드·테스트·의존성 목록·공통 지침·PROJECT_STATE.md·CURRENT_HANDOFF.md의 공유 가능한 상태/인계를 공유할 수 있다. 실행 후보의 정확한 파일 목록은 config/share_candidates.json을 따른다. 인증정보와 PC 로컬 설정·DB는 분리한다.

제외: config/local.json, runtime.local.json, .env, private_data/, data/, SQLite와 sidecar, 보유내역/투자노트, validation/current/, 로그·전체 세션·기존 dist/. 기존 ZIP과 과거 감사/상태 문서에는 실제 수치나 로컬 경로가 포함될 수 있어 외부 공유 승인본으로 간주하지 않는다. PROJECT_STATE.md도 기존 역사 기록을 포함하므로 전송 전 내용 검토가 필요하다.

## 보유내역 자동 동기화 · 사용자 선택 2026-10-01

보유 직접 입력을 기본으로 하고 GitHub 전용 비공개 저장소의 같은 보유내역을 두 PC에서 사용한다. scripts/open-investment.cmd가 연결 앱을 연다. 각 PC의 GitHub CLI 인증은 따로 준비한다. 보유·현금·연구/가격 입력·구성 설정의 저장과 복원은 코드 수신과 별도다. 충돌 시 덮어쓰지 않고 입력을 보관한다. 실제 사용법과 최초 이전은 [HOLDINGS_SYNC.md](HOLDINGS_SYNC.md)를 따른다. 집 PC 실제 실행은 해당 PC에서 별도로 확인한다.

## 다른 PC에서 할 일

필요할 때 Secondary PC에서 기존 작업본으로 `INVESTMENT START`를 요청한다. 안전 점검·원격 확인·수신은 위 공통 스킬을 따른다. 실제 자료가 있는 작업본의 fixture 배치를 직접 실행하는 대신 `.\.venv\Scripts\python.exe tools\validate_share_candidates.py`로 격리 home 사본의 portable 검증과 실자료 없는 화면을 확인한다. 이것은 실제 집 PC 수신·실행 증거가 아니다.

받은 커밋과 그 PC 앱/가상 데이터 검증을 각각 기록한다. 로컬 변경이나 원격 분기가 있으면 보존하고 수신을 멈춘다. 설정·키·DB를 가져오지 않는다. 작은 문서 변경으로 양방향 왕복을 별도 검증하기 전까지 두 PC 인계 완료라고 하지 않는다. 한 PC·한 쓰기 세션 규칙은 기술적으로 강제되지 않는다.
