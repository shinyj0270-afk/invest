# 투자대가·주도산업 주간 연구 검증본 — 2026-11-02

작성: Claude Code, 2026-11-09 KST(지연 등록). 사용자가 제공한 2026-11-02 주간 연구노트를 공개 원문과 대조해 작성한 검증본이다. 원본은 덮어쓰지 않고 `.local/research-library/inbox/2026-11-02/original.md`(SHA256 `5a5afc91…6dda510`)에 보존한다. 국내 주식·국내 상장 ETF 연구이며 모든 가설은 실증 전이다. 미국 사례는 방법론 참고일 뿐 국내 업종 강세나 매수 판단의 증거가 아니다.

## 출처 대조 범위와 정정

신규 URL 4개는 2026-11-09에 HTTP 200과 제목 일치를 확인했다. S04(IBD 섹터순환)의 발행일은 원본에 "직접 확인 불가"로 적혀 있었으나 페이지 메타데이터 `datePublished` 2024-08-05로 확인했다. S06(드러켄밀러)은 페이지 본문에서 2026-01-30 녹화와 2026-02-27 공개를 확인했다. S12(Stripe Press)는 출판사 소개만 확인했고 판본 발행일은 미확인이다. S13(PBS)의 방송일 1997-01-14는 원본 기재값이며 이번에 재확인하지 못해 published_on을 null로 둔다.

S10·S11의 연차보고서 PDF URL은 같은 보고서의 기존 링크 페이지 출처(SRC-20261012-10/11)로 대체 연결했다. 같은 문서의 URL 변형을 중복 출처로 만들지 않기 위해서다. 2025 회계연도 CEO 서한은 Greg Abel이 썼으며 버핏의 2026년 서한으로 귀속하지 않는다. IBD 자료는 오닐 사후 교육이다. IBD RS·FTD를 자체 RS70/RS126·KOSPI 이평 국면과 같은 것으로 보지 않는다.

| 번호 | 등록 출처 ID | 발행일 | 비고 | URL |
|---|---|---|---|---|
| S01 | SRC-20261012-01 | 2013-03-21 | 기존 재사용 | [원문](https://www.mheducation.com/highered/mhp/product/trade-like-stock-market-wizard-how-achieve-super-performance-stocks-any-market.html) |
| S02 | SRC-20261012-02 | 미확인 | 기존 재사용 | [원문](https://mtp.minervini.com/) |
| S03 | SRC-20261026-03 | 2009-05-18 | 기존 재사용 | [원문](https://www.mheducation.com/highered/mhp/product/how-make-money-stocks-winning-system-good-times-or-bad.html) |
| S04 | SRC-20261102-04 | 2024-08-05 | 신규; 페이지 메타 날짜, 공개 미리보기만 | [원문](https://www.investors.com/how-to-invest/investors-corner/sector-rotation-a-key-to-find-the-best-stocks/) |
| S05 | SRC-20261012-06 | 미확인 | 기존 재사용 | [원문](https://www.investors.com/how-to-invest/stock-market-timing-how-to-invest-in-stocks-tracking-bull-markets-bear-markets-stock-market-trends/) |
| S06 | SRC-20261102-06 | 2026-02-27 | 신규; 1차 구술 출처 | [원문](https://www.morganstanley.com/insights/videos/hard-lessons/duquesne-stan-druckenmiller-iliana-bouzali) |
| S07 | SRC-20261026-10 | 2024-10-15 | 기존 재사용 | [원문](https://www.morganstanley.com/im/en-us/institutional-investor/insights/consilient-observer/measuring-the-moat.html) |
| S08 | SRC-20261026-08 | 2026-04-14 | 기존 재사용 | [원문](https://www.morganstanley.com/im/en-us/institutional-investor/insights/consilient-observer/the-neglected-value-driver.html) |
| S09 | SRC-20261012-08 | 2026-09-22 | 기존 재사용 | [원문](https://www.oaktreecapital.com/insights/memo/shall-we-repeal-the-laws-of-economics---part-iii) |
| S10 | SRC-20261012-10 | 2025-02-22 | 기존 링크 페이지로 대체 | [원본 표기 PDF](https://www.berkshirehathaway.com/2024ar/2024ar.pdf) |
| S11 | SRC-20261012-11 | 2026-02-28 | 기존 링크 페이지로 대체; Abel 귀속 | [원본 표기 PDF](https://www.berkshirehathaway.com/2025ar/2025ar.pdf) |
| S12 | SRC-20261102-12 | 미확인 | 신규; 출판사 소개만 | [원문](https://press.stripe.com/poor-charlies-almanack) |
| S13 | SRC-20261102-13 | 미확인 | 신규; 방송일 원본 기재값 | [원문](https://www.pbs.org/wgbh/pages/frontline/shows/betting/pros/lynch.html) |

## 신규 연구카드

MASTER-20261102-01(미너비니), -02(오닐), -03(드러켄밀러), -04(모부신·Callahan), -05(막스), -06(버핏/에이블 귀속 구분), -07(멍거), -08(린치). 각 카드는 자체 요약(own_paraphrase)이며 원문 본문을 저장하지 않는다.

## 신규 가설

- **THESIS-20261102-01 산업 순위 변화 속도의 추가 설명력**: 산업 RS 수준·확산·상위3 집중을 통제한 뒤에도 순위 개선/악화 속도(Δrank)가 이후 63/126거래일 상대가격에 추가 설명력을 주는지 본다. THESIS-20261026-01의 증분 가설이다.
- **THESIS-20261102-02 시장 국면 전환과 주도산업 신호의 상호작용**: 같은 산업 지표라도 시장 국면이 개선 중인지 악화 중인지에 따라 지속성과 하락 위험이 다른지 본다. FTD 원전 재현을 주장하지 않는다.

각 가설에 context 근거(CTX-20261102-01/02)를 하나씩 연결했다. 지지/반박 근거가 아니다.

## 등록 결과(2026-11-09, work 로컬 DB)

기존 `import_weekly_research` 검증 → SQLite backup → apply: 신규 16(출처 4·카드 8·가설 2·context 2), 기존 출처 9 재사용. 같은 묶음 재실행 inserted 0(duplicate). 분류 catalog 16건 입력, 재입력 0. 실증·현재 산업 순위·사람 curate는 실행하지 않았다.
