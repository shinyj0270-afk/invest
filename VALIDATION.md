# 이번 검증 · work14 · 2026-09-28

이번 실행 `tools/verify_all.py` 통합 12명령 성공, Python 92개. `tests/verify_live_app.py` 실앱 8탭·조건 저장·다운로드·모바일 검증 통과. `tools/validate_share_candidates.py` 선별 41개 감지 0건, 임시 home 프로필 빌드·가상 배치·Python/JS 테스트·실제 자료 빈 상태 통과. 이 결과는 회사 PC에서 임시 home 설정으로 수행한 시험이며 실제 집 PC 검증은 아니다. 로그는 `validation/current/`, 공유 범위 판단은 [SHARE_REVIEW](docs/SHARE_REVIEW.md).

scripts/pc-finish.ps1 -RunTests로 통합 12명령 exit 0 확인. Python 89개(기존 79+신규 10), JS 84개, 기존 UI 43개 통과. 이후 AppTest 경로 분리와 예약 차단을 추가해 tests.test_dual_pc 최종 12개 재실행 통과(고유 Python 총 91). tests/verify_live_app.py 실제 브라우저 8탭·저장·내보내기·모바일 검증 통과. 가상 1개/기존 실제 3개 A4 각각 1페이지, 한글·경계 검사 통과. 실제 로컬 자료 9 XLSX·144 숫자·39 지표 재검증 통과, 신규 API 호출 없음.

명령·제한·Git 모의 검증: [DUAL_PC_VALIDATION](docs/DUAL_PC_VALIDATION.md). 이번 원시 로그: validation/current/results.json, dual-pc.txt. 외부 Git 전송/집 PC 검증은 하지 않음. 아래는 이전 실행 기록.

# VALIDATION · v0.4-work12 · 2026-09-28 Windows 실제 실행

- `tools/verify_all.py`: 로컬 가상환경에서 실행. 새 로그 `validation/current/results.json` 및 개별 로그.
- Python unittest **79개 통과**(기존 인포맥스 45개 + 연구/저장소/어댑터 33개 + Streamlit AppTest 1개).
- 기존 JavaScript 계산 **19개 + 65개 통과**.
- 기존 Python Playwright UI **13개 + 30개 검사 통과**. 과거에 미설치였던 Python Playwright를 이번 프로젝트 가상환경에 설치해 실제 실행.
- `tests/verify_live_app.py`: 실행 중인 Streamlit 8개 탭, 가상 모드 직접 선택, 조건 저장, 조건 JSON·결과 CSV·인쇄 HTML 다운로드, 모바일 폭, JS 오류 없음 통과.
- `tests/verify_report_browser.py`: 가상 기업 및 실제 SK하이닉스/현대차/삼성전자 각각 **A4 PDF 1페이지**, 한글 추출, 이름·기준일, PDF 텍스트 경계 검사 통과. PyMuPDF 렌더 이미지도 생성.
- `tools/company_finish.py`: 저장 XLSX 9개 해시 체크포인트·숫자 144개 구조 검사, 기존 39개 지표 값 재생성 통과. 원문 금액 33개는 기존 확보 원문 참조와 재대조한 것이며 신규 네트워크 원문 조회가 아님.
- 기존 Node 인포맥스 화면 검사 두 파일도 실행 통과. `test_infomax_ui.cjs` 최초 실행은 브라우저 경로 미설정으로 실패했고 `CHROMIUM_PATH`에 기존 Edge를 지정한 후 통과.
- 가상 daily/weekly 및 반복 weekly 실행 통과. 실제 저장파일을 work/user_input SQLite에 적재한 뒤 daily/weekly 실행 통과. 실제 연구 후보 0개는 장기 원계정·가격/문서 부족에 따른 정상 결과.

수정한 실패: SQLite connection context가 연결 자체를 닫지 않아 Windows 임시 DB 정리 실패 → 명시적 close 추가. AppTest 상대 경로가 tests 기준으로 해석됨 → 절대 경로 사용. Streamlit iframe 구 API 경고 → 설치 버전의 st.iframe 사용. 실제 API·수익 예측력·전 시장 완전성·회사/공급자 이용 권한은 이 테스트의 검증 범위가 아닙니다.

현재 원자료/PDF와 DB는 비공개 로컬 경로이며 소스 인계 ZIP에 포함하지 않습니다. 아래는 이전 배포 기록입니다.

---

# 이전 VALIDATION · HTML 시제품 v0.2

검증일: 2026-09-27. 사용자 PC가 아닌 격리된 Linux 컨테이너에서 검증했습니다.

## 실제 실행 결과

| 명령 | 결과 | 로그 |
|---|---|---|
| `python build.py` | 단일 HTML 생성 성공 | 생성 파일과 소스 확인 |
| `node tests/test_engine.js` | 기존 엔진 19개 통과 | tests/engine_results.txt |
| `node tests/test_portfolio.js` | 신규 엔진 65개 통과 | tests/portfolio_results.txt |
| `python tests/test_ui.py` | 기존 UI 13개 통과 | tests/legacy_ui_rerun.txt |
| `python tests/test_portfolio_ui.py` | 신규 UI 30개 통과 | tests/portfolio_ui_results.txt |

총 127개 자동 검증 항목이 이번 실행에서 통과했습니다. 모두 가상 자료 기반 기능 테스트이며 투자 성과/적중률/원문 정확성 테스트가 아닙니다. 과거 v0.1의 로그는 legacy/에 별도로 보존했습니다.

추가 수동 스크립트로 390×844 viewport의 보유 탭을 확인했고 document.scrollWidth=390, viewport=390을 관측했습니다. 이 추가 확인은 위 127개에 포함하지 않았습니다. 데스크톱/모바일 스크린샷을 열어 표·입력·경고 영역을 육안 확인했습니다. 넓은 표와 상단 탭은 모바일에서 내부 가로 스크롤을 사용합니다.

## 환경

- Linux x86_64 / glibc 2.41
- Python 3.13.5
- Node.js v22.16.0
- Playwright 1.57.0
- Chromium 144.0.7559.96 (Debian GNU/Linux 13)
- 실제 브라우저 실행 파일: /usr/bin/chromium
- 테스트의 하드코딩된 실행 경로는 CHROMIUM_PATH/탐지/Playwright 기본 경로 방식으로 변경했습니다. Windows의 해당 경로 존재 여부는 확인하지 않았습니다.

## 검증한 핵심

기존 조건검색·AND/OR·null/0·업종 모집단 계산을 재실행했습니다. 새 엔진은 입력 검증, 출처/가격/검토일 시점, 미래 자료 차단, 의견의 근거 부족, 과대 비중과 기업 의견 분리, 손익 비의존성, 최대 5개 고유 기업, 산업/위험군 상한, 현금 보존, 자료 부족과 0편입 구분, 정책 확인, 정렬 재현성과 원본 불변을 검사했습니다.

브라우저 테스트에서는 신규 탭·가상 예제 표시·근거 보기·정책 변경 시 무효화·JSON/MD 내보내기·오류 파일의 기존 상태 보존·XSS 이스케이프·입력 초기화·JavaScript 오류 없음·시험 동작 중 외부 네트워크 요청 없음·모바일 overflow 방지를 검사했습니다. 모든 가능한 취약점이나 외부 링크 클릭 후의 사이트 동작을 검증한 것은 아닙니다.

src/engine.js와 src/ui.js가 원래 v0.1 파일과 바이트 단위로 같음을 확인했습니다. v0.5 지시문의 기존 9절 장기성장 연구가 v0.4와 동일하게 보존됨을 문자열 대조했습니다.

## 수정 과정에서 발견한 문제

처음 신규 모바일 UI 검사에서 grid 최소 너비 때문에 문서가 390px viewport를 넘었습니다. minmax(0,1fr), grid 자식 min-width:0, 작은 화면의 카드 배치를 수정하고 재실행해 통과했습니다. 최종 로그는 수정 후 결과입니다.

후보 전체가 unknown인 경우를 단순 현금 100%로 해석하지 않도록 DATA_REQUIRED 분기를 보강했고 해당 회귀 테스트를 추가했습니다. 근거 공개 전의 검토일도 보류하도록 검사했습니다.

## 미검증·미구현

사용자의 실제 보유주식, 최신 시세, 실제 공시/재무 상태, 키움/OpenDART/인포맥스 인증·연동, 회사 데이터 이용 권한, 가격 기업행위 정합성, Windows/Android 실기기, 최신 로컬 앱·Streamlit 통합, 실제 수익률/백테스트, 상관계수 추정, 정확한 거래비용, 개인별 투자 적합성, 현재 보유로부터의 실제 리밸런싱은 검증하지 않았습니다.

이 HTML은 입력자가 검토한 분석 상태를 규칙에 적용합니다. 실시간 자료에서 전문가 의견을 자동 생성하는 서비스가 아닙니다. 매매 주문·계좌 잔고 자동 수집·외부 LLM 호출·예약 작업·Wiki 동기화는 구현하거나 실행하지 않았습니다.

화면 내 가상 A~H 기업과 tests/fixture_report.md는 기능 시험용이며 실제 시장 자료가 아닙니다. 입력 as_of 기준 판정이 오늘의 투자 의견을 의미하지 않습니다. 기본 비중/기한/스트레스 숫자와 휴리스틱은 예측력이 검증되지 않은 개발 가정입니다.

## 재현과 파일 확인

README.md에 재실행 명령을 수록했습니다. SHA256SUMS.txt는 배포 파일 식별용이며 금융 데이터의 진위를 보증하지 않습니다. 실제 사용자 환경에서는 기존 프로젝트 회귀 검사와 실데이터 대조를 다시 수행해야 합니다.
