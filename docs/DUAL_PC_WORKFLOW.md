# 두 PC 운영

현재 기준 작업본은 이 문서의 상위 프로젝트다. work/home은 대등하고 각자 로컬로 실행한다. 기존 대시보드를 새 사본으로 교체하지 않는다.

## 현재 상태

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

수신은 사용할 원격·브랜치를 확인한 별도 작업이다. clean 상태→원격 fetch→ahead/behind 및 진행 작업 확인→분기되지 않았을 때만 pull --ff-only. 로컬 미커밋 변경은 보존하고 중단한다.

마감 전송은 명시적 요청을 받은 뒤 별도로 수행한다. 이번 테스트와 다음 지점 기록→전송 파일/커밋의 경로와 내용을 검토→명시한 경로만 git add→commit→원격 fetch 및 divergence 재검사→허용된 브랜치 push→원격에서 커밋 존재 확인. URL의 인증정보와 query는 출력하지 않는다.

tracked_private_paths는 경로 기반 경고일 뿐 비밀 탐지 인증이 아니다. 소스/문서에 들어간 값과 전송할 전체 커밋의 내용·이력은 별도 검토한다. 비밀 발견 시 전송을 중단하고 값 없이 위치만 보고한다. 임의 이력 재작성/키 폐기는 하지 않는다.

## 공유 후보와 제외 대상

코드·테스트·의존성 목록·공통 지침·PROJECT_STATE.md의 일반 기업 데이터와 개인 관심 기록을 공유할 수 있다. 실행 후보의 정확한 파일 목록은 config/share_candidates.json을 따른다. 인증정보와 PC 로컬 설정·DB는 분리한다.

제외: config/local.json, runtime.local.json, .env, private_data/, data/, SQLite와 sidecar, 보유내역/투자노트, validation/current/, 로그·전체 세션·기존 dist/. 기존 ZIP과 과거 감사/상태 문서에는 실제 수치나 로컬 경로가 포함될 수 있어 외부 공유 승인본으로 간주하지 않는다. PROJECT_STATE.md도 기존 역사 기록을 포함하므로 전송 전 내용 검토가 필요하다.

## 다른 PC에서 할 일

첫 PC에서 기존 작업본의 변경과 진행 중인 작업부터 점검한다. 깨끗하고 분기되지 않은 `main`에서만 아래 순서로 수신한다.

```powershell
git status --short --branch
git fetch origin main
git status --short --branch
git pull --ff-only origin main
git rev-parse HEAD
.\.venv\Scripts\python.exe tools\verify_portable.py
```

받은 커밋과 그 PC 앱/가상 데이터 검증을 각각 기록한다. 로컬 변경이나 원격 분기가 있으면 보존하고 수신을 멈춘다. 설정·키·DB를 가져오지 않는다. 작은 문서 변경으로 양방향 왕복을 별도 검증하기 전까지 두 PC 인계 완료라고 하지 않는다. 한 PC·한 쓰기 세션 규칙은 기술적으로 강제되지 않는다.
