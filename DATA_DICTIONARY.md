# 데이터 계약 · work12

기존 schema_version 0.1 스냅샷과 인포맥스 지표는 보존한다. 새 Python 앱은 이 계약에 아래 선택 원계정을 추가한다. 저장 스냅샷마다 SHA256 식별자·모드·기준일·회계 기준을 갖는다. 실데이터와 fixture는 DB 경로부터 분리한다.

|입력|필수 의미|부족할 때|
|---|---|---|
|quarters|period_end, available_at, basis; revenue/op/parent_income는 원 단위 단독분기|연속 4/13분기 부족 시 TTM/교차 N/A|
|annual|연말, 이용가능일, CFS/OFS; 원 단위 매출/이익/OCF/CAPEX/자본/부채/현금|완료연도 공백·CAPEX 미확인·분모 0은 N/A|
|effective_tax_rate|0~1 실효세율, tax_verified=true일 때만 ROIC 프록시|추정세율 자동 대입 없음|
|dps / dps_basis|현금 DPS 원/주, 동일 주식종류·분할조정 기준; special_dividend 별도|0→양수는 배당 개시, 무한 CAGR 금지|
|prices|date, 조정 close/high/low 원, volume 주, turnover 원, venue, adjustment_basis|253일/벤치마크·동일 거래일 부족 시 추세 N/A|
|flows|date, foreign_net_won/institution_net_won 원, venue, final|5/60일 새 산식은 완전 기간·확정·동일 범위 필요|
|evidence|path, document, location, summary, available_at, first_seen_at, reviewed_at, review_status|수치 신호와 독립. 미래 관측/검토 근거는 후보 확정에 미사용|
|stages|단계·관측 상태·근거·available_at/first_seen_at|입력된 상태만 표시. 자동 승급 없음|
|valuation_basis|검증 EPS/PER 주식종류·조정·기간 기준|상대가치 시나리오 대기|

수집 응답은 staging에만 저장한다. OpenDART의 IS 3개월 금액과 CF 누적 금액을 구별하고 모호한 account_id는 추정 매핑하지 않는다. 정정은 period_end+basis별 이용가능일을 기준으로 선택한다. available_at 미확보 자료를 PIT 백테스트로 사용하지 않는다.

인포맥스의 기존 20개 관측일 잠정 사용 예외는 USER_DATA_DECISIONS.md에만 정의하며 다른 공급자/새 기간에 자동 확장하지 않는다. 주요 원자료 메타데이터(출처·접수번호·수집시각·단위·통화·조정 기준)는 신규 실응답 정규화 단계에서 확인해야 한다.

---

# 기존 보유·포트폴리오 데이터 계약

## 시장 스냅샷 파일 어댑터 추가 (2026-09-28)

별도 시장 계약 `snapshot.schema.json` 0.1을 유지하며 `tools/infomax_import.py`가 1333 파일을 변환한다. 아래 보유·연구 계약으로 자동 전환하지 않는다. 입력 형식·단위·산식·미지원 항목은 `INFOMAX_IMPORT.md`를 참조한다.

- `meta.data_mode`: fixture/user_input. 가상 자료는 화면에 명시한다.
- `meta.adapter_version`, `config_sha256`, `source_files`: 변환 버전과 재현용 해시. 해시는 원문 진본이나 이용 권한을 인증하지 않는다.
- `meta.import_audit`: 종목별 원자료 행 수, 완료 거래일 이후 제외 행 수, 설정된 재무 공개일, 계산된 지표 수.
- `meta.price_venue`, `flow_venue`: 가격과 수급 범위를 따로 보존한다. 다르면 비율 계산을 보류한다.
- 기업별 `data_quality`: 최대 30개 설명 문자열. `metric_missing_reasons`: 지표별 결측 사유 객체. 숫자가 없다는 뜻을 0으로 대체하지 않는다.
- 원자료 재무 보고기간을 그대로 공시 공개일로 채우지 않는다. 매출/영업이익 등 분기 데이터로 연간 history를 만들지 않는다. 연구 판단·매수/매도 의견·보유수량을 생성하지 않는다.

버전: `holdings-portfolio-0.1`, 엔진 `0.2.0`, 2026-09-27.

이 계약은 사용자/기존 리서치 모듈이 검토한 상태를 HTML에 전달하는 형식입니다. 원자료 공시에서 상태를 생성하는 자동 분석기는 이번 HTML에 없습니다. `evidence.reviewed=true`는 **입력자가 확인했다고 표기한 상태**이며 이 프로그램이 문서를 읽고 검증했다는 뜻이 아닙니다.

## 최상위

| 필드 | 형식 | 의미 |
|---|---|---|
| `schema_version` | 고정 문자열 | `holdings-portfolio-0.1` |
| `mode` | `fixture` / `user_input` | 실시간 모드 없음 |
| `as_of` | YYYY-MM-DD | 판정을 위한 명시적 기준일, 생성 시각과 다름 |
| `snapshot_id` | 비어 있지 않은 문자열 | 입력 스냅샷 식별자 |
| `cash_krw` | 0 이상 유한 숫자 / null | 전략 범위 현금; null은 모름 |
| `holdings` | 배열, 최대 500행 | 보유 종목 |
| `research` | 배열, 최대 3,000행 | 보유/관심 후보의 검토 입력 |

금액은 원 단위입니다. 키·계좌번호·비밀번호 등 계약에 없는 민감정보를 넣지 마세요. 원자료의 통화 변환·수정주가·기업행위 정합성은 별도로 확인해야 합니다. API 원문 JSON을 그대로 가져오는 형식이 아닙니다.

## holdings

| 필드 | 형식 | 의미 |
|---|---|---|
| `code` | 정확히 6자리 문자열 | 선행 0 보존, 중복 금지 |
| `quantity` | 양의 안전한 정수 | 현재 수량 |
| `avg_cost_krw` | 0 이상 유한 숫자 / null | 원가, 기업 의견에 사용하지 않음 |
| `thesis_note` | 선택, 최대 4,000자 | 사용자의 투자 이유 메모 |

현재 보유목록이 전체 계좌/전체 자산을 나타낸다고 가정하지 않습니다. 가격이나 현금이 부족하면 전체 평가액/비중을 비워 둡니다. 매입가 0 또는 null에서는 손익률을 계산하지 않습니다. 손익은 세금/수수료/배당 미반영입니다.

## research

| 필드 | 형식 | 의미 |
|---|---|---|
| `code` | 6자리 문자열, 중복 금지 | holdings와 연결 |
| `issuer_id` | 문자열 | 같은 회사의 여러 주식 종류를 식별 |
| `name` | 문자열 | 기업명 |
| `market` | 문자열 | 적격 시장 KOSPI/KOSDAQ |
| `security_type` | 문자열 | 초기 적격 유형 ordinary |
| `analysis_profile` | 문자열 | 초기 적격 유형 nonfinancial |
| `sector`, `risk_group` | 문자열 / null | 검토한 산업·공통위험 분류 |
| `price_krw` | 양수 / null | 현재가 입력; 0은 오류 |
| `price_date` | 날짜 / null | 가격 관측일 |
| `price_source` | `{label,url}` / null | 가격 출처 |
| `review` | 아래 객체 | 입력자가 검토한 분석 상태 |
| `evidence` | 아래 배열, 최대 30개 | 근거 메타데이터 |

다른 기업 유형은 삭제하지 않고 별도 분석 필요로 둡니다. 산업명이나 공통위험군이 없는 기업은 새 포트폴리오에서 제외/자료 대기 처리합니다. 위험군 분류는 상관계수 추정 결과가 아닙니다.

### review

```text
thesis: intact | weakened | broken | unknown
business: improving | stable | deteriorating | unknown
finance: sound | concern | critical | unknown
valuation: attractive | fair | stretched | unknown
material_risk: clear | unresolved | confirmed | unknown
reviewed_on: YYYY-MM-DD | null
financial_period: 보고기간을 나타내는 문자열 (가격일과 구별)
positives: 비어 있지 않은 근거 문장 배열, 최대 12개
negatives: 반대 근거 문장 배열, 최대 12개
invalidation: 판단을 바꿀 조건, 문자열
next_review_on: YYYY-MM-DD | null (알림 등록이 아님)
```

각 근거 문장 최대 2,000자, 변경 조건 최대 4,000자입니다. 단순히 형식을 채우려고 가상의 사업 사실을 적으면 안 됩니다. 정보가 모르면 unknown/빈 배열로 입력하고 판단을 보류하세요. 원문과 주요 주장별 evidence ID 연결은 v0.5 통합 단계의 추가 요구입니다.

### evidence

```text
id: 같은 기업 안에서 중복 없는 식별자
label: 근거 문서 이름
url: 유효한 http(s) 주소 (계정/비밀번호가 포함된 URL 금지)
available_on: 평가 시점에 실제 이용 가능해진 날짜
reviewed: 입력자가 원문 대조 여부를 표기한 boolean
```

평가일 이후 공개된 근거, 확인하지 않은 근거, 근거 공개 전의 검토일은 판정을 차단합니다. 현재 버전의 원문 검증은 자동화되어 있지 않습니다. `example.invalid` 주소는 가상 예제 전용이며 실재 출처로 취급하지 않습니다.

## 판정 규칙

기본적으로 모든 필수 상태가 확인되어야 합니다. 검토일/가격 한도는 개발 예시(120/4 달력일)로 설정 가능하며 실제 거래 달력 기반 최신성은 운영 통합에서 검증해야 합니다.

- 근거가 검토된 broken / critical / confirmed 중대 사건은 매도 검토. 다른 가격·찬성 근거 누락은 별도 경고로 표시하되 해당 중대 사건을 숨기지 않습니다.
- 필수 근거·가격·상태가 부족하거나 미래/기한 초과이면 판단 보류.
- weakened / deteriorating / concern / unresolved는 재검토.
- 나머지가 충족하고 가치평가 stretched는 비중 축소 검토.
- 나머지가 충족하고 논리 유지·사업 안정/개선·재무 양호·가치평가 fair/attractive·중대 위험 clear이면 보유 검토.

이 규칙은 전문가의 현재 종목 평가를 대신하지 않습니다. 주식수·매입가·손익은 기업 의견을 결정하지 않고 비중 의견은 기업 합산 비중으로 따로 계산합니다.

## 배분 정책과 결과

`DEFAULT`의 기업 상한 25%, 산업/공통위험군 40%, 최소현금 20%, 하락 시나리오 -30%는 **개발 가정**입니다. `stressLossLimitPct`는 기본 null, `policyConfirmed`는 false입니다. 개인 적합성 검증 없이 바꾸어 사용한 숫자를 권장 투자 비중으로 설명하지 않습니다.

`maxCompanies`는 1~5. 비중은 내부 bp(0.01%) 정수로 처리합니다.

```text
주식예산bp = min(10000 - ceil(minCashPct*100), floor(10000*stressLossLimitPct/abs(stressShockPct)))
슬롯bp = floor(min(주식예산bp/maxCompanies, floor(companyCapPct*100), floor(sectorCapPct*100), floor(groupCapPct*100)))
기업비중 = 슬롯bp/100
현금비중 = 100 - 실제 편입기업비중 합계
```

적격 풀은 HOLD와 분류/근거 조건을 통과한 기업입니다. 우선순위는 attractive/fair, improving/stable, 기존 보유/신규, 종목코드 순입니다. 최대 기업 수와 기업 중복, 산업/위험군 상한을 차례로 적용하는 결정론적 휴리스틱입니다. 점수의 확률 보정이나 기대수익 최적화는 하지 않습니다.

결과 상태:

| 상태 | 의미 |
|---|---|
| `DATA_REQUIRED` | 후보가 없거나 후보 전반에 필수 정보가 부족해 0편입/현금 의견조차 산출하지 않음 |
| `SETTINGS_REQUIRED` | 시나리오 손실 기준·정책 확인 대기 |
| `MODEL_PROPOSAL` | 조건을 충족하는 1~5개 기업의 모의 목표안 |
| `CASH_ONLY` | 충분한 판정 또는 비중 설정에 따라 편입 비중 0; 강제 매도 지시 아님 |

후보가 2개라면 N=5 기준 3개 슬롯은 현금으로 남습니다. 연구 입력의 후보 집합 안에서만 선택하며 전 시장 최적선정이라고 주장하지 않습니다. 미편입 기존 보유는 변경하지 않습니다. 실제 포트폴리오를 이 비중으로 전환하는 비용·수량·시점 계산은 미구현입니다.

## 상충·해석 유의

연구 검토일은 공시일 이상, 평가일 이하이어야 합니다. 가격일과 재무 보고기간을 같은 날짜로 만들지 않습니다. 예제 평가일은 고정된 과거 날짜이며 오늘의 의견이 아닙니다. 실제로 미래의 데이터를 확보했다는 주장을 입력만으로 검증하지는 못합니다.

현재 참조 구현은 최종 리포트의 영구 기록/설정 해시/문서별 증거 대조를 자동 저장하지 않습니다. 운영 통합에서 v0.5의 스냅샷·설정·버전 계약을 구현해야 합니다. HTML은 근거와 입력을 보존해 명시적 JSON/MD 내보내기를 제공합니다.
