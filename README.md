# 두 PC 운영 적용 · work14 · 2026-09-28

두 PC에 인계할 코드·문서 91개는 `config/share_candidates.json`에 명시했습니다. 검사·임시 home 실행 결과와 원격 상태는 [공유 범위 점검](docs/SHARE_REVIEW.md)에 있습니다. 원본 README와 PROJECT_STATE는 포함하고 PC별 DB·설정·인증정보는 제외합니다.

GitHub 원격: [shinyj0270-afk/invest](https://github.com/shinyj0270-afk/invest) `main`. 회사 PC 최초 커밋은 원격에서 확인했습니다. 집 PC에서의 수신·실행은 아직 확인하지 않았습니다.

기존 앱을 보존하면서 회사/집 PC 공통 지침과 로컬 설정을 분리했습니다. 현재 회사 PC 로컬 검증 완료, 원격 미연결, 집 PC 미검증입니다. [운영 절차](docs/DUAL_PC_WORKFLOW.md)와 [변경·검증 내역](docs/DUAL_PC_VALIDATION.md)을 먼저 확인하세요. 아래 work12 설명은 기존 기능 기록입니다.

# INVESTMENT · 연구 앱 v0.4-work12

2026-09-28 회사 PC에서 기존 work11에 Python/Streamlit 앱을 추가했습니다. 기존 HTML·인포맥스 사용자 결정·수동 보유/포트폴리오 코드는 보존했습니다. 상세 명세 대조는 [IMPLEMENTATION_AUDIT.md](IMPLEMENTATION_AUDIT.md)를 확인하세요.

## 실행

PowerShell에서:

```powershell
cd '<이 PC의 INVESTMENT 작업폴더>'
.\.venv\Scripts\python.exe -m streamlit run app.py
```

주소는 http://127.0.0.1:8501 입니다. 실제 저장자료 모드는 로컬 SQLite의 마지막 정상 스냅샷 또는 기존 인포맥스 검토 JSON을 읽습니다. 없으면 빈 상태로 남습니다. 가상 테스트는 사용자가 사이드바에서 직접 선택합니다. DB는 `data/<home|work|unknown>/<fixture|user_input|live>/research.sqlite3`에 분리됩니다.

새 PC에서는 그 PC의 프로젝트 경로에서 Python 3.12로 `.venv`를 만들고 `.venv\Scripts\python.exe -m pip install -r requirements.lock.txt`를 실행하세요. `config/local.json`의 프로필은 해당 PC에서 명시적으로 설정하세요. 회사 PC 설정·실데이터·인증정보는 인계 ZIP에 없습니다.

## 추가 기능

- SQLite 원자적 스냅샷·staging 분리, 조건/피어집합 저장, 이벤트 중복 방지.
- AND/OR 3상태 검색, 시장/산업/경로·정렬, 조건 JSON 및 CSV 출력. 기존 JS 엔진과 Python 판정 동등성 검사.
- 기업 원계정·TTM/CAGR/FCF 및 5/60일 수급 계산 계약, 동일 기간 피어 중앙값·최소 5표본 백분위.
- 같은 스냅샷의 A4 HTML·상대가치 시나리오. 음수 EPS나 피어 부족 시 산출 불가.
- 기존 품질 점수와 다섯 성장 경로, 별도 문서 상태, 최대 10개 경로 균형 목록.
- 추세·상대 모멘텀·수축 프록시·돌파 관찰. 충분한 이력/조정/범위 없으면 자료 부족.
- 조회 전용 공급자 어댑터와 일간/주간 로컬 계산 명령. 계좌/주문 호출 없음.

실제 3종목에는 장기 원계정·조정 OHLCV·벤치마크·문서 근거가 부족하여 신규 연구 판정은 자료 부족입니다. 인포맥스 39개 기존 지표 값과 사용자가 허용한 잠정 기준은 유지합니다. 기능 구현과 실데이터 연결 완료를 구분합니다.

## 배치와 검증

```powershell
.\.venv\Scripts\python.exe batch.py init-fixture --profile work
.\.venv\Scripts\python.exe batch.py daily --profile work --mode fixture
.\.venv\Scripts\python.exe batch.py weekly --profile work --mode fixture
.\.venv\Scripts\python.exe tools/verify_all.py
.\.venv\Scripts\python.exe tests/verify_live_app.py
```

마지막 명령은 앱을 별도 터미널에서 실행한 상태로 사용합니다. Windows UI/PDF 검사는 설치된 Edge를 사용합니다. 다른 PC는 `CHROMIUM_PATH`를 해당 브라우저 실행파일 경로로 설정하세요. 순수 JS 회귀 검사는 Node.js가 필요합니다.

실데이터 파일의 명시적 로컬 적재 및 계산:

```powershell
.\.venv\Scripts\python.exe batch.py import-file --profile work --mode user_input --file private_data/infomax/snapshot-review.json
.\.venv\Scripts\python.exe batch.py daily --profile work --mode user_input
.\.venv\Scripts\python.exe batch.py weekly --profile work --mode user_input
```

배치는 저장자료를 재계산하며 API 수집이나 휴장일 검증을 수행했다고 주장하지 않습니다. 공식 달력 미대조 상태를 결과에 남깁니다. UI rerun은 스케줄러가 아닙니다. `scripts/register-tasks.ps1`와 `unregister-tasks.ps1`는 설명용으로 준비했고 실제 등록하지 않았습니다. 명시적 프로필·확인 스위치 및 한국 시간대가 있어야 등록할 수 있습니다. PC가 꺼지면 실행되지 않습니다.

## 공급자 설정 대기

`config/runtime.example.json`을 같은 PC의 비공개 `config/runtime.local.json`으로 복사하고 실제 허용된 공급자만 설정합니다. 키움은 `KIWOOM_ACCESS_TOKEN`, OpenDART는 `OPENDART_API_KEY` 환경변수 참조만 사용합니다. 비밀값을 JSON 파라미터나 코드에 넣지 마세요.

`collect.py dart financial --params <비밀값 없는 요청JSON>`은 회사 고유번호·사업연도·보고서코드·연결기준을 받습니다. `.venv\Scripts\python.exe`로 실행합니다. 키움은 `ka10001/ka10059/ka10081`만 허용하며 현재 공식 입력·응답 단위/거래소 정의 검토 전에는 `kiwoom_spec_verified=false`로 차단됩니다. 조회 응답은 비공개 staging에 저장하며 검증 스냅샷으로 자동 승격하지 않습니다. 원문 응답→전 시장 정규화 자동 적재는 미완료입니다.

공식 확인 출처: [OpenDART 전체 재무제표](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019020), [키움 공식 가이드](https://openapi.kiwoom.com/m/guide/index?guideNum=06). 실제 인증 조회는 실행하지 않았습니다.

---

# 이전 HTML v0.2 배포 기록

> 2026-09-28 회사 PC 작업본: 현재 상태는 [PROJECT_STATE.md](PROJECT_STATE.md), 회사↔집 인계는 [HANDOFF.md](HANDOFF.md), 집 PC 시작 지시문은 [START_ON_HOME_PC.md](START_ON_HOME_PC.md)를 먼저 확인하세요. 아래 내용과 VALIDATION.md는 원 배포 설명입니다. 현재 Windows에서 재실행한 검증은 상태 문서에 따로 기록했습니다.

작성: 2026-09-27

2026-09-28 추가: **인포맥스 CSV/XLSX 파일 → 대시보드 JSON 변환**을 지원합니다. [사용 절차](INFOMAX_IMPORT.md)를 확인하세요. `examples/infomax_snapshot_fixture.json`을 상단의 데이터 파일 가져오기로 열면 세 가상 기업의 연결 결과를 바로 확인할 수 있습니다. 실제 공급자 자동 연결은 아닙니다.

기존 v0.1 HTML/JavaScript 시제품을 보존하면서 **보유종목 점검**과 **최대 5개 기업 포트폴리오** 탭을 추가했습니다. 실제 실행 가능한 단일 HTML과 소스·가상 입력·테스트를 제공합니다. 지시문 버전은 v0.5, 이 HTML 시제품의 버전은 v0.2입니다.

**현재 사용자 PC에 설치된 운영본을 수정한 것이 아닙니다.** 실시간 시세·공시·증권계좌 연결과 실제 종목의 투자 의견은 포함하지 않습니다. 새 두 탭은 입력자가 검토한 연구 상태와 출처 메타데이터를 이용하는 규칙형 참조 구현입니다. 실사용 데이터와 투자 적합성 검증은 별도입니다.

## 바로 열기

`INVESTMENT_Dashboard.html`을 데스크톱 브라우저로 엽니다. Aside, 서버, 유료 API, 로그인, 새 모델 구독 없이 화면을 사용할 수 있습니다. 휴대전화의 파일 미리보기 앱은 JavaScript를 실행하지 않을 수 있으므로 데스크톱 브라우저에서 먼저 확인하세요. 이번 검증 환경은 Linux Chromium이며 Windows/Android 기기 실행은 별도 확인이 필요합니다.

사용 흐름은 **04 보유종목 점검 → 가상 예제 실행 → 근거 보기 → 05 포트폴리오 → 설정 확인 체크 → 구성안 계산**입니다. 가상 예제는 실제 기업·가격·공시가 아닌 A~H 기업입니다. 먼저 가상 예제로 데이터 부족, 매도 검토, 보유 의견과 과대 비중의 분리를 확인하세요.

실제 자료는 **가상 예제를 비운 뒤** 명세에 맞춘 사용자 JSON을 가져오거나 보유목록을 직접 입력합니다. 보유수량만 입력하면 기업 상태를 알 수 없으므로 의견은 ‘판단 보류’로 남습니다. 가격·기업 연구를 별도로 제공하거나 기존 앱의 분석 스냅샷과 연결해야 합니다. 계좌번호·인증키는 넣지 마세요.

브라우저의 파일 열기 제약 때문에 로컬 서버가 꼭 필요한 경우에만, **이 패키지 폴더에서** 다음 명령을 사용할 수 있습니다. 작업환경에서 실행이 허용되는지 먼저 확인하세요.

```text
python -m http.server 8765 --bind 127.0.0.1
```

주소: `http://127.0.0.1:8765/INVESTMENT_Dashboard.html`

다른 프로젝트 폴더나 비밀정보 폴더를 HTTP 루트로 사용하지 않습니다. 0.0.0.0 바인딩, 회사망/인터넷 공개, 서버 자동 등록을 하지 않습니다.

## 추가 기능

### 보유종목 점검

직접 입력/JSON 가져오기, 수량·평균매입가·현금 관리, 평가액·단순 평가손익·현재 비중, 근거 보기, 검토 결과 내보내기를 제공합니다. 의견은 **보유 검토 / 비중 축소 검토 / 매도 검토 / 재검토 / 판단 보류**입니다.

기업의 사업 전망에 대한 의견과 포트폴리오 비중 의견은 별도입니다. 기업 의견이 보유여도 동일 기업 합산 비중이 설정 상한을 넘으면 축소 검토를 표시합니다. 매입가는 손익 계산에만 사용하며 매입가 또는 과거 손실률만으로 기업 의견을 바꾸지 않습니다.

필수 근거/가격이 누락되거나 설정 기한을 넘으면 보류합니다. 근거가 확인된 중대 위험은 관련 없는 가격·가치평가 자료 누락 때문에 숨기지 않지만, 실제 주문이나 거래 가능성을 의미하지는 않습니다. 현재 HTML은 출처의 실제 존재나 본문과 입력 주장의 일치까지 외부 검증하지 않습니다.

### 최대 5개 기업 포트폴리오

적격 후보에서 고유 기업 최대 5개를 제안하며 기업·산업·입력 공통위험군 비중 상한과 현금 가정을 적용합니다. 빈 슬롯을 다른 기업에 몰아주지 않습니다. 현금은 기업 수에 포함하지 않습니다.

자료가 없으면 ‘자료 부족’이지 현금 100% 투자 의견이 아닙니다. 충분한 입력으로 판정한 뒤 적격 기업이 0개인 경우에만 해당 모형의 현금 100% 결과가 가능합니다. 보유목록에서 제안에 들지 않은 기업을 삭제하거나 자동 매도하지 않습니다.

첫 모형은 **고정 슬롯 균등배분**입니다. 가치평가 매력/보통 → 사업 개선/안정 → 기존 보유 → 코드 순으로 적격 입력을 확인하는 휴리스틱이며 기대수익 최적화·예측 확률 모형이 아닙니다. 기본 숫자는 개발 예시이고 실제 운용에 적합하다고 검증되지 않았습니다. 시나리오 손실 기준과 확인 체크를 입력해야 결과가 나옵니다.

공통 하락 가정은 비중을 이용한 단순 산술입니다. ‘-30% 가정에서 손실 10% 이하’로 설정하더라도 실제 손실이 10% 안에 멈춘다는 뜻이 아닙니다. 5개 이하 주식은 집중형 구성이고 기업·산업 제한만으로 충분한 분산을 보장하지 못합니다.

## 기존 기능 보존

01 조건검색(AND/OR·3상태·조건 저장·CSV 출력), 02 기업분석(정규화 수치 입력·요약·이력), 03 산업비교(동일 산업 모집단·중앙값), 데이터·계산 기준 화면을 유지했습니다. `src/engine.js`와 `src/ui.js`는 v0.1과 동일합니다.

기존 시장 데이터 JSON과 새 보유·연구 JSON은 현재 시제품에서 분리되어 있습니다. 새 입력을 가져와도 조건검색 원장이 자동으로 채워지지 않습니다. 기존 정규화 기업 데이터에 보유·연구를 연결하는 실제 통합 계약은 `INVESTMENT_META_PROMPT_v05.md`에 있습니다.

v0.4에 설계된 Streamlit 전환·One-Pager·장기성장·추세추종·자동 수집이 모두 이번 HTML에 구현되었다는 뜻이 아닙니다. 현재 PC의 실제 구현 상태를 먼저 검사해야 합니다.

## 파일

| 파일 | 용도 |
|---|---|
| `INVESTMENT_Dashboard.html` | 실행용 단일 HTML |
| `src/portfolio_engine.js` | 순수 함수 기반 판정·배분·검증 |
| `src/portfolio_ui.js` | 신규 탭·입력·근거·리포트 |
| `src/engine.js`, `src/ui.js` | 보존한 기존 계산/UI |
| `src/shell.html`, `src/style.css`, `build.py` | HTML 조립 소스 |
| `examples/holdings_research_fixture.json` | 명시적인 허구 기업 테스트 |
| `examples/holdings_research_empty.json` | 보유·연구 빈 입력 |
| `snapshot.schema.json`, `snapshot_empty.json` | 보존한 기존 시장 스냅샷 계약 |
| `DATA_DICTIONARY.md` | 새 입력과 판정·배분 산식 |
| `INVESTMENT_META_PROMPT_v05.md` | 기존 Codex·Claude 프로젝트 통합 지시문 |
| `CODEX_APPLY_v05.txt` | 짧은 전달 문구 |
| `tests/`, `VALIDATION.md` | 실제 기능 검사와 한계 |
| `legacy/` | 과거 설명·로그·화면, 현재 검증 아님 |

## 개발·재검증

소스 수정 후 `python build.py`로 단일 HTML을 다시 만듭니다.

```text
node tests/test_engine.js
node tests/test_portfolio.js
python tests/test_ui.py
python tests/test_portfolio_ui.py
```

브라우저 검사는 Python용 Playwright와 Chromium이 필요합니다. 이미 있는 개발환경을 우선하고 전역/회사 환경에 임의 설치하지 않습니다. 테스트는 `CHROMIUM_PATH`, 시스템 chromium/chromium-browser 순서로 실행 파일을 찾고, 없으면 Playwright의 설치된 브라우저를 사용합니다. Windows에서 허용된 Chrome/Chromium 경로를 지정하거나 해당 프로젝트 환경의 Playwright 브라우저를 준비한 뒤 재검증하세요.

이번 배포의 검증은 Linux 격리 환경에서 수행했습니다. 기록된 테스트 수가 Windows에서 자동 보장되는 것은 아닙니다. 실제 명령과 결과는 `VALIDATION.md`를 확인하세요.

## 개인정보·회사 PC

새 보유·연구 입력은 브라우저 메모리에서만 처리하며 새로고침하면 사라집니다. 명시적인 ‘현재 입력 내보내기’로 만든 파일은 개인 금융정보를 포함할 수 있으므로 비공개로 관리하세요. 기존 검색 조건만 브라우저 저장을 사용합니다. 실제 계좌 자료·인증정보·인포맥스 원자료를 회사→집, Wiki, Git 또는 클라우드로 자동 옮기지 않습니다.

이 HTML은 외부 API/LLM 요청을 하지 않습니다. 사용자가 출처 링크를 누르면 해당 사이트가 열리는 것은 별개입니다. 자료 이용 조건과 회사 정책은 사용자의 허용 범위 안에서 별도 확인해야 합니다.

## 실제 프로젝트에 적용

`CODEX_APPLY_v05.txt`와 `INVESTMENT_META_PROMPT_v05.md`를 기존 INVESTMENT 작업공간에 전달합니다. 이미 Streamlit/다른 프레임워크로 개발된 운영본이 있다면 이 HTML로 덮어쓰지 말고 참조 엔진·테스트를 이식해야 합니다. 실제 시세·공시·검토 근거 어댑터, 현재 대비 비중 비교, 적합한 운용 설정을 구현·검증한 뒤 실사용으로 구분하세요.

외부 참고: FINRA 집중위험 안내 https://www.finra.org/investors/insights/concentration-risk (2026-09-27 접근). 위 모형의 숫자/임계값을 검증해주는 자료는 아닙니다.
