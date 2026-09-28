# 최초 적용 결과 · 2026-09-28 · work13

## Git 인계 · work15

사용자가 공개 `shinyj0270-afk/invest`를 목적지로 확인했다. 기존 폴더에서 `main`을 초기화하고 91개 명시 파일만 stage했다. `git diff --cached --check` 통과, 로컬 설정·DB·원자료 및 목록 밖 파일은 제외. 최초 커밋 `796343f121254165bc184c4ed9be7cc6fd79e697`과 후속 상태 문서 커밋을 원격에 전송하고 `git ls-remote origin refs/heads/main`으로 최종 로컬 HEAD와 같은 SHA를 확인했다. 집 PC에서는 아직 받거나 실행하지 않았다.

## 사용자 정정 후 상태 · work14

이 프로젝트는 일반 상장기업 데이터와 개인 관심 기록이며 회사 감사·반출 승인 대상 민감자료가 없다는 사용자 설명을 적용했다. `config/share_candidates.json`은 원본 README.md와 PROJECT_STATE.md를 포함한다. 아래의 과거 "회사 반출 승인 대기" 및 "대체 상태 문서" 판단은 현재 적용되지 않는다. 원격 저장소의 목적지만 확인되면 Git 인계를 진행할 수 있다. 인증정보와 PC 로컬 데이터는 계속 분리한다.

## 후속 적용 · work14 · 2026-09-28

수동 저장 스냅샷 경로를 `config/local.json`의 `manual_snapshot_file`로 옮겼다. 회사 PC는 기존 파일 경로를 설정으로 유지한다. 다른 PC의 예시는 null이며, 실제 파일이 없으면 실제 모드는 빈 상태다. 앱 데이터 상태의 인포맥스 문구와 보존 HTML의 회사 PC 3종목 고정 문구를 현재 PC/모드 기준으로 바꿨다. 기존 원자료는 이동·복사하지 않았다.

선별 후보 41개에 대해 `tools/validate_share_candidates.py`를 실행해 감지 항목 0개, 임시 home 프로필 빌드·Python/JS·가상 배치·실제 빈 상태 검증 통과. 회사 PC `tools/verify_all.py` 통합 12개 명령 모두 통과, Python 92개와 JS/기존 UI/A4/실제 로컬 값 대조 포함. `tests/verify_live_app.py`가 실행 중인 앱 8탭·저장·내보내기·모바일 폭을 다시 통과했다. 구체 경계는 `docs/SHARE_REVIEW.md` 참고. 아래 work13 수치는 이전 실행 기록이다.

별도 AppTest로 회사 PC의 실제 저장자료 모드도 다시 열어 8개 탭·실제 자료 표시·설정된 로컬 수동 파일 존재를 확인했다. 원자료 파일을 출력하거나 이동하지 않았다.

## 대조 결과와 수정

현재 프로젝트와 상위 작업폴더 모두 Git 저장소가 아니었다. branch/upstream/미푸시/추적 이력은 존재하지 않아 검사할 대상이 없으며, 기존 파일 전체를 보존했다. 새 저장소/원격/사본을 만들지 않았다. 기존 AGENTS.md/CLAUDE.md도 없어 공통 지침과 단방향 가져오기를 추가했다.

활성 v0.5의 집 PC 우선 문구를 대등 운영으로 수정했다. 원본 폴더의 동일 명세도 맞췄다. 과거 작업 기록은 보존했다. data_dir가 실제 앱/배치/수집기에 적용되지 않던 부분을 공통 로더로 연결했고, 복사된 다른 PC의 project_root와 잘못 지정한 배치 프로필을 거부한다. API는 PC 로컬 허용 목록과 runtime 공급자 권한을 모두 요구한다. 기존 수동 인포맥스 입력만 work에서 유지했다.

## 변경 파일

- 공통 규칙: AGENTS.md, CLAUDE.md, docs/DUAL_PC_WORKFLOW.md, docs/DUAL_PC_VALIDATION.md.
- 코드: investment/local_config.py, app.py, batch.py, collect.py, tools/pc_check.py.
- 설정/스크립트: .gitignore, config/profile.example.json, **비공개** config/local.json, scripts/pc-start.ps1, scripts/pc-finish.ps1, scripts/register-tasks.ps1.
- 검증/패키징: tests/test_dual_pc.py, tests/test_research_app.py, tools/verify_all.py, tools/handoff.py. 패키징 목록은 새 모듈을 포함하도록 수정했으나 새 ZIP 생성/전송은 하지 않았다.
- 문서: INVESTMENT_META_PROMPT_v05.md와 상위 폴더의 같은 명세, README.md, ENVIRONMENT.md, PROJECT_STATE.md, VALIDATION.md, HANDOFF.md, START_ON_HOME_PC.md.
- 실행 산출물: 기존 build.py 생성 HTML, validation/current/ 검증 로그·이미지·PDF와 가상 배치 저장소. 실제 원본 재수집은 하지 않았다. 산출물은 공유 대상이 아니다.

## 이번 실행 증거

프로젝트 .venv 사용. 현재 앱은 127.0.0.1:8501로 실행 중인 기존 Streamlit 서버에서 변경 소스를 재로딩해 검증했다.

| 실제 명령 | 결과 |
|---|---|
| scripts/pc-start.ps1 | work, 올바른 data_dir, 예약 false, remote_pending |
| scripts/pc-finish.ps1 -RunTests | tools/verify_all.py 12개 명령 모두 exit 0 |
| .venv/Scripts/python.exe -m unittest tests.test_dual_pc -v | 최종 새 테스트 12개 통과 |
| .venv/Scripts/python.exe tests/verify_live_app.py | 실제 브라우저 8탭·가상 모드·조건 저장·JSON/CSV/HTML·모바일 폭·JS 오류 없음 |
| scripts/pc-start.ps1 및 pc-finish.ps1 재실행 | UTF-8 경로 출력 정상, 점검만 실행 |

통합 검증 시 Python 89개(기존 79 + 최초 신규 10), JS 84개, 기존 UI 43개 통과. 이후 PC별 경로를 실제 AppTest로 저장·분리하는 검사와 예약 비활성 CLI 거부 검사를 추가해 신규 12개 전체를 재실행했다. 고유 Python 테스트는 총 91개이며 통합 실행 한 번에 91개를 실행했다고 주장하지 않는다. 이번 결과는 validation/current/results.json과 dual-pc.txt에 남겼다.

새 테스트는 임시 로컬 저장소에서 clean/no remote/dirty/diverged/merge marker/추적된 비공개 경로/ignore/원격 URL 비노출을 확인했다. 테스트의 fetch/push는 임시 폴더의 로컬 bare 저장소에만 수행했다. 실제 프로젝트나 외부 Git 서버에는 commit/fetch/pull/push하지 않았다. 점검기는 상태를 바꾸지 않으며 remote_freshness=not_fetched로 출력한다.

마지막 보완 후 신규 12개를 다시 실행해 통과했다. 하위 폴더에서 시작해도 상위 저장소 전체의 변경을 검사한다. 패키징 목록에서 과거 validation 로그/출력을 제거했고 파일 존재·중복 없음·validation 경로 제외를 확인했다. 패키지 자체는 만들지 않았다.

기존 A4 검증도 이번 통합 실행에서 재실행: 가상 1개와 실제 저장자료 3개 모두 A4 1페이지·한글 추출·텍스트 경계 검사 통과. 저장 실데이터 대조는 9개 XLSX 체크포인트·추가 숫자 144개·화면 지표 39개 통과. 이는 기존 로컬 자료 대조이며 신규 공급자 조회나 정의 인증이 아니다.

## 공유와 미완료

공통 운영 문서·소스·테스트·의존성 파일과 원본 README/PROJECT_STATE를 선별했다. 로컬 설정·DB/sidecar·보유내역·투자노트·로그·전체 세션·검증 출력·기존 ZIP은 이번 인계 후보에서 제외한다. .gitignore는 이미 추적된 파일의 제외를 보장하지 않는다.

- 현재 회사 PC: 로컬 적용·검증 완료.
- 원격 전송: 미실행. 원격 저장소의 목적지 확인 대기.
- 집 PC: 수신·환경 설치·실행·왕복 인계 미검증.
- API: 키움/OpenDART 인증 및 권한 설정 대기 유지. 인포맥스 자동 연동/외부 저장/동시접속 권한 미확인 유지.
- Wiki: 지정 경로 없음. 재구축/실행/동기화 없음.
- 실제 예약 등록, 자동 시작, 전역 환경 변경 없음.
