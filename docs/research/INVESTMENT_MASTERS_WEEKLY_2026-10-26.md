# 투자대가·주도산업 주간 연구 검증본 — 2026-10-26

작성: Codex, 2026-10-26 KST. 사용자가 제공한 주간 연구노트를 공식 공개 출처와 대조해 새로 작성한 검증본이다. 원본을 덮어쓰지 않는다. 국내 주식·국내 상장 ETF 연구이며, 모든 가설은 실증 전이다. 미국 사례는 방법론 참고이고 국내 업종 강세나 매수 판단의 증거가 아니다. 원본·manifest·DB·상세 영수증은 Git 제외 로컬 보존한다.

## 출처 대조 범위와 보류

S01 출판사 서지·목차와 S03 서지를 확인했다. 책 전문·VCP의 상세 구조나 Trend Template 전체 규칙은 검증하지 않았다. S02는 공식 교육 소개이며 성과 홍보를 독립 성과 검증으로 취급하지 않는다. S08·S10은 공식 페이지의 요약·메타데이터 확인이며 전체 PDF 검증이 아니다. S09는 메모의 거품 관련 질문 부분까지 대조했다. S11은 역사적 서한 목록만 확인했다.

S04~S07은 공개 제목·미리보기만 열렸다. 첨부에 적힌 S04 2024-06-13, S05 2024-10-16, S07 2026-10-23 발행일은 이번 조회에서 확인하지 못해 신규 source의 published_on을 null로 둔다. S06은 기존 null 출처를 유지한다. 52주 RS와 최근3개월 가중치, A/D 기간·구체 산식, FTD/distribution day 규칙 및 순위 상승 폭은 검증된 사실로 등록하지 않는다. 제목의 3-Month RS Rating을 기존 52주 RS와 동일한 지표로 확정하지 않는다. IBD 교육·보도를 오닐 생전의 신규 발언으로 귀속하지 않는다.

막스 메모는 기술의 실재성과 자산가격 적정성을 분리한다. 이를 국내 공급망이나 시장 내재 CAP 비교에 적용하는 것은 작성자의 연구 확장이다. 모부신 연구는 Dan Callahan 공동저자 귀속을 보존한다. 현재 인물 스키마의 mauboussin 슬롯을 사용하며 Callahan을 새 정식 투자대가 슬롯으로 만들지 않는다.

| 번호 | 등록 출처 ID | 발행일 | 접근 범위 | URL |
|---|---|---|---|---|
| S01 | SRC-20261012-01 | 2013-03-21 | 기존 immutable 출처 재사용; 이번 재열람은 신규 카드 분류에 기록 | [공식 출처](https://www.mheducation.com/highered/mhp/product/trade-like-stock-market-wizard-how-achieve-super-performance-stocks-any-market.html) |
| S02 | SRC-20261012-02 | 미확인 | 기존 immutable 출처 재사용; 이번 재열람은 신규 카드 분류에 기록 | [공식 출처](https://mtp.minervini.com/) |
| S03 | SRC-20261026-03 | 2009-05-18 | publisher_bibliography; book_body_not_read | [공식 출처](https://www.mheducation.com/highered/mhp/product/how-make-money-stocks-winning-system-good-times-or-bad.html) |
| S04 | SRC-20261026-04 | 미확인 | institution_education; public_title_excerpt_only; full_text_and_date_unverified | [공식 출처](https://www.investors.com/how-to-invest/investors-corner/how-to-invest-in-stocks-relative-strength/) |
| S05 | SRC-20261026-05 | 미확인 | institution_education; public_title_excerpt_only; full_text_and_date_unverified | [공식 출처](https://www.investors.com/how-to-invest/investors-corner/how-to-buy-stocks-ibd-rating-reveals-what-stocks-big-money-funds-are-buying/) |
| S06 | SRC-20261012-06 | 미확인 | 기존 immutable 출처 재사용; 이번 재열람은 신규 카드 분류에 기록 | [공식 출처](https://www.investors.com/how-to-invest/stock-market-timing-how-to-invest-in-stocks-tracking-bull-markets-bear-markets-stock-market-trends/) |
| S07 | SRC-20261026-07 | 미확인 | institution_reporting; public_title_excerpt_only; date_and_full_rank_change_unverified; US_example_only | [공식 출처](https://www.investors.com/research/ibd-industry-themes/cme-stock-cboe-ice-sector-rotation-ai-stocks/) |
| S08 | SRC-20261026-08 | 2026-04-14 | primary_author_research; official_page_summary; CAP_ROIC_spread_duration; full_PDF_not_read | [공식 출처](https://www.morganstanley.com/im/en-us/institutional-investor/insights/consilient-observer/the-neglected-value-driver.html) |
| S09 | SRC-20261026-09 | 2026-02-26 | primary_author_memo; Is_It_a_Bubble_section; technology_investment_price_distinction | [공식 출처](https://www.oaktreecapital.com/insights/memo/ai-hurtles-ahead) |
| S10 | SRC-20261026-10 | 2024-10-15 | primary_institution_page; bibliography_and_summary_only; no_new_empirical_claim | [공식 출처](https://www.morganstanley.com/im/en-us/institutional-investor/insights/consilient-observer/measuring-the-moat.html) |
| S11 | SRC-20261026-11 | 미확인 | primary_company_index; historical_1977_2024_links_only; no_new_Buffett_letter_claim | [공식 출처](https://www.berkshirehathaway.com/letters/letters.html) |

## 신규 연구카드

### MASTER-20261026-01 — minervini

출판사 목차는 SEPA·추세·산업군과 촉매·이익의 질·주도주·위험관리를 함께 다룬다. 공식 교육 소개는 차트·위험관리·포지션 크기를 안내한다. 책 전문, Trend Template 개별 수치와 VCP 구조는 이번에 검증하지 않았다.

- 전략: trend, growth
- 조건: 수정가격·유동성·산업분류·공시시점을 고정; 산업 확산과 개별기업 진입위험은 별도 연구 질문으로 관측
- 반례: 유동성 저하나 기업행사 때문에 수축 프록시가 왜곡될 수 있음
- 출처: SRC-20261012-01, SRC-20261012-02

### MASTER-20261026-02 — oneil

공식 출판사는 오닐의 CAN SLIM 저서를 확인한다. IBD 후속 교육·미국 산업순환 기사는 공개 제목과 미리보기만 확인했다. RS/A-D 상세 산식·기간·발행일 및 순위 변화는 미검증으로 보존한다. 산업 상승의 폭·집중도 비교는 작성자의 국내 연구 설계이며 오닐 직접 발언이나 한국시장 성과 증거가 아니다.

- 전략: growth, trend
- 조건: 산업 모집단·구성기업·비교지수·관측일을 사전 고정; 기관 순매수·가격거래량 프록시·ETF 순자산 변화를 분리
- 반례: 소수 대형주 집중이나 산업분류 변경이 광범위한 강세처럼 보일 수 있음
- 출처: SRC-20261026-03, SRC-20261026-04, SRC-20261026-05, SRC-20261012-06, SRC-20261026-07

### MASTER-20261026-03 — mauboussin

모부신·댄 캘러핸 공동 연구의 공식 요약은 ROIC와 자본비용의 격차·투자 규모·양의 격차 유지기간을 기업가치 요인으로 구분하며 시장 내재 CAP와 평균회귀를 다룬다. 국내 자본재의 CAP 비교는 작성자 가설이다. 전체 PDF 실증표는 검증하지 않았다.

- 전략: value, growth
- 조건: ROIC/WACC 정의·시점·무형자산 처리·말기가치 가정 공개; 공동저자 Dan Callahan 귀속 보존; 현재 스키마의 인물 슬롯은 mauboussin
- 반례: 일시적 공급 부족이나 경쟁 증설로 높은 ROIC가 지속되지 않을 수 있음
- 출처: SRC-20261026-08, SRC-20261026-10

### MASTER-20261026-04 — marks

막스는 AI 기술의 실재성과 자산가격 적정성을 별도 질문으로 나누고 인프라 투자회수와 미래 수익성의 불확실성을 설명한다. 국내 AI 공급망의 CAP·수주 질에 적용하는 것은 작성자의 확장이다. 특정 한국산업 추천으로 해석하지 않는다.

- 전략: cycle, value
- 조건: 기술 수요·기업 현금흐름·투자회수·평가가격을 독립 확인; 기업별 신규 공급·수요 둔화와 기대의 차이를 검토
- 반례: 혁신이 기대를 초과하거나 수요 증가에도 경쟁 때문에 이익이 감소할 수 있음
- 출처: SRC-20261026-09

## 신규 세부 가설과 기존 연구 연결

### THESIS-20261026-01 — 산업 주도력의 폭과 지속기간

검증 전 자체 합성: 산업 RS가 유사하더라도 상승 확산률·종목 중앙값·상위 집중도가 다르면 이후 추세 유지 특성이 다를 수 있다.

THESIS-20261019-01의 실적 확산 질문에서 가격 확산·집중도의 추가 설명력으로 구분한 후속 가설. 기존 revision 유지; active는 연구 중이며 검증 완료 아님.

- 기준일: 2026-10-26; 상태 active는 연구 중이며 검증 완료 아님
- 첫 적용 후보 섹터: 반도체; 다른 후보는 전력망·산업자동화·조선·방산이며 현재 주도력 판정 아님
- 연결 카드: MASTER-20261026-01, MASTER-20261026-02
- 검증: 산업 동일/시총가중 상대수익·50/200일선 상회비중·상위3종목 기여를 월말 고정; 이후3·6개월 상대성과·하락위험 비교; 시장국면·기존 RS·유동성·상폐·분류변경·다중검정 통제
- 반증: 시장국면과 기존 산업 RS를 통제한 뒤 확산 지표의 추가 설명력이 없으면 재검토

### THESIS-20261026-02 — 주도산업의 시장 내재 경쟁우위 지속기간

검증 전 자체 합성: 같은 주도산업의 주가·수주가 강할 때 미래 성과는 성장률 외에도 추가 투자수익률과 경쟁우위 유지기간의 차이에 영향받을 수 있다.

THESIS-20261019-02 및 THESIS-20261012-01의 투자효율에서 시장 기대 CAP 지속기간으로 확장. 기존 가설 대체 아님; 실증 미실행.

- 기준일: 2026-10-26; 상태 active는 연구 중이며 검증 완료 아님
- 첫 적용 후보 섹터: 전력기기; 다른 후보는 전력망·산업자동화·조선·방산이며 현재 주도력 판정 아님
- 연결 카드: MASTER-20261026-03, MASTER-20261026-04
- 검증: 동일산업 ROIC-WACC·수익성 유지기간·수주와 증설·당시 추정치 비교; 이후3·6·12개월 상대성과; 기업규모·산업가격·환율·생존편향 통제; CAP 역산 가정 공개
- 반증: 산업·기업 매출 성장과 가격 추세를 통제한 뒤 경쟁우위 지표가 추가 설명력을 제공하지 못하면 재검토

배경 근거 CTX-20261026-01/02는 각 가설 revision 1에 context로 연결한다. 실증 지지·반박은 미확보다. ETF 재무는 구성기업 재무 집계와 구분하며, 가격·거래량 프록시, 실제 투자자 순매수, ETF 자금흐름은 서로 대체하지 않는다. PIT·수정가격·분류 변경·상장폐지·유동성·환율·비용을 통제하기 전 성과를 주장하지 않는다.

## 등록 계약

기존 import_weekly_research CLI로 검증·SQLite backup·apply·같은 입력 재실행을 수행한다. catalog는 기존 annotate API로 raw/derived 및 persons·strategy 태그·sector·related 선행 가설을 연결하고 같은 값은 재입력하지 않는다. 기존 source payload와 이전 revision은 그대로 보존한다. 자동 링크는 탐색 관계이며 독립 근거 수나 인과 검증을 의미하지 않는다. 사람 검토/curated 승격, 유료 본문 저장·복제, 다른 PC DB 복사와 결과 발행은 하지 않는다. 대시보드는 등록·검증 이후 기존 읽기 전용 projection에서 새 기록을 조회한다.

## 실제 등록 검증 — work, 2026-10-26

| 종류 | 등록 전 | 등록 후 | 신규 |
|---|---:|---:|---:|
| 출처 | 15 | 23 | 8 |
| 연구카드 | 8 | 12 | 4 |
| 가설 | 7 | 9 | 2 |
| 배경근거 | 7 | 9 | 2 |
| weekly 영수증 | 2 | 3 | 1 |
| catalog 분류 | 9 | 25 | 16 |

핵심 연구 레코드는 37→53건이다. 기존 출처 3건 재사용, 신규 16건 등록. 같은 원본·manifest의 두 번째 실제 apply는 inserted=0/skipped=19/duplicate=true이며 DB 행 변화가 없다. 같은 catalog 값 재검사도 신규0이다. 기존 모든 행과 revision 보존·중복 URL0·SQLite integrity_check=ok를 확인했다.

신규 ID는 SRC-20261026-03/04/05/07/08/09/10/11, MASTER-20261026-01~04, THESIS-20261026-01/02, CTX-20261026-01/02다. 각 가설 r1·연결 카드2개와 context1개를 재조회했다. 기존 인물·전략·섹터·주제 기반 주간 링크74개와 10월19일 선행 가설 연결을 확인했다. 링크 수는 증거 수나 신뢰 점수가 아니다. 전체 catalog/weekly record ID와 백업·실행 영수증은 Git 제외 로컬 inbox에 보존한다. 다른 PC DB 등록·수신은 미확인이다.

운영 대시보드의 인증된 GET /research-library HTTP200에서 source23/card12/thesis9 및 새 가설2건·연결 인물/섹터/카드/배경근거를 확인했다. 서버 build/source 일치·restart_required=false이며 재시작/제품코드 변경은 없다. 브라우저 연결 부재로 실제 화면 검사는 미실행이고, 전체 /dashboard 요청은45초 시간초과였다. 기존 화면의 '연구 목록 다시 확인'으로 새 DB를 조회할 수 있다.
