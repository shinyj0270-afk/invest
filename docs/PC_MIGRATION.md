# Windows PC 실행·검증·인계

work는 Primary, home은 Secondary다. 같은 branch는 한 PC의 한 쓰기 세션만 수정한다. 최신 코드와 상태는 승인 Git main, 다음 작업은 CURRENT_HANDOFF.md를 사용한다. Linux/macOS 지원은 이번 범위가 아니다.

## 새 PC 또는 새 작업 폴더

1. 기존 작업본이 있으면 미완료 변경과 진행 작업을 먼저 확인한다. 새 폴더로 덮어쓰지 않는다. Git 수신은 [공통 START](../skills/investment-session/SKILL.md)를 따른다.
2. 이 PC에 Python 3.12, Git, Node.js를 준비하고 프로젝트의 .venv를 만든다. 보유 비공개 동기화를 사용할 경우 GitHub CLI와 이 PC의 인증이 별도로 필요하다. 다른 PC의 .venv·인증 파일을 복사하지 않는다.
3. `.venv\Scripts\python.exe -m pip install -r requirements.lock.txt`로 의존성을 준비한다. 선택적 requirements-ui.txt의 Playwright도 lock과 같은 1.63.0이다. 브라우저는 기존 설치를 우선 사용하며 자동 다운로드하지 않는다.
4. config/profile.example.json을 참고해 **이 PC에서** config/local.json을 설정한다. profile은 사용자 확인 work/home, project_root는 `.`, data_dir와 manual_snapshot_file은 이 PC의 위치다. 예약은 false를 기본으로 유지한다. 런타임 공급자 권한/인증은 [기존 실행 지침](DUAL_PC_WORKFLOW.md)대로 별도 설정한다.
5. 먼저 오프라인 점검, 다음 격리 검증을 실행한다. 통과해도 실자료 확보나 다른 PC 검증이 완료된 것은 아니다.

```powershell
.\scripts\pc-start.ps1
.\scripts\pc-finish.ps1 -RunTests
```

PowerShell 정책이 차단하면 우회하지 않고 같은 기능의 Python 명령을 사용한다.

```powershell
.\.venv\Scripts\python.exe tools\pc_check.py --phase start
.\.venv\Scripts\python.exe tools\validate_share_candidates.py --ui
```

## 실행기

기본은 `scripts/open-investment.cmd`다. PowerShell은 `scripts/open-investment.ps1 -Port 8767`이며 두 경로 모두 기존 tools/open_dashboard.py를 호출한다. Python 실행기는 health의 app/version/root_id를 대조해 **현재 작업본**의 서버만 재사용한다. 다른 앱/작업본이 포트를 점유하면 오류를 보고하며 기존 서버를 종료하지 않는다. 브라우저를 열지 않을 때는 PS의 `-NoBrowser` 또는 Python의 `--no-browser`를 사용한다. Python 실패 종료코드는 PS 호출자에게 전달된다.

## UI 브라우저 선택

감사에서 고정 경로가 발견된 dashboard_journey/dashboard_upgrade/trend_diagnostics/trend_chart UI 테스트는 tools/browser_runtime.py를 공유한다. 순서는 `CHROMIUM_PATH` → PATH의 chromium/chromium-browser/msedge/google-chrome → Windows 환경변수 기반 Edge/Chrome 설치 위치 → Playwright의 설치된 기본 Chromium이다. 명시한 경로가 없으면 대체 브라우저로 조용히 넘어가지 않고 오류를 낸다. 기본 Chromium도 없으면 Playwright 오류를 그대로 보고한다. 나머지 기존 UI 테스트는 각 파일의 기존 CHROMIUM_PATH 처리 방식을 유지한다.

```powershell
$env:CHROMIUM_PATH = '<이 PC에서 확인한 브라우저 실행파일 경로>'
.\.venv\Scripts\python.exe tools\validate_share_candidates.py --ui
```

## 검증의 쓰기 범위

- pc-start/pc-finish 기본: 오프라인 점검만 수행하며 Git 전송/상태 문서 갱신은 하지 않는다.
- pc-finish -RunTests: 공유 후보 검토 후 임시 home 사본에서 portable 검사와 합성 UI4개를 실행한다. 로컬 설정 대신 격리용 home 설정을 만들며 원자료/DB/보유 캐시는 복사하지 않는다. 실행 결과와 로그는 원래 작업본의 공유 제외 validation/current에 남긴다.
- tools/verify_portable.py: build/fixture 배치를 포함하므로 **격리 사본 안에서** 사용한다. 운영 폴더에서 직접 실행하는 읽기 전용 점검이 아니다.
- tools/verify_all.py: 기존 동작을 유지한 in-place 검증기다. 자동 마감 경로에서 제외했다. 명시적인 `--in-place` 없이는 실행을 거부한다. 허용하면 작업본 HTML/fixture/로그를 쓰고 조건에 따라 기존 원자료 검사를 수행하므로 일반 마감에는 위 격리 경로를 사용한다.

## 로컬 자산별 경계

| 자산 | 위치/역할 | 이전 원칙 |
|---|---|---|
| 공통 코드·문서 | Git main | 검증된 commit을 안전하게 수신 |
| local/runtime 설정 | config의 비추적 로컬 파일 | 이 PC 경로·프로필·권한으로 직접 설정 |
| 인증 | 환경변수/CLI 인증 저장소 | PC별 준비, Git/전체 복사 금지 |
| 시장·재무·추천·DB | data_dir/profile 하위 | 코드 수신과 별개. 확보/갱신 상태를 각 PC에서 확인 |
| 수동 원자료 | manual_snapshot_file 및 private_data 등 | 자동 복제하지 않음 |
| 보유 캐시/pending 입력 | .local/holdings-sync/cache.json | data_dir 밖의 별도 자산. 캐시를 덮어쓰거나 직접 복사하지 않고 [보유 동기화 절차](HOLDINGS_SYNC.md)의 충돌 보존/확인 적용 |
| 서버 로그 | .local/holdings-sync/server.log | 운영 확인용, 공유 제외 |
| 화면 저장 상태 | 브라우저 저장소 | 코드 인계로 이전되지 않음. 자동 복제를 가정하지 않음 |
| .venv·브라우저·예약 | PC별 실행 환경 | 재구성/검증 필요. 예약은 별도 요청 없으면 등록하지 않음 |

구 tools/handoff.py는 과거105파일 목록의 **부분 ZIP** 도구다. help/생성 시 legacy임을 표시한다. ZIP 해시 검증은 내부 무결성 검사이며 최신 앱·Project Sync v2 인계 완전성 검사가 아니다. 최신 인계에 사용하지 않는다.

## 실제 home에서 남는 확인

필요할 때 home의 기존 작업본에서 START로 최신 commit을 수신하고 PC별 .venv/Node/브라우저/설정 상태를 확인한다. 격리 검증 후 기본 실행기로 앱을 열어 루트/포트·화면·자료 상태를 확인한다. 보유 충돌 또는 pending 입력은 기존 절차로 보존한다. work에서 실행한 격리 home 검사는 이 실제 수신·실행을 대신하지 않는다.
