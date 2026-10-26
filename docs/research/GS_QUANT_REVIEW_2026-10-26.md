# GS Quant 대시보드 적용 검토 — 2026-10-26

작성: Codex. 범위: 공식 저장소·공식 소스의 정적 검토와 기존 INVESTMENT 기능 대조. 패키지 설치·코드 실행·DB 등록·대시보드 변경은 하지 않았다. 적용 효과와 우선순위는 아래에서 **설계 제안/추론**으로 구분한다.

## 판단

**선택적으로 참고할 내용이 있다. 전체 GS Quant를 운영 의존성으로 추가할 필요성은 현재 확인되지 않았다.** 가장 유용한 후보는 기존 위험 분석의 교체가 아니라 **상관관계·베타의 시간 변화**, **가설별 사전 정의 관찰 성과**다. 기존 대시보드의 누적 가격수익·20일 변동성·낙폭·상관행렬을 새 기능처럼 중복 추가하지 않는다.

공식 README는 GS Quant를 파생상품·거래전략·위험관리 및 통계 분석용 도구로 설명한다. API는 기관 고객에게 제공되는 client id/secret이 필요하다. 따라서 공개 Python 코드 이용과 Goldman Sachs 데이터·가격평가 API 이용을 구분한다. [공식 README](https://github.com/goldmansachs/gs-quant/blob/bbe7071653ccfc0d431e11c3a31dbd511afc394f/README.md)

## 조사 기준

- 2026-10-26 GitHub API로 `master`의 실제 SHA **`bbe7071653ccfc0d431e11c3a31dbd511afc394f`**를 확인했다. 아래 소스 링크는 이 SHA에 고정했다. [조회 대상 커밋](https://github.com/goldmansachs/gs-quant/commit/bbe7071653ccfc0d431e11c3a31dbd511afc394f)
- 로컬 비교 기준은 [포트폴리오 위험 계약](../PORTFOLIO_RISK.md), [구성 변경 위험 검토 계약](../RISK_REVIEW_AND_FISCAL_CONTRACT.md) 및 현재 코드에 대한 읽기 점검이다. 이 문서는 실데이터 성과 또는 런타임 호환성을 검증한 결과가 아니다.
- 라이선스는 Apache-2.0이다. 소스 복사·수정·재배포를 선택하면 해당 라이선스와 NOTICE 적용 여부를 구현 시 확인한다. 자체 산식 구현과 라이브러리 설치는 별도 선택이다. [LICENSE](https://github.com/goldmansachs/gs-quant/blob/bbe7071653ccfc0d431e11c3a31dbd511afc394f/LICENSE), [NOTICE](https://github.com/goldmansachs/gs-quant/blob/bbe7071653ccfc0d431e11c3a31dbd511afc394f/NOTICE)

## 로컬 계산과 API의 경계

| 기능 | 공식 소스에서 확인한 사실 | INVESTMENT 적용 판단 |
|---|---|---|
| 실현 변동성 | `volatility`는 가격/수익률 Series, 창 길이, 연율화 계수를 받아 로컬 계산한다. 출력 20은 20%이며 기본 표본 표준편차를 쓴다. | 기존 20일 변동성과 중복. 신규 설치 근거로 삼지 않는다. |
| 이동 상관 | `correlation`은 두 Series의 수익률, 같은 날짜 관측으로 이동 상관을 계산한다. 중복 날짜 제거·결측 제외 처리가 포함된다. | 기존 정적 상관표에 시간 변화 관찰을 덧붙이는 참고 구현 후보. |
| 이동 베타 | `beta`는 종목과 벤치마크 가격/수익률로 이동 공분산/분산을 계산한다. 초기 3개 값은 결측으로 만든다. | 시장 민감도 변화를 보여주는 신규 후보. 기존 종목별 위험 기여도와 다른 의미다. |
| 정규화·낙폭 | `index`는 첫 유효 관측 대비 정규화, `max_drawdown`은 음수 비율의 Series를 반환한다. | 기존 누적수익·MDD와 중복. 단위·창 정의 비교용으로만 참고. |
| 초과수익 | `excess_returns_pure`는 두 로컬 Series를 받고, `excess_returns`의 통화/Asset 경로는 `GsDataApi`를 호출한다. | 기존 누적수익 차이(%p)와 정의가 다르다. 이름이 같아도 대체하지 않는다. |
| Sharpe | `sharpe_ratio` 기본 가격/통화 경로는 무위험 벤치마크 조회로 이어진다. 이미 초과수익인 입력 경로 또는 별도 순수 함수는 구분해야 한다. | 단순 Series 입력만으로 모든 Sharpe 경로가 오프라인이라고 설명하지 않는다. 국내 무위험금리·현금 처리 정의도 선행 필요. |

위 표의 함수·계산 경로는 [econometrics.py](https://github.com/goldmansachs/gs-quant/blob/bbe7071653ccfc0d431e11c3a31dbd511afc394f/gs_quant/timeseries/econometrics.py), 순수/세션 함수 표시와 창 처리는 [helper.py](https://github.com/goldmansachs/gs-quant/blob/bbe7071653ccfc0d431e11c3a31dbd511afc394f/gs_quant/timeseries/helper.py)에서 확인했다. 이 특정 로컬 산식에 API 호출이 없다는 소스 판단이며, 패키지 설치·import·전체 기능의 무인증 동작을 실행 검증했다는 뜻은 아니다.

### 가져올 때 유지할 계산 계약

1. **준비 구간**: GS Quant의 정수 창 `w`는 기본적으로 `Window(w, w)`로 정규화되어 앞 `w`개를 제거한다. 현 대시보드의 20개 수익률 확보·초기 19개 수익률 결측과 출력 시작점이 자동으로 일치하지 않는다. 신규 지표는 최소 유효 관측 수와 최초 표시일을 명시한다. [helper.py](https://github.com/goldmansachs/gs-quant/blob/bbe7071653ccfc0d431e11c3a31dbd511afc394f/gs_quant/timeseries/helper.py)
2. **날짜·결측**: GS 상관함수의 중복 날짜 첫 행 보존·결측 제거를 그대로 옮기면 현재 프로젝트의 날짜 누락/중복 오류를 드러내는 계약이 약해질 수 있다. INVESTMENT의 완료 종가·수정 기준·공통 거래일 검사를 먼저 적용하고, 오류를 교집합·보간·0으로 숨기지 않는다. [econometrics.py](https://github.com/goldmansachs/gs-quant/blob/bbe7071653ccfc0d431e11c3a31dbd511afc394f/gs_quant/timeseries/econometrics.py), [로컬 계약](../PORTFOLIO_RISK.md)
3. **단위**: GS 변동성은 % 단위, MDD는 비율(예: -0.2)이다. 로컬 UI의 %·%p와 명시적으로 변환해야 한다. `max_drawdown`의 창 안 이동 최고값·이동 최솟값 조합을 엄밀한 단일 후행창 MDD 또는 전체 관측 고점 낙폭과 무조건 같은 지표로 취급하지 않는다. [econometrics.py](https://github.com/goldmansachs/gs-quant/blob/bbe7071653ccfc0d431e11c3a31dbd511afc394f/gs_quant/timeseries/econometrics.py)
4. **초과수익**: `excess_returns_pure`는 매 관측의 두 가격 변화 차이를 재귀적으로 누적한다. 현재 로컬 지표는 동일 시작점의 누적 가격수익률 두 값의 차이(%p)다. 비교 화면에 산식을 함께 보이지 않는 대체는 하지 않는다. [GS 산식](https://github.com/goldmansachs/gs-quant/blob/bbe7071653ccfc0d431e11c3a31dbd511afc394f/gs_quant/timeseries/econometrics.py), [로컬 산식](../PORTFOLIO_RISK.md)

## 적용 우선순위 — 설계 제안/추론

| 순서 | 제안 | 기존 기능과 차이 | 선행 조건·완료 기준 |
|---|---|---|---|
| 1 | 63/126거래일 이동 베타·상관 | 정적 상관표에서 보이지 않는 종목-시장 및 종목 간 위험 동조화 변화 | 기존 검증 가격 재사용, 최소 관측 수·평가일·벤치마크·분산 0 처리 표시. 동일/역상관·공백·미래자료 배제·창 경계 독립 산식 검사. |
| 2 | Research Library 가설별 사전 관찰 성과 | `THESIS-20261026-01/02` 등 연구 질문의 이후 결과를 원래 가설·당시 근거와 연결 | 기존 immutable checkpoint/전후비교를 재사용할 수 있는지 확인. 가설 시점·후보군·비교지수·3/6/12개월에 대응하는 63/126/252거래일 관찰(정확한 평가일 규칙 사전 고정)·반증 조건을 미리 고정하고, 뒤늦게 바꾼 기준을 과거에 적용하지 않음. |
| 3 | 기존 시장·업종 화면에 위험 상태 변화 결합 | 현재 breadth·자체 국면·업종 수익률을 새로 만드는 작업이 아니다. 이동 베타·상관 변화를 곁에 표시하는 확장 | 국면별 과거 성과와 표본 수를 확인하기 전 위험회피/매수 지시로 승격하지 않음. |
| 4 | 업종 성과의 분모·가중방식 비교 | 현재 시총 가중 업종 수익·개별주 백분위에 균등가중/중앙값/상위3 기여를 대조 | 당시 구성종목·시총 분모를 확보할 수 있는지 우선 확인. 현재 구성으로 과거를 재현하면 생존편향·미래정보 가능성을 표시. GS가 국내 업종 PIT 데이터를 제공한다고 추정하지 않음. |

1번은 GS의 이동 산식에 직접 근거한 적용 제안이다. 2~4번은 GS의 시계열·전략 평가 구조와 현재 대시보드의 연구 기능을 연결한 **자체 설계 추론**이며 GS Quant가 Research Library 가설 검증·한국 업종 데이터·검증된 투자 신호를 제공한다는 주장이 아니다. 전략 평가 객체가 별도로 있다는 근거: [strategy.py](https://github.com/goldmansachs/gs-quant/blob/bbe7071653ccfc0d431e11c3a31dbd511afc394f/gs_quant/backtests/strategy.py), [backtest_objects.py](https://github.com/goldmansachs/gs-quant/blob/bbe7071653ccfc0d431e11c3a31dbd511afc394f/gs_quant/backtests/backtest_objects.py).

베타는 시장과의 과거 동행 민감도이고, 낮은 베타가 손실 방지·고평가 해소·기업 고유위험 제거를 보장하지 않는다. 새 지표는 현 프로젝트의 최대5종목·종목당40%·현금최소5% 사용자 한도를 변경하거나 자동매매·주문·잔고조회로 연결하는 근거가 아니다. [현재 구성 계약](../PORTFOLIO_RISK.md)

## 백테스트는 무엇까지 오프라인인가

`GenericDataSource`와 `DataManager.add_data_source`는 로컬 `pd.Series`를 받을 수 있다. `PredefinedAssetEngine`에는 시뮬레이션 실행 엔진이 있다. 반면 `GsDataSource`는 `Dataset.get_data`를 호출한다. [data_sources.py](https://github.com/goldmansachs/gs-quant/blob/bbe7071653ccfc0d431e11c3a31dbd511afc394f/gs_quant/backtests/data_sources.py), [predefined_asset_engine.py](https://github.com/goldmansachs/gs-quant/blob/bbe7071653ccfc0d431e11c3a31dbd511afc394f/gs_quant/backtests/predefined_asset_engine.py)

이로부터 백테스트 전체가 무인증이라고 결론 내릴 수 없다. 공식 테스트는 날짜함수에 GsSession이 필요하다는 이유로 `is_business_day`와 `business_day_offset`을 mock 처리한다. `GenericEngine`은 `PricingContext`·`HistoricalPricingContext`를 사용한다. **따라서 로컬 가격을 넣는 간단 전략도 달력·상품 해석·가격평가 경로를 확인해야 하며, 현재 연구가설 관찰에는 검증된 로컬 달력과 가격을 사용하는 작은 평가 모듈을 먼저 설계하는 편이 적합하다는 추론이다.** [공식 테스트](https://github.com/goldmansachs/gs-quant/blob/bbe7071653ccfc0d431e11c3a31dbd511afc394f/gs_quant/test/backtest/test_backtest_predefined.py), [generic_engine.py](https://github.com/goldmansachs/gs-quant/blob/bbe7071653ccfc0d431e11c3a31dbd511afc394f/gs_quant/backtests/generic_engine.py)

후보군·리밸런싱 시점·체결 시차·비용·배당·상장폐지·당시 데이터 가용시점을 고정하기 전에는 연구 관찰 성과를 실현 가능한 전략 수익률이라고 표시하지 않는다. 이는 이번 검토의 설계 경계이며 GS 실행 결과가 아니다.

## 설치·운영 비용과 미확인

공식 `pyproject.toml`은 Python>=3.10과 기본 의존성 **24개**를 선언한다. numpy>1.17.0, pandas>=1.4, scipy>=1.2.0, statsmodels>=0.14.5 외에 lmfit, HTTP 클라이언트, OpenTelemetry 등이 포함된다. notebook extra에는 Jupyter·matplotlib·seaborn·treelib가 추가된다. 저장소 `requirements.txt`는 본 패키지와 `gs_quant[notebook]`을 지정하므로 단순 운영 설치에 그대로 쓰면 불필요한 notebook 계열을 포함할 수 있다. [pyproject.toml](https://github.com/goldmansachs/gs-quant/blob/bbe7071653ccfc0d431e11c3a31dbd511afc394f/pyproject.toml), [requirements.txt](https://github.com/goldmansachs/gs-quant/blob/bbe7071653ccfc0d431e11c3a31dbd511afc394f/requirements.txt)

현재 INVESTMENT의 pandas 3.0.6·numpy 2.5.3 고정 환경에서 import·수치·회귀 동작은 이번에 실행하지 않았다. 넓은 하한 버전 선언만으로 해당 조합의 호환을 보증할 수 없다. 저장소의 uv 설정에는 GS 내부 패키지 인덱스도 있으므로 프로젝트 환경에 설정을 복사하지 않는다. [pyproject.toml](https://github.com/goldmansachs/gs-quant/blob/bbe7071653ccfc0d431e11c3a31dbd511afc394f/pyproject.toml)

공개 코드 라이선스와 기관 API 접근권은 별개다. 공개 README만으로 API 이용료·계약조건·국내 종목 데이터 이용권을 확정할 수 없다. 실제 비용·권한은 미확인으로 두며, 현 검토에는 GS 인증정보나 유료 데이터가 필요하지 않았다. [README](https://github.com/goldmansachs/gs-quant/blob/bbe7071653ccfc0d431e11c3a31dbd511afc394f/README.md)

## 이번 검토의 다음 실행점

**설계 제안**: 기존 추세/Advanced 분석 구역에서 63일 이동 베타·상관을 우선 검토한다. 입력 검증과 날짜 계약을 보존한 작은 로컬 산식으로 구현하고, 지표가 기존 정적 분석을 보완하는지 확인한 뒤 가설별 사전 관찰 성과로 확장한다. GS Quant 설치, Marquee 연결, DB 변경, 대시보드 구현 및 Git 전송은 이번 읽기 검토에 포함하지 않았다.

## 후속 구현 · 2026-10-26

사용자 “다 적용해줘”에 따라 이동통계·업종분해·가설 후속관찰을 기존 로컬 산식으로 구현했다. 위 미실행 문구는 조사 당시 이력이다. 실제 계약·시험은 [QUANT_EXTENSIONS](../QUANT_EXTENSIONS.md), 실행/배포/전송 근거는 PROJECT_STATE와 CURRENT_HANDOFF를 따른다. GS Quant 패키지는 설치하지 않았다.
