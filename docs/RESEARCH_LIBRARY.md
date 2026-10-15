# Research Library MVP

## 최근 연구 이야기와 원문 가독성 · 2026-10-15

- 통합 검색과 원문 참조 사이에 최대 3개의 최근 연구 이야기를 표시한다. 표시 가능한 연구노트·산업 가설·연구카드에서 핵심, 적용 조건, 반례, 원문 관측과 미확보 근거를 5~8개 문단으로 추린다. 별도 모델 호출·외부 기사 자동 수집·DB 쓰기는 하지 않는다. 원문 제목이나 서지 정보만으로 본문을 생성하지 않는다. 충분한 연구가 없으면 3개를 임의로 채우지 않는다.
- 연구 기록/분류의 실제 업데이트 시각으로 정렬하고 내용 기준일과 원문 발행일을 따로 표시한다. 오래된 서적을 최근 기사로 표시하지 않는다. 출처 링크·연구 기록 이동·검색 필터를 연결한다. 가설의 상태와 반증/자료 부족을 보존하고 매매 판단이나 새 실증 결과로 승격하지 않는다.
- `/research-library`의 `stories`는 기존 읽기 전용 projection에서 출처 삭제/제외·권한 철회·검토 유효성을 처리한 뒤에만 생성한다. 따라서 철회된 근거가 이야기로 다시 노출되지 않는다. 기존 기록·revision은 변경하지 않는다.
- 원문 참조는 제목을 크게, 발행/확인일과 원문 링크는 작은 글씨로 표시한다. stage/revision/기록시각/분류/원문 위치/이력은 기본으로 접힌 상세에 보존한다. 320/390px에서도 검색·원문 링크·상세를 사용할 수 있다.

## 회사 통합 · 2026-10-12

지정 원격 feature `shinyj0270-afk/research-library`의 `f829ece1a152db0bb2765c59243596f3676bce58`를 회사 main에 통합하는 작업이다. 기존 1차 MVP는 CLI/API이며 아래 열람 연결을 추가했다. 아래의 메뉴 미변경 설명은 최초 MVP 시점의 범위다.

- 통합 대시보드의 더보기/모바일 분석 화면에서 **Research Library**를 선택한다. 대가8인 슬롯, 회사 로컬 연구카드·산업 가설의 현재 revision/기준일/반증조건/종목 연결을 열람한다. 데이터가 없으면 빈 상태이며 연구 DB를 생성하지 않는다. 입력은 기존 CLI를 사용한다.
- `/research-library`는 동일 loopback Host와 대시보드 토큰을 확인한다. PC별 연구DB를 SQLite `mode=ro`로만 읽고 연결을 닫는다. work DB에서 Telegram 자료가 발견되면 표시를 거부한다. 정적 HTML에는 연구 자료를 넣지 않으며 home DB를 회사로 복사하지 않는다.
- 운영자료 쓰기 없는 확인은 `python tools/serve_dashboard.py --read-only --port 8768`로 수행한다. 이 모드는 수집·보유동기화·연구DB 생성·추천 작성·체크포인트 저장을 실행하지 않고 POST를 거부한다. 기존 일반 운영 실행 동작은 유지한다.
- Claude 기록의 P3 중 seed ID의 비어 있거나 문자열이 아닌 입력 검사와 제거된 seed의 이전 revision 출처 표시를 보완했다. URL 정확 문자열 중복 기준은 유지한다. URL 호스트/기본포트/쿼리 순서의 동치 판단과 원문 식별자 보존 정책은 별도 설계·경계검증 후 적용한다. 서로 다른 URL을 독립 근거로 인증하지 않는다.
- 기존 feature 검토 APPROVED/56개 통과는 사용자 보고 및 feature 인계에 기록된 근거다. 회사에서는 새 실행 결과만 별도로 기록하고 회사 추가 UI/서버 변경을 과거 Claude 승인의 범위로 확대하지 않는다. 원시 Claude 검토 JSON은 회사에서 접근하지 못했으며 P3 요약은 지정 commit의 인계 문서로 확인했다.

이번 통합의 실제 실행·검증·GitHub 전송 상태는 CURRENT_HANDOFF.md를 따른다.

장기 투자 관점·산업 가설을 축적하는 독립 로컬 연구 계층이다. 단기 뉴스·실시간 수집·알림·주문·자동매매는 포함하지 않는다. 기존 START/CLOSE 및 SYNC_CONTRACT를 유지한다. 현재 Research Library worktree에서 구현하며 main 병합/push는 별도 작업이다.

## 기존 기능과 재사용

- investment/workspace_research.py: 저장 재무·가격·출처 분석. 신규 분석 계산을 만들지 않는다.
- investment/trend_following.py: 가격 기반 8조건 변형·자체 RS·시장 관측. analysis_context가 호출한다.
- investment/thesis_monitor.py: 종목별 v2.1 실패 시나리오·붕괴 조건. 별도 monitor_entries를 검증하고 evaluate를 호출한다. 섹터 가설이 종목 판단을 자동 변경하지 않는다.
- investment/store.py: transactional connect를 재사용하되 기존 research.sqlite3의 표/자료는 변경하지 않는다.
- investment/local_config.py: 사용자 확인 PC 프로필을 읽는다. unknown이면 실제 입력을 중단하며 설정을 추측하지 않는다.
- 기존 국내 일반주 분석은 core.eligible 범위다. 국내 상장 ETF는 code/market/kind 연결을 지원하지만 ETF 재무·추세 분석 공급자는 미연결이며 pending이다. ETF 계산을 새로 구현하지 않는다.

## 세 모듈

Telegram Research는 core 배열 2~3개 슬롯과 선택적 auxiliary를 관리한다. 실제 채널은 사용자가 지정한다. home에서만 registry/permission/수동 reference batch를 처리한다. work/unknown은 실제 Telegram 처리 금지. CLI는 Telegram 입력 파일을 열기 전에 프로필을 확인한다. 메시지 ID·날짜·원문 링크만 받으며 원문 본문·첨부·참여자·인증정보 필드는 거부한다. 기간·확인일·삽입/중복 수·누락 상태·범위 근거를 별도 기록한다. 메시지 ID 간격은 삭제·서비스 메시지·접근 제한으로 생길 수 있어 누락으로 단정하지 않는다. none_observed도 완전 수집 인증이 아니며 completeness는 unverified로 유지한다. 재수입은 중복 처리하고, 같은 ID의 다른 내용은 전부 rollback한다. 수정/삭제된 메시지 자동 덮어쓰기는 없다.

Investment Masters는 버핏·멍거·막스·린치·드러켄밀러·모부신·미너비니·오닐 8인 연구 슬롯을 제공한다. 기본 분류는 탐색 시작점이며 전체 전략을 단일 분류로 확정하지 않는다. 실제 카드는 복수 value/growth/cycle/trend 분류, 원문 source IDs, 자체 서술 원칙, 적용 조건, 반례를 요구한다. source는 canonical HTTPS URL, 발행일(미확인 null), 접근일, 페이지/섹션 locator, public/paid/private, independent/telegram을 가진다. 원문 본문 필드가 없다. 출처와 카드는 immutable이며 정정은 새 ID로 남긴다. 자체 서술 선언·길이 제한은 저작권 준수 인증을 대신하지 않으므로 사람 검토가 필요하다. 실제 대가의 원칙/반례를 검증한 seed 콘텐츠는 아직 없고 source_research_pending이다.

Investment Thesis는 sector/theme/claim/조건/반증조건/기준일/변경사유와 종목·대가카드 연결을 기록한다. expected_revision이 현재 revision과 달라지면 보존·중단한다. 각 evidence는 가설 revision, 복수 source IDs, support/refute/context, 관측과 해석, 확인일을 분리한다. 과거 revision 근거를 새 가설 지지로 자동 승격하지 않는다. source의 접근일 이후만 연결하며 누적 근거 수를 신뢰 점수나 투자 판단으로 바꾸지 않는다. 서로 복제한 여러 자료를 독립 근거 수로 해석하지 않는다. 글쓰기 초안은 결정론적인 독립 서술 틀·양쪽 근거·반증조건·출처와 미확보를 제시한다. 모델 호출·원문 재작성·자동 발행 없음.

## Telegram 권한 경계

2026-10-11 실제 읽은 공식 문서:

- https://telegram.org/tos
- https://telegram.org/tos/content-licensing
- https://telegram.org/blog/export-and-more (2018-08-27)

공식 Desktop 내보내기 기능의 존재는 연구·AI 이용 권한을 증명하지 않는다. 콘텐츠 이용조건은 통상 이용 이외 접근과 AI 관련 수집/이용을 제한하고 구체적 맥락의 지속적 동의를 규정한다. 이 MVP는 API/스크래핑/Desktop 원문 import/AI 자료 전송을 구현하지 않는다. manual_reference도 플랫폼 이용 근거(platform_basis), 채널별 권한(channel_basis), 공식 약관 확인일, reviewer 및 local_analysis_allowed=true가 모두 있어야 활성화된다. 단순 구독·공개채널·관리자 한 명의 허락을 모든 권리자의 동의로 추정하지 않는다. 이 필드는 검토 기록이며 프로그램이 권한을 독립 인증하지 않는다. 권한 철회 시 registry revision으로 enabled=false 처리하고 후속 입력을 중단한다. 기존 자료 폐기/보존 판단은 수동 후속이다. 실제 채널의 링크와 권한은 미확인으로 유지한다.

## 저장·공유

CLI DB: .local/research-library/{profile}/user_input/research_library.sqlite3. 합성 테스트는 fixture 별도 DB. 모든 입력/출력 파일은 .local/ 아래로 제한하고 기존 출력 덮어쓰기를 거부한다. .local/·DB 및 sidecar는 기존 .gitignore 제외 대상이다. 다른 PC의 설정/DB/자료를 복사하지 않는다. 이 MVP는 고정 로컬 저장을 사용하며 기존 data_dir 및 보유 동기화에 연구 DB를 연결하지 않는다.

approved-result는 확인한 정확한 초안의 digest와 reviewer/검토일, 독립분석·개인정보 없음·재배포 허용의 명시 확인을 요구한다. paid/private/telegram에 의존하는 결과는 거부하며 과거 가설 revision의 대가카드·누적 근거도 확인한다. 출력은 명시된 review와 초안만 반환하고 raw DB/채널/권한은 반환하지 않는다. 승인 결과도 .local에만 저장한다. 일반 Git 이동/stage/push는 자동 실행하지 않는다. 사람의 내용 검토 후 허용된 결과만 별도 명시 경로로 공유한다. 자체 확인표와 allowlist는 개인정보·저작권 검토를 대체하지 않는다. Telegram 유래 가설/노트는 회사 공유 및 외부 모델 검토 입력에서 제외한다.

## 실행

해당 PC의 기존 프로젝트 .venv에서 tools/research_library.py를 실행한다. worktree에 .venv가 없으면 그 worktree의 실행 환경 준비는 별도이고 다른 PC .venv를 복제하지 않는다. masters 명령은 프로필 없이 연구 슬롯 목록만 표시한다. 나머지 입력은 config/local.json의 사용자 확인 profile 필요.

```
python tools/research_library.py masters
python tools/research_library.py source --id source-1 --input .local/source.json
python tools/research_library.py master --id card-1 --input .local/card.json
python tools/research_library.py thesis --id thesis-1 --input .local/thesis.json
python tools/research_library.py thesis --id thesis-1 --expected-revision 1 --input .local/revised-thesis.json
python tools/research_library.py evidence --id evidence-1 --input .local/evidence.json
python tools/research_library.py propose --input .local/observations.json --output .local/candidate.json
python tools/research_library.py history --kind thesis --id thesis-1
python tools/research_library.py draft --id thesis-1 --output .local/draft.md
python tools/research_library.py channels --input .local/channels.json
python tools/research_library.py telegram --id channel-1 --input .local/coverage.json
```

입력 계약의 합성 예시는 tests/test_research_library.py의 source/card/thesis/evidence/registry/collection 함수다. 실제 자료나 실재 권한으로 사용하지 않는다. approved-result 입력 digest는 investment.core.digest(lib.draft(id))로 얻으며 검토 후 해당 값과 flags를 입력한다. CLI의 JSON 오류/참조 오류는 실패이며 실자료 성공으로 대체하지 않는다.

## 방법론 및 검증 책임

최종 재검토 후 추가 보완: thesis의 필수 seed_source_ids(직접 작성은 빈 배열 가능)에 propose 입력 출처를 보존한다. 모든 revision의 seed/card/evidence 출처를 공유 검사에 포함하며 나중에 seed를 지워도 과거 제한 출처 이력은 남는다. propose는 서로 다른 원문 URL 2개 이상의 관측을 요구하고 제한출처 표기를 반환한다. 근거와 이전 반박은 관측일·실제 UTC 기록시각·KST 기준 소급 입력을 표시한다. reviewed_on은 포함 연구의 기록일/관측일보다 이르면 거부한다. history 조회는 home의 보존 기록 열람이고, 철회된 Telegram 출처의 신규 분석·초안 재사용은 계속 차단한다. 철회된 출처를 포함한 가설의 유지/폐기 처리도 fail-safe로 차단될 수 있어 보존 여부와 독립 출처로의 정리는 수동 후속이다.

Claude Code 1차 정적 검토 후 보완: Telegram source는 channel_id와 활성 채널/권한을 재검사하고 권한 철회 후 evidence·draft 재사용을 거부한다. independent로 표시한 t.me/telegram.me/telegram.dog 출처를 거부한다. 날짜는 YYYY-MM-DD만 허용하고 KST 미래일을 거부한다. 초안은 기준일·실제 기록일·revision·변경사유·active/invalidated/retired 상태를 표시한다. invalidated revision에는 그 기준일까지 관측된 refute 근거가 필요하다. 과거 반박은 별도 재평가 섹션으로 남고, 근거별 날짜/source IDs·원문 locator가 연결된다. 제한 출처의 모든 revision 의존성을 확인해 로컬 초안에도 회사/외부 모델 공유 금지를 표시한다.

propose 입력은 sector/theme/as_of/observations/conditions/invalidation/instruments/master_ids를 받는다. observations는 서로 다른 source_id 2개 이상의 자체 observation과 support/refute/context를 담는다. 반환한 candidate는 검증 전 연구 질문이며, 사용자가 구체화한 가설과 evidence를 각각 저장한다. 인과·출처 독립성은 미검증이다.

URL은 DART rcpNo 같은 query를 허용하고 사용자정보·인증/세션/추적 query·fragment·로컬/IP 호스트를 거부한다. approved-result는 --draft .local/draft.md로 실제 검토 파일이 현재 초안과 일치하는지도 확인한다. draft 출력은 UTF-8/LF이고 content digest를 표시한다. 승인 reviewer는 로컬 입력에 보존하되 공유 결과에서는 제외한다. 사람의 실제 읽기 행위와 권한 적법성은 도구가 독립 인증하지 않는다.

Codex는 구조·구현·합성 계약/회귀 검증, Claude Code는 신규 모듈·설계·합성 테스트만 읽고 방법론·반증·역사·권한·공유 분리의 독립 검토를 담당한다. 기존 main/Orca 작업본 및 사용자 자료는 변경하지 않는다. 모델 선택/Reasoning은 실제 실행과 구분하고 자동 전환하지 않는다. 소스 비독립성, 생존편향, 후견편향, 원문/해석 구분, 발행일 미확인, ETF 적용범위, 원 전략과 자체 변형의 차이를 검토한다. 연구 결론의 실제 품질은 실재 콘텐츠가 입력되고 검토되기 전 PENDING이다.

MVP 범위는 로컬 CLI/API이며 운영 대시보드 메뉴는 변경하지 않는다. 따라서 신규 브라우저 UI 검증과 운영 DB 이행은 해당 없음. 실제 채널 수집·대가 콘텐츠 구축·ETF 분석 공급자·블로그 발행은 미완료로 유지한다.


## home 실자료 검증 및 운영 기준 · 2026-10-12

기존 records 표와 immutable source/master/evidence 및 thesis revision을 유지한다. `research_catalog`는 같은 DB에 kind=catalog의 별도 revision 메타데이터만 추가한다. 기존 INVESTMENT/Infomax/포트폴리오 계산·보유동기화에는 연결하지 않는다. Agents/claude-mem/전체 Telegram 백업을 구현하지 않는다.

### 자료 단계와 필수 메타데이터

| 단계 | 정의 | 현재 저장 방식 |
|---|---|---|
| raw | 원출처의 식별·날짜·링크를 보존한 참고 레코드. 원문 본문 자체가 아님 | source 및 Telegram 메시지 reference. summary=null |
| derived | 작성자/AI의 자체 해석·가설·요약. 원출처의 직접 주장과 구별 | master/thesis/evidence 및 catalog summary. AI 해석은 source_note에 표시 |
| curated | 사람이 출처·정확성·활용성·권한을 실제 검토한 선택 자료 | catalog stage=curated, human_reviewed=true, reviewed_by/reviewed_on 필수 |
| excluded | 홍보·저품질·중복 파생자료 등 활용 제외 | 일반 검색·열람 제외, 근거와 이력 보존 |
| deleted | 잘못 입력된 항목의 논리 삭제 | 일반 검색·열람·get/초안 재사용 차단, 원본/history 유지 |

curated는 투자 판단 승인이나 재배포 허가가 아니다. 입력된 review 선언은 도구의 독립 인증이 아니며 AI가 사람 검토 완료를 대리 선언하지 않는다. raw→derived→curated 자동 승격은 없다. 별도 원문/AI 텍스트 필드를 섞지 않고 raw의 summary 입력은 거부한다.

출처 필수 필드: title/url/published_on(미확인 null)/accessed_on/access/origin/locator, Telegram은 channel_id 추가. 날짜는 현재 YYYY-MM-DD 단위이며 시간대 포함 published_at 시각 보존은 미지원이다. 모르는 발행일을 조회일로 채우지 않는다.

catalog 필드: stage/topic/sector/tags/persons/instruments/event_id/summary/source_note/reason/reviewed_by/reviewed_on/human_reviewed. topic/sector/source_note/reason은 필수이고, 모르는 분류는 미확인 또는 산업공통으로 표시한다. persons는 기존 8인 ID, instruments는 기존 국내 code/market/kind 식별 계약을 유지한다. core_thesis는 master.principle 또는 thesis.claim에, 적용 조건·반례는 기존 필드에 둔다. tags는 최대30개의 중복 없는 문자열이다. sector relevance/company relevance는 연구 적용 후보일 뿐 실제 기업 정량 근거나 대가의 종목 추천이 아니다.

### 선별·중복·연결 규칙

- Telegram 핵심3채널은 사용자 지정 이름으로 home에서 비활성 등록했다. 정확한 채널/메시지 URL 및 platform_basis/channel_basis/reviewer/약관 확인일 근거가 없으므로 활성화·실제 입력은 대기한다. 공개·구독 가능 여부만으로 허가를 완료 처리하지 않는다. 로그인/세션/쿠키 추출·우회·원문 자동 수집 없음. 기존 외부 모델·회사 공유 제한을 유지한다.
- 첫 표본은 채널별 약5건, 총15건으로 제한한다. 기업/산업/핵심 논점과 출처를 추적할 수 있는 자료를 우선하며 단순 광고·출처 없는 재가공·과장 성과·반복 전달은 curated에서 제외한다. 채널 전체를 일괄 신뢰 등급으로 인증하지 않는다. 자료별 재가공 여부/확인 가능성/사용 목적과 채널별 뉴스·아이디어·기업·시장·AI재가공 성격을 source_note에 근거와 함께 기록한다.
- Telegram 메시지 중복은 channel_id+message_id digest, 날짜/링크까지 같으면 재입력은 삽입0. 동일 키의 다른 날짜/링크는 전체 batch rollback 후 사람 확인이다. 다른 채널의 같은 이슈는 각 source를 별도로 보존한다.
- CLI source 중복은 정확 URL을 먼저 확인한다. 같은 URL/같은 payload는 기존 id를 반환한다. 다른 payload는 중단하고 metadata 정정을 안내한다. URL 의미 동치/리다이렉트/같은 인물의 유사 노트 의미 중복 판정은 미지원이며 사람 확인이다. 한 쓰기 세션 원칙을 유지한다. Library.source 직접 API의 중복 계약은 기존 ID/revision 기준이므로 실제 입력은 CLI source를 사용한다.
- 같은 이슈는 사람 검토한 동일 event_id와 topic으로 연결한다. 여러 source_id를 연결해도 독립 근거 수로 인증하지 않는다. 동일 인물·주제의 기존 노트는 search로 찾고 기존 source/card ID를 연결한다. 기존 노트의 정확한 Git URL/locator와 로컬 원본 해시를 보존하고 노트 본문을 DB에 재복제하지 않는다.
- 섹터 표준값은 반도체/전력기기/조선/화학을 사용한다. 수요·설비투자·투자효율·금리·위험관리 등 topic은 섹터와 분리한다. 비슷한 단어는 tags에 보조로 남기고 실제 관련성 미확보 자료에 특정 기업 태그를 채워 검색 성공을 만들지 않는다.

### 검색·정정·삭제·재수집

기존 CLI에 search/annotate를 추가했다. 입력·출력은 기존대로 .local 아래만 허용한다. 검색 결과의 catalog_revision으로 정정 expected_revision을 확인하고 --stage deleted로 삭제된 항목의 이력 메타데이터만 확인한다. 결과의 source와 annotation은 분리되며 출처 URL/발행일/접근일/locator가 함께 반환된다. 권한 철회된 출처의 재사용 검색은 차단된다. UI는 열람 전용이며 새 검색/annotation은 CLI로 수행한다.

```
python tools/research_library.py search --person marks
python tools/research_library.py search --topic "설비투자와 투자효율"
python tools/research_library.py search --sector 반도체
python tools/research_library.py search --company 005930
python tools/research_library.py search --event-id event-identifier
python tools/research_library.py search --stage curated
python tools/research_library.py annotate --kind source --id source-1 --input .local/annotation.json
python tools/research_library.py annotate --kind source --id source-1 --expected-revision 1 --input .local/correction.json
```

- 정정: 원문 source는 덮어쓰지 않는다. 잘못된 분류/해석은 catalog 현재 revision을 확인한 뒤 같은 target의 다음 revision에 reason을 기록한다. 원출처 사실 자체의 정정은 새 source ID로 보존하고 source_note로 이전 ID를 연결한다. 같은 URL의 상충 payload는 CLI 중복 경고 후 사람이 원문 대조하고 기존 immutable API의 명시 정정 경로를 판단한다. 자동 재수집 덮어쓰기 없음.
- 삭제: annotate stage=deleted로 논리 삭제한다. 종속 카드·가설은 UI에서도 숨기며 초안 재사용은 실패한다. 영구 개인정보 삭제는 미지원이고 별도 사용자 요청·참조 영향 확인이 필요하다. 논리 삭제를 물리적 삭제로 보고하지 않는다. history로 원본과 수정 이력을 확인하고 reason·현재 expected_revision을 넣어 명시 복원한다.
- 제외: stage=excluded로 일반 검색/열람 제외, --stage excluded로 사유를 확인한다. curate는 사람이 개별 자료를 읽고 검토했을 때만 지정한다. 삭제/제외 후 가설을 자동 투자 판단으로 승격하지 않는다.
- 누락: coverage에 기간/start/end/checked_on/missing/coverage_basis를 남긴다. 메시지 ID 간격은 누락 증거가 아니다. known_gaps는 접근 가능한 정확 링크·기간을 사람 확인한 경우만 사용한다. 허용된 누락 메시지 소량을 같은 batch로 재입력해 inserted/duplicates를 비교한다. 삭제·권한 제한·접근 불가는 분리 기록한다. completeness는 여전히 unverified이며 전체 백업 완료를 선언하지 않는다.

### 이번 실제 검증 결과와 한계

- 실제 입력은 기존 주간 연구노트1회분 + 독립 공식 출처3개 = 출처 문서4건, 자체 해석 대가카드3건이다. 카드·annotation·revision을 독립 실제 문서 수에 더하지 않는다. Telegram 3채널 각각0건으로 10~20건 및 Telegram 핵심3채널 완료 조건은 충족하지 못했다.
- 기존 노트는 docs/research/INVESTMENT_MASTERS_WEEKLY_2026-10-12.md. Marks/Minervini/Mauboussin 연결과 인물 검색 각2결과, 공통 topic 검색4결과, 출처 재입력 모두 duplicate 확인. 수정·논리 삭제·복원 후 immutable 원본 일치 확인.
- 실제 반도체/전력기기/조선/화학 검색 및 005930 검색은 모두0건. 검색 함수는 합성 테스트로 검증했지만 실제 관련 연구 미확보다. Telegram+대가 혼합 검색 및 다중 실제 채널 같은 이슈 연결은 미검증이다.
- 원문 URL/접근일/locator 및 기존 노트·Marks 발행일 보존. 나머지 공식 페이지2개의 발행일은 null로 유지한다. raw 참고출처3/derived4/curated0이며 실제 사람 curate 검토는 대기한다.
- 로컬 검증 보고서 .local/research-validation-20261012/actual-report.json 및 DB/입력 스크립트는 Git 제외. 원문 본문·유료자료·세션/인증·보유·로컬 DB를 공유하지 않는다. 합성3채널/중복/원문금지/권한철회/수정/검색/리뷰게이트 검사를 실제 채널 성공으로 대신하지 않는다.

### Agents 도입 준비도 (구현하지 않음)

| 후보 | 입력 | 출력 | 자동화 가능한 단계 | 사람이 승인할 단계 |
|---|---|---|---|---|
| Collector | 허용된 채널/URL·기간·권한 기록·소량 표본 | 출처 reference와 coverage·중복/실패 보고 | 기존 계약 검사·정확 ID 중복·날짜 정규화 | 접근/이용권한·로그인·채널 선정·원문 저장 범위·누락 재수집 |
| Research | 허용 출처/기존 노트·master IDs·연구 질문 | 출처 연결 자체 서술·조건·반론·derived 후보 | ID 연결 후보·태그 제안·반론 누락 검사 | 원문 귀속·실제 논점 검증·외부 모델 전송 허가·curated 승격 |
| Synthesis | 검토된 섹터/topic/event·출처·기존 정량 자료 | 검증 전 산업 가설·반증조건·근거 연결 | event/topic 그룹·누락 검사·기존 분석 참조 | 출처 독립성·인과·기업 관련성·시점/통화 계약·투자 판단/공유 |

현재 판정은 준비 PARTIAL, 운영 자동화 도입 보류다. 입력 계약·revision·검색 경계는 있으나 실제3채널·10~20건·사람 curate·혼합검색/섹터/기업 재활용을 먼저 검증해야 한다. Telegram 유래 자료의 외부 모델 입력 제한은 그대로이므로 Research/Synthesis Agent에 자동 전달하지 않는다. 자동 주문/매매/전체 백업/claude-mem은 범위 밖이다.
