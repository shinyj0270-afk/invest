# 검증된 공식 대체 원문 반영

DART 정기보고서 경로에서 표를 받지 못한 기업에 대해, 검증 완료한 투자설명서·증권신고서·감사/검토보고서의 실제 재무표를 별도로 반영한다. 원문 검증 완료는 사용자 확인 기록이며 자동 검증이나 최신 정정본 확인을 뜻하지 않는다. 회사 요약 페이지와 분할 가정·추정치는 이 경로의 입력 대상이 아니다.

## 실행

해당 PC의 설정과 저장 기업 목록이 있는 원본에서 명시적으로 실행한다. 워크트리의 개발·합성 검증에는 개인 데이터나 설정을 복사하지 않는다.

```powershell
.\.venv\Scripts\python.exe tools/import_official_statements.py <로컬-검증본.json>
```

원문 파일은 검증본 JSON과 같은 폴더에 보존한다. 입력은 `official-document-statements-1` 스키마이며 아래 계약을 따른다. 예제 구조와 합성 값은 `tests/test_official_statements.py`의 `packet()`을 참조한다. 실제 원문·수치·검증본·결과는 Git 공유에서 제외한다.

- `company`: code, name, market, corp_code. 저장 기업의 종목·이름·시장과 정확히 일치해야 한다.
- `document`: file(같은 폴더의 원문), sha256, HTTPS url, kind(prospectus/registration/audit/review), publisher_role(issuer/underwriter/exchange), legal_name, corp_code, pages, available_at, caveats. 확보한 사본의 날짜와 정정 한계를 그대로 보존한다.
- `review`: status=`user_confirmed`, reviewer, confirmed_on. 이 필드는 확인한 원문에 대한 명시적 검증 기록이다. 프로그램이 검토자를 인증하거나 PDF의 회계적 의미를 자동 판정하지 않는다.
- `reports`: basis(CFS/OFS), year, quarter(2/4), period_start, period_end, cadence(cumulative/annual), currency=KRW, actual=true, cells. 현재 지원은 12월 결산 연간·반기 실제치이며 다른 결산월·단독분기를 가정하지 않는다.
- `cells`: 계정별 원문 text, label, 물리 page(1부터), table/row/column(0부터), column_label, multiplier(1/1000/1000000), period_start/period_end/basis. 주석 열과 비교 열을 포함한 원문 좌표를 보존한다. 빈칸·대시는 0으로 바꾸지 않는다.

필수 계정은 assets/liabilities/equity/revenue/operating_profit/net_income/ocf 및 현금 검산용 icf/financing_cf/cash_start/cash_end/fx_effect다. parent_net/nci_net/parent_equity/nci 등의 추가 계정은 확인한 경우만 넣는다. 추출 셀은 사람이 검증한 전사 자료이며, 원문 해시 검사는 사본의 동일성을 확인한다. 셀 좌표 자체를 PDF에서 다시 인식하는 기능은 아니다.

## 반영과 조회

입력 식별·기간·단위·원문 해시·대차·현금흐름 검산을 모두 통과한 뒤 기존 수집 잠금을 잡는다. `<data_dir>/<profile>/company-financials/official-documents/<code>.json`에 원자적으로 저장하며 기존 적용본은 변경 시 백업한다. 관측본 `.observed.json`과 적용본은 구분한다. 같은 기간 정정은 기존 7% 반영 정책을 유지하고, 더 오래된 문서·문서 종류/법인 변경은 검토 상태로 보존한다. 원문 변경으로 이전 기간이 사라지는 덮어쓰기는 거부한다.

`load_cached`는 이 별도 저장본을 읽어 공식 자료 종류·URL·SHA256·페이지와 열 이름을 제공한다. 기존 DART와 같은 기간·기준·주기의 값이 겹치면 기존 DART 값을 유지한다. 인포맥스 우선 정책은 기존 테이블 병합 경로를 유지한다. 연간·반기 누적 값은 그대로 표시하며 미확보 단독분기·TTM·ROE를 생성하지 않는다. 자료 공개일 이전 조회에는 노출하지 않는다.

대체 원문 확보·반영은 정기보고서 수집 성공과 별개다. 기존 실패/불완전 수집 기록은 지우지 않고 `collection_health.alternative_document`에 대체 원문 근거를 함께 제공한다. 서버 재시작·예약·외부 조회·LLM 호출·원격 전송은 이 명령에 포함되지 않는다.

검증: `python -m unittest tests.test_official_statements` 및 `tools/validate_share_candidates.py`의 격리 portable 검사. 실제 원문 반영 결과와 합성 테스트 결과를 구분한다.
