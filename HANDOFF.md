# 최신 인계 상태 · work13

로컬 적용 완료 / 원격 전송 미실행 / 다른 PC 수신·실행 미검증. 이번 변경은 기존 작업폴더에 있습니다. 기존 ZIP은 이전 버전이며 승인된 공유본이 아닙니다. [두 PC 운영](docs/DUAL_PC_WORKFLOW.md)과 [검증 내역](docs/DUAL_PC_VALIDATION.md)을 따르세요. 아래는 이전 인계 기록으로 보존합니다.

# work12 새 실행 앱 인계 (2026-09-28)

최신 버전은 v0.4-work12입니다. 기존 HTML 및 인포맥스 39개 지표/사용자 정책을 보존하고 app.py Streamlit 앱, SQLite, 연구/출력/배치를 추가했습니다. 실행·설치는 README.md, 이번 검증은 VALIDATION.md, 실제 명세 대비 범위와 미완료는 IMPLEMENTATION_AUDIT.md를 먼저 확인하세요.

소스 인계본은 dist/INVESTMENT_v0.4-work12.zip입니다. .venv·실데이터·SQLite·인증정보·회사 PC 로컬 설정은 포함하지 않습니다. 다른 PC에서는 그 PC의 .venv와 profile을 설정하고 가상 모드로 확인하세요. v0.4 원본은 현재 폴더에 없으므로 정확한 추가 대조는 파일 확보 후 가능하며, 이번에는 접근 가능한 v0.5의 공통 정의를 사용했습니다.

아래 이전 버전 설명은 당시 기록입니다.

---
# work11 사용자 기준 적용 완료 (2026-09-28)

여섯 가지 사용자 결정을 모두 반영했습니다. 외국인·기관 순매수/거래대금 비율도 같은 20개 공통 관측일 합계로 잠정 계산하며 거래소 범위 동일성 미확인 표시를 유지합니다. 3종목 × 13개 = 39개 지표 값입니다. 사용자 결정 대기 항목은 없습니다. 공급자 정의·달력·정정 여부 등 미확인 사실은 그대로 보존합니다.

Python 45개 및 실제 HTML 브라우저 검증 통과. 최신 소스 인계본은 dist/INVESTMENT_v0.2-work11.zip이며 원자료는 미포함입니다. 회사 PC 검토 화면도 갱신했습니다. 아래 work10 이전의 보류·버전 표시는 당시 기록이고 현재 상태는 이 기록이 우선합니다.

---
# work10 사용자 결정 반영 (2026-09-28)

금액 차이가 나면 인포맥스를 우선 사용한다는 사용자 결정을 적용했습니다. 원문 비교값과 차이는 보존합니다. 현대차 사채 차이 3,331.95억원을 반영하여 순차입금/자본은 약 125.9048%입니다. 인포맥스 미확보 유동성 부채·리스는 원문에서 보충한 혼합 출처 추정치이며 정의 동일성·중복 여부는 미확인입니다.

최근 20개 공통 관측일(2026-08-27~2026-09-23)의 외국인·기관 순매수와 평균 거래대금을 잠정 표시하여 총 33개 지표 값을 연결했습니다. 거래소 범위 미확인, 추후 정정 가능, 공급자 분류 기준·세부 범위 미확인, 공식 거래일 미대조 표시를 유지합니다. 수급/거래대금 두 비율은 범위 비교 가능성에 대한 다음 사용자 결정을 기다립니다.

최신 결정은 USER_DATA_DECISIONS.md와 config/infomax.user-decisions.json에 있습니다. 최신 소스 인계본은 dist/INVESTMENT_v0.2-work10.zip이며 원자료는 포함하지 않습니다. 아래 work09 이전의 계산 방식·보류 상태·버전 표시는 당시 기록입니다. 현재 정책은 이 기록이 우선합니다.

---
# work09 최신 대조 결과 (2026-09-28)

공식 원문과 추가 금액 33개가 정확히 일치했습니다. ROE·이자보상배율의 잠정 상태를 해제하고 순차입금/자본을 공식 유동성 부채·사채·리스 포함 기준으로 재구성하여 총 24개 지표 값을 연결했습니다. 공급자 STK 거래소 범위·수급 분류·정정 시점과 현대차 공급자 사채 산식은 미확인입니다. 최신 근거는 PROVIDER_FINANCIAL_AUDIT.md, 최신 소스 인계 ZIP은 dist/INVESTMENT_v0.2-work09.zip입니다. 아래 이전 버전의 잠정/보류 기록보다 이 기록이 우선합니다.

# 회사 PC ↔ 집 PC 작업 인계

ChatGPT INVESTMENT 프로젝트에 최신 소스 패키지와 `PROJECT_STATE.md`를 함께 보관한다. 로컬 폴더 자동 동기화는 구성하지 않는다.

## 작업 종료 시

1. `PROJECT_STATE.md`에 기준 버전, 작업한 PC, 변경 내용, 실제 테스트 결과, 미검증 항목, 다음 작업을 기록한다.
2. 아래 명령으로 빌드와 계산 검증을 실행한다.

```powershell
python -X utf8 build.py
node tests/test_engine.js
node tests/test_portfolio.js
```

3. UI가 바뀌었다면 UI 테스트도 실행한다. 실행하지 못한 검증은 미실행으로 기록한다.
4. 버전을 지정해 인계 파일을 만든다. 같은 버전이 이미 있으면 덮어쓰지 않으므로 새 버전을 사용한다.

```powershell
python -X utf8 tools/handoff.py --version v0.2-work07
python -X utf8 tools/handoff.py --verify dist/INVESTMENT_v0.2-work07.zip
```

5. `dist/INVESTMENT_버전.zip`과 `PROJECT_STATE.md`를 ChatGPT INVESTMENT에 업로드하고 “최신 기준본: 버전명”을 대화에 적는다. ZIP 업로드가 해당 화면에서 지원되지 않으면 조직에서 허용한 파일 전달 방법으로 ZIP을 옮기고 ChatGPT에는 상태 문서를 올린다.

## 다른 PC에서 시작할 때

1. 최신 버전 파일을 내려받는다. 기존 작업폴더가 있으면 미반영 변경을 비교·보존한다. 압축 해제만으로 기존 폴더를 덮어쓰지 않는다.
2. ZIP에는 최상위 `INVESTMENT/` 폴더가 들어 있다. 확인한 작업 위치에 해제한다.
3. `PROJECT_STATE.md`와 `START_ON_HOME_PC.md`를 읽는다. 패키지 검증 명령은 파일 누락·변경 확인용이며 작성자 신원을 인증하지는 않는다.
4. `config/profile.example.json`을 `config/local.json`으로 복사하고 해당 PC의 프로필과 절대 경로를 설정한다. 인증은 필요한 경우 PC별로 별도 설정한다.
5. 빌드와 테스트를 재실행한 후 다음 작업을 진행한다. 작업이 끝나면 새 버전으로 같은 인계 절차를 반복한다.

## 인계 범위

`tools/handoff.py`의 `FILES`에 적힌 소스·테스트·문서·가상 예제만 포함한다. 새 소스 파일이 생기면 내용을 확인한 후 이 목록에 추가한다. 목록에 있는 파일 자체에 비밀값을 넣지 않아야 한다.

`.env`, `config/local.json`, 인증키/토큰, 사용자 보유내역, 실제 데이터, `.venv`, `.git`, `dist`, 임의 로그·다운로드는 자동 포함하지 않는다. 회사 자료와 인포맥스 원자료는 업로드 허용 범위가 확인된 경우에만 별도 검토한다.

한 번에 한 PC의 버전을 기준으로 개발한다. 집에서 수정한 뒤 회사에서 옛 버전으로 계속하지 않도록 매 인계에서 기준 버전을 명시한다.

## 선택적 UI 테스트 환경

HTML 실행과 Node 계산 테스트는 외부 패키지가 필요 없다. UI 자동 검증에는 Python Playwright와 브라우저가 필요하다. 설치가 허용된 PC에서 프로젝트 가상환경을 사용한다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-ui.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -X utf8 tests/test_ui.py
.\.venv\Scripts\python.exe -X utf8 tests/test_portfolio_ui.py
```

이미 사용 가능한 브라우저가 있으면 다운로드 대신 `CHROMIUM_PATH`에 실제 실행 파일 경로를 지정할 수 있다. Python/Node/브라우저/인증 설치 상태는 PC마다 다르므로 이전 PC의 통과 결과를 그대로 재사용하지 않는다.
# 최신 회사 PC 인계: v0.2-work08

소스 패키지: `dist/INVESTMENT_v0.2-work08.zip`. 회사 PC 작업 범위와 미완료 확인 항목은 `COMPANY_PC_COMPLETE.md`를 우선합니다. 실제 원자료는 로컬 `private_data/infomax/runs/`에 9개 XLSX 해시 백업으로 보존되며 이 소스 패키지에는 포함되지 않습니다. 업로드는 아직 수행하지 않았습니다.
