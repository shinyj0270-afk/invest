# Phase 0 Portability & Migration Audit

작성: 2026-10-06 KST · 실행 PC: work (Primary) · 조사 기준: main `10eb926cafb3ac175a764e54d9797c317d396361`.

## 판단

현재 Windows work/home 사이의 코드 인계는 기존 Git 및 PC별 설정 구조로 유지할 수 있다. 기본 실행기는 저장소 위치에서 루트를 계산하고 주요 저장소는 `data_dir/profile`로 분리한다. 조사 범위에서 사용자 개인 디렉터리에 강하게 묶인 주 실행 코드나 대규모 구조 변경의 필요성은 확인하지 못했다. 다만 보조 실행기의 서버 식별, 브라우저 탐색, 설치 목록, 검증의 쓰기 범위를 정리해야 환경 이동 시 잘못된 성공 판정을 줄일 수 있다.

이번 산출물은 조사 문서다. 아래 수정안은 미구현이며 다른 OS로의 이전, 집 PC 실행 성공, 실데이터 최신화를 보장하지 않는다. 별도 요청 없는 플랫폼 전환·프레임워크 교체·Agents API/Orca 도입은 제안 범위에 포함하지 않는다.

## 조사 범위와 방법

- 변경 전 clean main, 진행 Git 작업 없음, 추적 비공개 경로 없음. fetch 후 HEAD와 origin/main은 0 ahead/0 behind로 일치해 pull하지 않았다.
- 공통 지침/인계/상태를 실제 읽었다. GLOBAL_WORKFLOW v1.0은 이 대화의 앞선 원격 조회 내용을 적용했다(이번 감사에서 새로 조회한 것으로 기록하지 않음).
- Git 추적 scripts/tools/config 42개 파일을 대상으로 경로·프로세스·설정 사용을 검색하고, 관련 실행 진입점·설정 소비 코드·테스트·설치 문서를 직접 읽었다. 공유 예시 외 인증·개인 입력·원자료·DB 내용은 조사하지 않았다. PC 점검 도구의 profile/work 및 로컬 설정 메타데이터만 확인했다.
- 기본 실행 경로: scripts/open-investment.cmd → 프로젝트 .venv → tools/open_dashboard.py → tools/serve_dashboard.py → investment/live_dashboard.py.
- 비교 경로: scripts/open-investment.ps1, pc-start/pc-finish, 예약 스크립트, app.py/batch.py/collect.py, 공유/ZIP 검증기와 UI 테스트.
- 정적 발견과 실제 실행 결과를 구분했다. 라이브 서버 시작/종료, 데이터 수집, 보유 동기화, 예약 등록, 패키지 설치는 실행하지 않았다.

## 발견 사항과 우선순위

P1은 다른 작업본을 정상 앱으로 오인할 수 있는 문제, P2는 환경 재현/검증 오류 가능성, P3는 운영 문서·플랫폼 제약을 뜻한다. 보안 취약점 등급이 아니다.

| ID | 우선순위 | 위치·관측 근거 | 영향 | 후속 조치와 완료 판정 |
|---|---|---|---|---|
| A01 | P1 | scripts/open-investment.ps1:8,18은 앱 이름 문자열만 확인. tools/open_dashboard.py:12는 app/version/root_id 모두 확인. 서버의 root_id 응답은 investment/live_dashboard.py:165–167 | 같은 포트에 다른 INVESTMENT 작업본이 실행 중이면 보조 PS 실행기가 이를 자기 작업본으로 오인할 수 있음. 기본 CMD→Python 경로에는 해당 식별 검사가 있음 | PS 실행기를 기존 Python 실행기로 위임하는 방안 우선. 동일 루트 재사용·다른 루트 거부·포트 점유·잘못된 포트·시작 실패를 가상 프로세스/로컬 fixture로 검증. 실서버 종료 금지 |
| A02 | P2 | tests/test_dashboard_journey_ui.py:26, test_dashboard_upgrade_ui.py:16, test_trend_diagnostics_ui.py:10, test_trend_chart_ui.py:10에 Edge 절대 경로 직접 지정 | Edge 설치 위치가 다른 PC에서는 CHROMIUM_PATH를 지정해도 이 4개는 적용되지 않음 | 기존 환경변수→설치 브라우저/Playwright 경로 정책을 공통화. 다른 경로와 브라우저 없음 사례를 검증하고 테스트별 로직은 유지 |
| A03 | P2 | requirements.lock.txt:23 playwright==1.63.0, requirements-ui.txt:2 playwright==1.57.0. 현재 work 설치는 1.63.0 | 설치 순서에 따라 버전이 달라질 수 있음. 버전 차이 자체를 실제 테스트 실패로 단정하지 않음 | 한 버전 기준으로 정리하고 해당 브라우저와의 실행 검증 후 확정. 이번에는 설치/다운그레이드하지 않음 |
| A04 | P2 | scripts/pc-finish.ps1:11–13은 verify_all 존재 시 우선 실행. tools/verify_all.py:17 이후 build 및 fixture 배치, :26 조건부 company_finish 실행. verify_portable도 build/fixture 배치 포함 | -RunTests는 읽기 전용 감사가 아니며 작업본 산출물·fixture 저장소·로그를 쓸 수 있음. 실자료 존재 여부에 따라 검증 범위도 달라짐 | 마감 점검과 격리 검증을 명확히 구분. 기존 tools/validate_share_candidates.py의 격리 복사 패턴 활용. 실제 자료/로컬 설정/산출물 보존을 검증 |
| A05 | P2 | tools/handoff.py의 FILES는 105개, 공유 목록은 253개. 구 ZIP 목록에 CURRENT_HANDOFF/SYNC_CONTRACT/세션 스킬/open_dashboard/serve_dashboard가 없음 | 구 ZIP 생성 성공이 현재 프로젝트 전체 인계 성공을 뜻하지 않음. 현재 Git 기반 인계에는 직접 장애 없음 | 구 ZIP 도구를 명시적 legacy로 문서화하거나 별도 범위 요청 시 목록 단일화. 자동 폴더 복제나 개인 데이터 포함 금지 |
| A06 | P2 | investment/holdings_sync.py의 load_service는 루트 .local/holdings-sync/cache.json, tools/open_dashboard.py:22는 같은 루트 아래 server.log. 주요 시장/재무/추천 저장소는 data_dir/profile 사용 | data_dir만 옮겼다고 모든 로컬 상태가 이전된 것은 아님. 이는 절대 PC 경로 결합이 아니라 저장 위치가 두 군데인 구조 | 코드 인계와 데이터 이전 목록을 구분해 문서화. .local 캐시·pending 입력을 자동 복사하지 말고 기존 HOLDINGS_SYNC 절차로 확인 |
| A07 | P3 | .cmd/.ps1 및 .venv/Scripts/python.exe, Windows ScheduledTasks/Get-TimeZone 사용 | Windows 두 PC에는 의도된 방식. Linux/macOS의 실행 가능성을 보장하지 않음 | 현재는 Windows 범위 유지. 다른 OS 요청이 생기면 별도 entrypoint·작업 스케줄러·파일 잠금·브라우저 검증 계획 수립 |
| A08 | P3 | ENVIRONMENT.md의 과거 Git 미설정/Wiki 부재 기록, README의 구 ZIP 안내와 설치/검증 경로 설명 | 과거 기록을 새 PC 설치의 최신 지침으로 오해할 수 있음 | 과거 문서 표시와 현행 DUAL_PC_WORKFLOW/HOLDINGS_SYNC/Project Sync v2 링크를 점검. 과거 기록 삭제 금지 |

## 이미 분리되어 있는 부분

| 영역 | 실제 코드 근거 | 의미와 한계 |
|---|---|---|
| 프로젝트 루트 | open-investment.cmd의 %~dp0, PS의 PSScriptRoot, Python의 __file__.resolve() | 작업 폴더명/상위 위치를 하드코딩하지 않음. 같은 포트의 다른 작업본 식별은 A01 별도 |
| 로컬 설정 | investment/local_config.py:7–41 | project_root 상대 경로 허용 및 현재 checkout 대조, data_dir/manual_snapshot_file 상대 경로 해석, unknown/프로필 불일치 차단 |
| 시장·재무·추천 저장 | investment/market_discovery.py:33, company_financials.py:35–37, recommendations.py:122 | data_dir/profile을 사용. 코드 동기화만으로 각 PC의 자료가 같아지지는 않음 |
| 앱 저장/배치/수집 | app.py, batch.py, collect.py | 같은 local_config 사용. collect는 runtime.local의 프로필/권한을 추가 확인. 이번 감사에서 API 연결 상태는 확인하지 않음 |
| Python 하위 프로세스 | tools/open_dashboard.py:24, 검증기 sys.executable | 현재 실행한 인터프리터를 재사용. 각 PC .venv는 별도 구축 필요 |
| 네트워크 바인딩 | investment/live_dashboard.py:315 | 127.0.0.1에 바인딩, 다른 PC로 서버 노출하지 않음 |
| 예약 | scripts/register-tasks.ps1:1–8 | 명시적 프로필/등록 플래그, 설정 true, Windows 한국 시간대 확인. 이번에 예약을 등록하지 않음 |

## 외부 의존성과 확인 수준

| 의존성 | 용도 | work 이번 확인 | home/다른 환경 |
|---|---|---|---|
| 프로젝트 Python | 앱/검증/보조 실행기 | .venv Python 3.12.14 | 이번 미확인, .venv 복사 금지 |
| Node.js | JS 검증 및 보유 입력 계약 검사 | v24.19.0, PATH 명령 존재 | 별도 준비·검증 필요 |
| Git | 코드 인계·오프라인 점검 | 2.55.0.windows.5, fetch 성공 | 이번 미확인 |
| GitHub CLI | 선택된 비공개 보유 동기화 | 2.101.0, 명령 존재만 확인 | 인증/쓰기 권한은 이번 미조회, PC별 준비 |
| Streamlit/Playwright/tzdata | 앱/UI/한국 시간 | 설치 메타데이터 1.64.0/1.63.0/2026.4 | 새 설치 재현성은 미검증 |
| 브라우저 | UI 검증/사용자 화면 | 이번 실행하지 않음. 경로 소비 방식만 조사 | 고정 Edge 경로와 버전 차이 A02/A03 |
| PyYAML | 외부 skill-creator 형식 검사기 | 미설치 재확인 | 앱 런타임 필수 의존성으로 추가할 근거 없음 |
| 데이터 공급자 | 공개 시장/재무·명시 입력 | 소비 코드만 확인 | 네트워크/권한/원자료 가용성 별도 검증 |

## 이번 검증과 한계

- tests.test_dual_pc **13개 재실행 통과**: 프로필 불일치, 사용자 지정 경로, fixture 분리, 복사된 루트 거부, 예약 차단, 미커밋 보존, 합성 Git divergence 등 기존 테스트.
- Git 추적 파일과 AST 기반으로 두 인계 목록의 크기 및 현재 진입점 누락을 직접 비교했다. ZIP을 만들거나 실행하지 않았다.
- 문서·공유 목록만 변경한다. 분석/Infomax/포트폴리오·실행기·테스트 소스 변경 없음. 앞선 Project Sync v2의 portable 14명령은 이번 재실행 결과가 아니다.
- 현재 work에서의 감사와 합성 테스트이며 실제 home이나 다른 OS에서 실행한 결과가 아니다. 새 의존성 설치 재현·실서버 충돌 재현·실자료 조회는 미검증이다.

## 권장 후속 순서

1. **Phase 1A — 보조 실행기 동일 작업본 식별 통일(A01).** 회사 PC에서 PS 경로를 기존 Python 실행기로 위임할 수 있는지 확인하고 최소 변경. 포트/오류 전달과 기존 CMD 경로를 유지하며 격리 검증. 완료 시 두 진입점 모두 다른 루트 서버를 정상으로 수용하지 않아야 한다.
2. **Phase 1B — UI 테스트 환경 재현(A02/A03).** 브라우저 선택 규칙과 Playwright 설치 기준을 통일하고 기존 UI 시나리오 실행.
3. **Phase 1C — 검증/이전 안내 정리(A04–A08).** 쓰기 검증 격리, legacy ZIP 범위, .local 상태, 설치 문서 정리. 데이터 자동 이전은 포함하지 않는다.

권장 실행 주체 Codex, GPT-6 Astra / Medium. 실제 경로 결합이 더 넓거나 데이터 이전/대규모 구조 변경이 필요하면 근거를 정리하고 High 검토로 전환한다. 이번 감사 자체에서는 그런 구현을 시작하지 않았다.

