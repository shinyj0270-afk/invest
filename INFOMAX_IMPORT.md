# 인포맥스 파일을 대시보드에 연결하기

버전: `infomax-file-0.1` / 2026-09-28

1333 Excel Download에서 저장한 다섯 파일을 로컬 Python 변환기로 읽고, 기존 HTML의 **데이터 JSON 불러오기**로 가져오는 기능이다. CSV와 XLSX를 지원한다. 계정 로그인, 인포맥스 함수 실행, 파일 업로드, 예약 갱신은 하지 않는다.

## 바로 화면을 확인하기

`INVESTMENT_Dashboard.html`을 열고 상단 JSON 불러오기에서 `examples/infomax_snapshot_fixture.json`을 선택한다. **가상 테스트 자료** 표시와 세 가상 기업의 지표가 나온다. 기업분석 아래에 자료가 부족한 이유도 표시된다. 이 파일에는 실제 회사의 관측값이 없다.

동일한 가상 입력과 결과를 새 폴더에서 재생성하려면 프로젝트 폴더에서 실행한다.

```powershell
python -X utf8 tools/infomax_demo.py --output-dir private_data/demo-new
```

생성된 `private_data/demo-new/snapshot.json`을 같은 방법으로 가져온다. 이미 있는 폴더는 덮어쓰지 않는다. 이 데모의 날짜와 거래소 표기는 시험용 가정이며 공식 거래 달력의 증거가 아니다.

## 실제 입력 파일 준비

앞선 회사 PC 조회는 `INFOMAX_SAMPLE_VALIDATION.md`에 기록했다. 임시 Excel 문서를 종료하기 전 필요한 파일을 회사 PC의 `private_data/infomax/`에 별도로 저장한다. 현재 대화에서 실제 시세 파일을 저장하거나 대시보드에 넣은 것은 아니다.

| 파일 예시 | 해당 시험 창 | 필요한 항목 |
|---|---|---|
| prices.xlsx | 통합 문서1 | 일자, 현재가, 누적거래량, 누적거래대금 |
| flows.xlsx | 통합 문서2 | 일자, 기관순매수금액, 외국인순매수금액 |
| balance.xlsx | 통합 문서4 | 일자, 자산, 자본, 부채. 연결·누적 |
| income.xlsx | 통합 문서5 | 일자, 매출액(영업수익), 영업이익, 당기순이익(포괄손익계산서). 연결·순 |
| info.xlsx | 통합 문서6 | 종목명, 구분, 코드, 단축코드, 소속시장구분, 업종코드, 시가총액 |

통합 문서3은 잔액에 순 옵션을 적용한 비교용이므로 사용하지 않는다. 수정가는 별도로 반환을 검증했지만 이번 어댑터의 지표 계산에는 사용하지 않는다.

- 히스토리 파일의 1행은 조건, 2행은 종목명, 3행은 항목명, 4행부터 값이다. 세로·내림차순·각 종목 날짜·거래일 0·시세산출 종가의 검증된 배치를 유지한다.
- 다섯 파일의 종목 집합과 이름이 같아야 한다. 이름이 중복되면 자동 연결을 거부한다. 샘플용으로 100종목 이하를 지원한다.
- XLSX는 Excel이 마지막으로 저장한 계산 결과를 읽는다. Python이 IMDH/IMDP를 계산하거나 갱신하지 않는다. 값이 없는 경우 Excel에서 계산 완료를 확인하고, 필요한 경우 별도 사본을 값으로 붙여넣어 저장한다. 종목명이 들어가는 함수 셀의 캐시도 필요하다.
- CSV는 UTF-8 BOM 또는 CP949를 읽는다. 코드를 `005930`처럼 6자리로 유지한다. 코드가 `5930`으로 바뀌면 임의 보정하지 않고 오류로 처리한다.
- 좁은 열을 화면에서 복사해 `####` 또는 반올림된 지수 문자열로 만든 파일은 피한다. XLSX 숫자 셀은 표시 문자열이 아닌 저장된 숫자로 읽는다.
- 하나의 시트가 있는 파일을 권장한다. 여러 시트면 다섯 파일에 공통으로 사용할 `--sheet Sheet1`을 지정한다. 서로 다른 시트명은 현재 CLI에서 지원하지 않는다.

XLSX 읽기는 [openpyxl 공식 문서의 read_only/data_only](https://openpyxl.readthedocs.io/en/stable/api/openpyxl.reader.excel.html) 방식이다. Excel에 저장된 값의 최신성을 보장하는 옵션은 아니다. CSV는 외부 패키지 없이 동작하고, XLSX는 `requirements-import.txt`가 필요하다.

## 기준 설정

`config/infomax.example.json`을 `private_data/infomax/config.json`으로 복사하고 입력 파일의 실제 기준을 기록한다. 예시는 미확인 설정을 null/false/unknown으로 두었으며, 그대로 실행하면 필요한 날짜 설정을 안내한다.

| 설정 | 입력할 내용 |
|---|---|
| `mode` | 실제 입력은 `user_input`. 가상 자료에만 `fixture` |
| `as_of` | 자료를 평가하는 YYYY-MM-DD |
| `completed_through` | 수집 완료가 확인된 최종 거래일 |
| `sessions_20d` | 그 날짜까지 연속된 실제 20거래일을 오름차순으로 명시. 주말만 빼서 추정하지 않음 |
| `prices_final`, `flows_final` | 해당 20거래일 자료의 확정 여부. 확인되지 않았으면 false 유지 |
| `price_venue`, `flow_venue` | 확인된 KRX / NXT / KRX+NXT, 모르면 null |
| `market_cap_date` | 기본정보의 시가총액 관측일. 완료 가격일과 다르면 지표를 비움 |
| `financial_period` | 사용할 분기 말일. 예: 2026-06-30 |
| `financial_basis` | 이번 구현은 연결 CFS만 지원 |
| `balance_comp`, `income_comp` | 누적 / 순. 실제 조회한 설정과 맞춰야 함 |
| `units` | 검증된 원/천원 필드 정의. 임의로 수정하지 않음 |
| `companies` | 파일의 코드별 주식종류, 금융/비금융, 해당 분기 자료의 실제 이용 가능일 |

`financial_available_on`은 **분기 말일이 아닌 공개되어 이용 가능해진 날**이다. 모르면 null로 남기고 재무비율 계산을 보류한다. 보고기간 이전 또는 평가일 이후의 공개일은 오류다. 이 필드는 사용자 확인 정보이며 공급자 공시 원문을 자동 검증한 증거가 아니다. 실제 과거 빈티지를 수집하지 않았으므로 백테스트용 시점 검증은 완료되지 않았다.

`security_type`은 ordinary/preferred/unknown, `analysis_profile`은 nonfinancial/financial/unknown이다. 미확인 기업은 자료에서 지우지 않고 일반 스크리너 대상에서 제외한다.

## 변환 실행

CSV만 사용할 때는 Python 표준 라이브러리로 실행할 수 있다. XLSX용 환경은 다음과 같이 프로젝트 가상환경에 준비할 수 있다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-import.txt
```

실제 파일을 준비한 뒤 실행할 명령:

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/infomax_import.py `
  --config private_data/infomax/config.json `
  --info private_data/infomax/info.xlsx `
  --prices private_data/infomax/prices.xlsx `
  --flows private_data/infomax/flows.xlsx `
  --balance private_data/infomax/balance.xlsx `
  --income private_data/infomax/income.xlsx `
  --output private_data/infomax/snapshot-01.json
```

새 출력 이름을 사용한다. 변환 도중 오류가 나면 새 스냅샷을 발행하지 않으며 이전 파일을 덮어쓰지 않는다. 성공한 JSON을 HTML에서 가져온다. 입력·원자료·결과 JSON의 자동 업로드나 PC 간 복사는 없다.

## 계산 범위

- 시가총액: 원 ÷ 100,000,000 → 억원. 완료 가격일과 관측일 일치 및 가격 확정 설정 필요.
- 20일 평균 거래대금: 정확히 지정한 20거래일 원 금액 합계 ÷ 20 ÷ 100,000,000.
- 외국인/기관 순매수: 천원 × 1,000 → 원으로 통일한 후 20일 합계 → 억원. 음수와 0을 보존한다.
- 순매수/거래대금: 같은 20거래일·같은 거래소 범위·양수 분모일 때만 계산한다.
- 영업이익률: 대상 연결 단독분기 영업이익 ÷ 양수 매출 × 100.
- 부채비율: 대상 연결 잔액 부채 ÷ 양수 자본 × 100. 자산/자본/부채가 모두 있으면 원정밀도 기준의 대차 검사를 수행한다.
- 매출증가율, ROE, 순차입금/자본, 이자보상배율, 유동비율은 필요한 비교기간·지배주주 항목·원계정이 부족해 null로 남긴다. 분기 4개를 연간 이력 행으로 바꾸지 않는다.

빈 수급을 0으로 바꾸거나, 빈 날짜를 제외한 앞선 20개 관측으로 계산 기간을 몰래 늘리지 않는다. 미래 행은 오류, 완료 거래일 이후이되 평가일 이내인 장중 행은 기간 계산에서 제외한다. 파일 해시, 설정 해시, 제외 행 수, 지표별 부족 사유를 결과에 남긴다.

## 검증 상태

가상 입력 기반 변환·계약·브라우저 시험은 `tests/test_infomax_import.py`, `tests/test_infomax_ui.cjs`로 수행한다. 실제 인포맥스 파일의 저장 캐시·이용 범위·교차 출처 대사는 미검증이다. 앞선 3종목 화면 조회 성공과 파일 어댑터의 가상 테스트 성공을 구분한다.

회사 PC에서는 제공된 Python 런타임의 openpyxl 3.1.5와 Node Playwright, 설치된 Edge로 검증했다. 기존 Python UI 테스트 전체는 Playwright Python 미설치로 이번에도 실행하지 않았다. 집 PC에서는 CSV 변환과 계산 테스트부터 재실행하고 XLSX/브라우저 의존성은 그 PC에 맞춰 준비한다.
