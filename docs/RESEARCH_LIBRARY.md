# Research Library MVP

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

Telegram Research는 core 배열 2개 슬롯과 선택적 auxiliary를 관리한다. 실제 채널은 사용자가 지정한다. home에서만 registry/permission/수동 reference batch를 처리한다. work/unknown은 실제 Telegram 처리 금지. CLI는 Telegram 입력 파일을 열기 전에 프로필을 확인한다. 메시지 ID·날짜·원문 링크만 받으며 원문 본문·첨부·참여자·인증정보 필드는 거부한다. 기간·확인일·삽입/중복 수·누락 상태·범위 근거를 별도 기록한다. 메시지 ID 간격은 삭제·서비스 메시지·접근 제한으로 생길 수 있어 누락으로 단정하지 않는다. none_observed도 완전 수집 인증이 아니며 completeness는 unverified로 유지한다. 재수입은 중복 처리하고, 같은 ID의 다른 내용은 전부 rollback한다. 수정/삭제된 메시지 자동 덮어쓰기는 없다.

Investment Masters는 버핏·멍거·막스·린치·드러켄밀러·모부신·미너비니·오닐 8인 연구 슬롯을 제공한다. 기본 분류는 탐색 시작점이며 전체 전략을 단일 분류로 확정하지 않는다. 실제 카드는 복수 value/growth/cycle/trend 분류, 원문 source IDs, 자체 서술 원칙, 적용 조건, 반례를 요구한다. source는 canonical HTTPS URL, 발행일(미확인 null), 접근일, 페이지/섹션 locator, public/paid/private, independent/telegram을 가진다. 원문 본문 필드가 없다. 출처와 카드는 immutable이며 정정은 새 ID로 남긴다. 자체 서술 선언·길이 제한은 저작권 준수 인증을 대신하지 않으므로 사람 검토가 필요하다. 실제 대가의 원칙/반례를 검증한 seed 콘텐츠는 아직 없고 source_research_pending이다.

Investment Thesis는 sector/theme/claim/조건/반증조건/기준일/변경사유와 종목·대가카드 연결을 기록한다. expected_revision이 현재 revision과 달라지면 보존·중단한다. 각 evidence는 가설 revision, 복수 source IDs, support/refute/context, 관측과 해석, 확인일을 분리한다. 과거 revision 근거를 새 가설 지지로 자동 승격하지 않는다. source의 접근일 이후만 연결하며 누적 근거 수를 신뢰 점수나 투자 판단으로 바꾸지 않는다. 서로 복제한 여러 자료를 독립 근거 수로 해석하지 않는다. 글쓰기 초안은 결정론적인 독립 서술 틀·양쪽 근거·반증조건·출처와 미확보를 제시한다. 모델 호출·원문 재작성·자동 발행 없음.

## Telegram 권한 경계

2026-10-11 실제 읽은 공식 문서:

- https://telegram.org/tos
- https://telegram.org/tos/content-licensing
- https://telegram.org/blog/export-and-more (2018-08-27)

공식 Desktop 내보내기 기능의 존재는 연구·AI 이용 권한을 증명하지 않는다. 콘텐츠 이용조건은 통상 이용 이외 접근과 AI 관련 수집/이용을 제한하고 구체적 맥락의 지속적 동의를 규정한다. 이 MVP는 API/스크래핑/Desktop 원문 import/AI 자료 전송을 구현하지 않는다. manual_reference도 플랫폼 이용 근거(platform_basis), 채널별 권한(channel_basis), 공식 약관 확인일, reviewer 및 local_analysis_allowed=true가 모두 있어야 활성화된다. 단순 구독·공개채널·관리자 한 명의 허락을 모든 권리자의 동의로 추정하지 않는다. 이 필드는 검토 기록이며 프로그램이 권한을 독립 인증하지 않는다. 권한 철회 시 registry revision으로 enabled=false 처리하고 후속 입력을 중단한다. 기존 자료 폐기/보존 판단은 수동 후속이다. 실제 채널 2개와 권한은 미확인으로 유지한다.

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
