# CURRENT HANDOFF

Updated: 2026-11-03T12:10:00+09:00 (SESSION CLOSE 재작성; 전송 검증 pending)
Last agent: Claude Code (Opus/Sonnet 5.5 세션) — Claude 중심 전환 후 첫 INVESTMENT 작업
Last PC: work Primary (config/local.json profile=work, pc_check finish 확인; 변경 없음)
Last task: .venv Codex 런타임 의존 제거 후 UI 테스트 점검, 역할 문구 전환, 방법론 질문 Q01~Q10 직접 조사와 승인 후 첫 구현 3건

Completed:
- 2026-11-02 `.venv`를 Codex 런타임(Python 3.12.14)에서 시스템 `C:\Python314`(3.14.7)로 교체. `requirements.lock.txt`와 동일 설치, 옛 환경은 `.venv-codex-backup`(Git 제외)에 보존, 운영 서버 재시작 후 build/source 일치.
- UI 테스트: 공식 `tools/validate_share_candidates.py --ui` 23개 중 `test_dashboard_upgrade_ui`·`test_dashboard_stability_ui`가 날짜(10월) 의존으로 실패 → `page.clock.install`로 시계 고정(`80e3391`) 후 23개 모두 PASS.
- 역할 문구: Claude Code 구현·검증·인수인계, Codex 독립 교차 검토로 INVESTMENT 문서 6개 개정(`de85832`). 다른 프로젝트(credit·PIANO-BLOG·BOND-BLOG·YOUNG-PIANIST·novel)는 각 저장소에 push, STUDIO는 Git 밖 파일 한 줄만 수정.
- ChatGPT Deep Research에 질문을 두 번 보냈으나 검색0·인용0·Q01만 답해 **결과 무효**, 어떤 문서에도 반영하지 않음. 대신 Claude Code가 공식 페이지를 직접 열어 Q01~Q10을 조사해 `docs/review/research_Q01~Q10_*.md` 10개 작성(`dd47f78`, 원본 main 반영·push 완료). 논문은 초록 수준, 확인 불가 항목을 문서마다 명시.
- 문서 정정: `ENVIRONMENT.md`의 `.venv` Python 버전(3.12.14 → 3.14.7).
- 사용자 승인(2026-11-03 "바꿀 건 바꾸고, 전송할 건 전송하자") 후 첫 구현 3건. **신규 파일만 추가했고 기존 코드·설정·투자 규칙·DB는 바뀌지 않았다.**
  - 시도 로그(Q06 T1): `investment/trial_log.py`(append-only·해시 연쇄 JSONL, `.local/trial-log/<profile>.jsonl`, Git 제외)와 `tools/trial_log.py`(record/summary). 아직 어떤 탐색에도 연결·사용되지 않았다.
  - 겹침 포함률 모의 실험(Q07 T1): `tools/overlap_coverage_sim.py`와 결과 `docs/review/result_Q07_overlap_coverage_sim_2026-11-03.md`(합성 자료). 겹침을 무시한 구간의 실제 포함률은 지평 63/126/252일에서 각각 0.71~0.81/0.55~0.61/0.36~0.45였다.
  - 요인 중복 진단(Q09 T1): `tools/factor_overlap_report.py`(요인 간 순위 상관·한 요인 제거 시 상위 N 겹침·점수 미계산 사유). 합성 fixture 실행 후 사용자 승인("실행")으로 **실제 저장 스냅샷에 읽기 전용 실행**했다(SQLite `mode=ro`, 파일 복사 없음, 운영 DB 해시 `10e742e8cd5abe4f…` 전·중·후 동일). 3개 기업 모두 점수 미계산 — **장기 점수 S_long은 현재 실제 자료로는 계산되지 않는다(휴면)**: 실제 적재 경로가 `annual`을 채우지 않아 Q·G·C·V가 결측. 집계는 `docs/review/result_Q09_factor_overlap_real_snapshot_2026-11-03.md`.

Pending:
- **자료 경로 미확정(Q01~Q03)**: 시점별 상장·상폐·상장주식수, DART 공개 시각·정정 빈티지, 조정계수·정산가 공식 경로 미확인. 2008 일별 시총·주식수는 KRX OPEN API(2010~) 범위 밖. 접수시간 개정(2024-04-25, hwp)과 KRX 총수익지수 방법서 미열람.
- **구조 공백**: 시도 로그 모듈은 생겼으나 실제 탐색에 연결되지 않음. 겹침 보정 추론은 합성 모의 실험까지만이고 앱·보고에는 반영하지 않음. 시기별 비용 버전표(Q04)와 계획·코호트 간 집계의 분모 표시(Q10) 없음. 장기 점수 S_long은 실제 자료로 계산되지 않음(위 결과). 현재 순위에 쓰이는 추천 초안 점수(RS·1개월 RS·매출 YoY·ROE)의 구성항 진단은 미실행.
- 사용자 행위 필요: KRX OPEN API 키 신청·약관 동의, OpenDART 키, 법령 시행일별 조문(2008 증권거래세율)·농특세 별표 확인.
- 비공식 UI 테스트 8개 실패 원인 미조사(2개는 8501 Streamlit 필요, 6개는 시계 고정에도 실패), `tests.test_auto_refresh` 5건 실패(옛 `.venv`에서도 동일) 미조사.
- `research_sessions.py`는 agent를 Codex/Claude로만 허용하고 작성자≠검토자를 강제한다. Claude 중심 전환용 재설계 미착수(Claude 산출을 Codex로 표기 금지).
- 주간 연구노트 등록 Codex 자동화(월 09:00, 옛 경로 `신영재\한국\INVESTMENT`)의 Claude 재구성 미착수. 예약 경로가 새 `.venv`로 동작하는지 미확인.
- 유지: home Telegram watch 2회 실수신·최신 코드 수신·과거 home RSS 원인 확인은 이전 인계 기준 미실행. `.venv-codex-backup` 삭제는 며칠 정상 운영 후 사용자 확인. ChatGPT Pro 종료 전 대화 내보내기 여부 미확인.

Next task: 추천 초안 점수 구성항(RS·1개월 RS·매출 YoY·ROE) 진단을 시장 탐색 모집단에서 읽기 전용으로 수행할지 사용자와 정한다.
Next action: 사용자가 승인하면 work Primary의 작업 워크트리에서 `recommendations.propose`가 쓰는 시장 캐시·공통 재무를 읽기 전용(`mode=ro`·파일 복사 없음·운영 DB 해시 전후 비교)으로 읽어 후보 통과 분포와 구성항 간 순위 상관·한 항 제거 시 상위 N 겹침을 내는 진단 도구를 TDD로 추가한다(기존 코드·설정·규칙 불변, 결과는 집계 표만 `docs/review/`에 기록). 병행 결정: 장기 점수 S_long을 시점별 연간 재무 적재(Q01~Q03 이후)까지 휴면으로 둘지, 그 사이 화면·문서에서 품질 점수를 순위 근거로 읽지 않도록 표시를 점검할지. 이후 모든 규칙·임계값 탐색은 `tools/trial_log.py record`로 먼저 기록하고 기록 없이 값 변경을 제안하지 않는다. 사용자 행위가 필요한 항목(KRX/OpenDART 키·약관·법령 조문 확인)은 대신하지 않는다.
Recommended next agent: Claude Code — 구현·검증·인수인계. Codex 교차 검토는 Q01~Q10 문서의 사실 대조(초록 수준 한계 포함)에 한정하며 승인된 기존 검토 계약에 따른다.
Recommended model: 기존 사용자 설정 유지
Recommended reasoning: High (PIT·편향·자료 계약), 단순 문서 정리는 Medium
Escalation condition: 과거자료 부재·정정 vintage/상폐 정산 미확보·동시쓰기/divergence·지표 변경 필요·약관상 보존/재배포 제한 해석(KRX OPEN API) 필요 시 근거를 보존하고 해당 단계 보류
Branch: shinyj0270-afk/invest (재사용 작업 워크트리); main (운영 원본)
Commit: 61fe566907905e68c5967256220da4435a6c5caf (실행 결과 문서 반영 직전 기준, 구현·인계를 push 완료한 SHA)
Remote status: 반영 직전 원본 main·작업본·origin main 모두 61fe566 일치(0/0). 이번 결과 문서·인계 commit/push는 작성 시 verification pending. 최종 보고 및 다음 START 실제 Git로 전송 commit을 확인한다.

Notes:
- 검증(구현): 신규 테스트 `tests.test_trial_log` 5·`test_trial_log_cli` 2·`test_overlap_coverage_sim` 7·`test_factor_overlap_report` 7개 OK. 방향·래그 의존 로직은 일부러 깨뜨려 테스트가 실패하는 것을 확인한 뒤 복원. 관련 기존 `test_dual_pc` 13·`test_research_sessions` 4·`test_research_followup` 8·`test_leader_strategy` 7·`test_portfolio_risk` 14개 OK. `validate_share_candidates.py`(UI 제외) PASS·경고 0. 작업 워크트리에서 `tools/verify_portable.py`를 단독 실행하면 `config/local.json`이 없어 `Explicit matching PC profile required`로 실패하는 것은 기존 동작이며 공식 검증기의 같은 항목은 PASS.
- 검증(앞선 CLOSE 실행): 문서 10개의 상대 링크 존재 확인, `tests.test_dual_pc` 13개·`tests.test_research_sessions` 4개 OK, `git diff --check` 0, `tools/pc_check.py --phase finish` clean(ahead/behind 0, 진행 Git 작업 0, 추적 private 경로 0, 예약 false). 공식 UI 23개 PASS는 `80e3391` 시점 실행 결과이며 이후 코드 변경 없음(문서만).
- 한계: Q01~Q10은 조사 기록이며 지표·비용·배분·임계값 도입 승인이 아니다. 논문 본문 미열람, 네이버 증권·WICS·SSRN은 접근 제한으로 못 열었고 우회하지 않았다. 검색 결과 중 삽입 지시문이 섞인 페이지(cavac.at)는 열지 않았다.
- 원본 반영: 오늘 5회(`80e3391`, `de85832`, `dd47f78`, `c8d8302`, `61fe566`)+이번 결과 문서 1회 예정. 재시작 1회(`61fe566`의 신규 모듈로 `restart_required=true` → 사용자 입력 보관 확인 후 안전 재시작 HTTP 202, build/source 일치·`restart_required=false` 확인). 신규 모듈·도구는 앱이 import하지 않아 동작 변화 없음. 어제 `.venv` 교체 시 서버 재시작 1회. 사용량 교대 0·비용 미집계. ChatGPT Deep Research 2회 실행(구독 한도 소모, 결과 무효).
- `config/share_candidates.json`에는 Codex 검토 문서 3개만 있고 Q01~Q10 문서는 등록하지 않았다(공유 후보 여부는 별도 결정). 중앙 Wiki 수정 없음. 결과 발행·DB/원자료 접근·주문 0.
- 다른 PC(home) 수신·실행 미확인. 집에서는 `fetch` 후 `pull --ff-only`로 문서만 받으면 된다. 내장 브라우저의 ChatGPT 로그인은 사용자가 직접 한 세션이며 계정·설정은 바꾸지 않았다.
- PROJECT_STATE에 이번 전환·조사 항목을 추가했다. 이전 인계(Codex 11-03 검토 블록)는 Git 이력(`3ac6b2c`)에 보존된다.

---

## [보존] home Orca 작업본(`shinyj0270-afk/invest`) 로컬 전용 기록 — 2026-11-02 머지로 원본에 통합

아래는 집 PC Orca 워크트리(`C:\Users\andrew\orca\workspaces\Investment\invest`)에만 있던 반영되지 않은 로컬 기록이다. 원본 main에 커밋/푸시된 적이 없어 이번에 머지하며 보존 목적으로 통째로 옮겼다. 내용은 작성 당시 그대로이며 이후 실제 상태(원격 behind 수 등)와는 다를 수 있다.

### 로컬 CLOSE 기록 — 2026-10-30 (원격 인계 미완료)

Updated: 2026-10-30T21:52:45+09:00
Last agent: Codex
Last PC: home Secondary (기존 사용자 확인 및 이번 pc_check)
Last task: START/CLOSE 점검 및 Orca 재시작 후 미완료 확인
Completed:
- 10/29 pc_check finish: 원본main clean·진행Git작업0·추적개인경로0·예약false. 집 작업본 CURRENT_HANDOFF 기존 미커밋43줄 보존, diff --check PASS. 새 기능/자료/앱 검증은 실행하지 않았다.
- 10/29 실제fetch/ls-remote로 원격2475bd8b76f0f747527829e0e3105b9c2c54592e 확인, 집HEAD4937bb6 대비 behind8/ahead0. 원격 변경에는 동일 CURRENT_HANDOFF와 기능코드가 포함된다. 원격 인계의 RSS수정/운영반영은 회사 기록이며 집수신/실행 성공으로 표시하지 않는다.
- 10/30 재시작 후 HEAD·원격추적ref·로컬인계 상태 재대조: 새commit/merge/push/마감문서 저장이 재시작 전에 없었음을 확인. 이번에는 로컬 마감기록만 추가한다. 기존 인수정정과 과거기록은 아래 보존한다.
Pending:
- 집 미커밋 인계와 원격 최신 인계의 대조·통합 및 최신코드 수신. 자동stash/reset/clean/덮어쓰기/강제push 없음. 원격인계 미완료, 이번재시작 후 원격 재조회는 하지 않았으므로2475bd8은10/29확인 시점이다.
Next task: 로컬 인계정정과 원격 최신인계를 보존하며 대조·통합하는 별도 작업. 완료 전 자동수신/전송 금지.
Next action: 실제Git/원격을 다시 확인하고 양쪽 인계를 비교한다. 10/23 사용자 인포맥스 유지·불필요한 재검증/공급자전환 금지·결과발행보류 결정을 보존한다. 최신기능을 과거 로컬코드로 덮어쓰지 않는다.
Recommended next agent: Codex
Recommended model: 기존 사용자 설정 유지
Recommended reasoning: High (양쪽 인계 대조)
Escalation condition: 동시쓰기·입력충돌·양쪽내용 손실 가능성 시 보존 후 중단
Branch: shinyj0270-afk/invest (home Orca); main (home 원본)
Commit: 4937bb62d6e7b3e2ca3bcba7313fa7c9c739191d (로컬HEAD, 새commit 없음)
Remote status: 10/29 actual main2475bd8, 로컬behind8. 이번CLOSE commit/push 미실행·원격인계 미완료.
Notes: 인계문서만 로컬저장. 제품코드·서버·개인DB/자료·예약·CREDIT·공통Wiki 변경없음. 재사용작업본과 기존로컬변경 보존.

### 집 인수 최종 정정 — 2026-10-23 (로컬 미커밋, 이번 인계 우선)

Updated: 2026-10-23T17:28:30+09:00 (문서 정리; SESSION CLOSE 아님)
Last agent: Codex
Last PC: home Secondary (기존 사용자 확인 유지; 프로필/개발 역할 변경 없음)
Last task: 사용자 최종 인계와 기존 미커밋 인계 대조·정리

Completed:
- 사용자 2026-10-23 최종 정정을 현재 인계 기준으로 정리했다. 아래 이전 세션 인계와 10/22 검증 기록은 이력으로 보존하며 당시 명령·Next action을 새 실행 지시로 사용하지 않는다.
- 사용자 확인(USER_CONFIRMED): 집에서 인포맥스 로그인 및 1333 기관·외국인 순매수금액 조회가 가능하다. 이번 문서 작업에서 직접 로그인·조회를 시험한 것은 아니다. 현재처럼 인포맥스를 이용하는 것을 기본으로 유지하고 기존 네이버/DART 경로·설정도 그대로 둔다.
- 이직 후 이용 가능성은 미정이나 실제 접근 문제가 생기거나 사용자가 별도 요청할 때만 비상 대비를 다룬다. 가능성만으로 인포맥스를 보조로 낮추거나 배제하지 않으며 새 공급자 조사·개발·시험·결제·확인 일정을 추가하지 않는다.
- 기존 가격/재무/수급·추세 partial 기록은 과거 검증 시점의 관찰로 보존했다. 같은 수집·계산·추세 재확인과 이미 완료된 DART·보유 복구·실행기·백업 검사를 이번 인수의 다음 작업으로 반복하지 않는다.

Pending:
- 최신 발행정책 수신/다른 발행 세션 부재 질문은 사용자가 넘어가기로 한 항목이다. 미확인·새 원격 결과 발행 보류를 유지하고 질문/발행 시험을 다시 열지 않는다. 기존 로컬 결과는 보존한다.
- watch 제한 2회·뉴스룸 RSS 등 이전 미해결은 별도 기능 후속이며 이번 인수의 필수 과제로 전환하지 않는다.
- 이 문서의 미커밋 변경은 재사용 작업본에만 있다. 아래 이전 마감 기록을 수정하거나 원본 main·원격에 반영하지 않았다.

Next task: 사용자 다음 실제 작업 지정. 현재 확인 범위에서 이번 인수 때문에 추가로 수행할 필수 작업은 없음.
Next action: 새 작업이 지정되면 기존 정본·현재 작업 상태·승인된 입력 경로를 읽고 그 요청 범위만 수행한다. 이 인계만으로 갱신·전송·설정 변경·역할 전환을 실행하지 않는다. CREDIT 데일리/빌드/서비스/자료/예약은 이번 인수 범위에서 계속 제외한다.
Recommended next agent: Codex (INVESTMENT 실제 작업이 지정된 경우)
Recommended model: 기존 사용자 설정 유지
Recommended reasoning: 기존 프로젝트 기준 유지
Escalation condition: 동시 변경·진행 Git 작업·입력 충돌은 보존하고 해당 변경만 중단
Branch: shinyj0270-afk/invest (집 재사용 작업본); main (원본)
Commit: 4937bb62d6e7b3e2ca3bcba7313fa7c9c739191d (이번 문서 정리 시작 HEAD; 새 commit 없음)
Remote status: 이번 원격 조회·수신·전송 미실행. 캐시된 origin/main을 현재 원격 최신 확인으로 표시하지 않음.
Notes:
- 이번 검증 범위는 인계 내용·기존 이력 보존·diff 확인뿐이다. 과거 앱/자료 검사를 새 PASS로 기록하지 않는다. 원자료·DB·인증·설정·서버·공통 Wiki를 변경하지 않는다.
- 집 보관/회사 점검에 관한 최종 사용자 정정은 이번 인수 판단의 근거이며 회사 상세 보고나 경로 접근을 추가로 요구하지 않는다. 전체 자료 이전 완료·회사 PC 종료·개발 Primary 전환 승인이 아니다.

### 이전 세션 인계 — 2026-10-22 (home, 과거 기록)

- 재사용작업본과 Git제외 검증/로컬자료 보존. 최종push후 clean/원격0/0 확인하고 대화세션 종료, 다음은 같은작업본의 새세션START. 양서버는 사용자사용을 위해 유지한다. 기존다른브랜치는 삭제하지 않는다.
- 제품코드변경0·예약등록0·회사인증/DB복사0·사용량교대0. 실제생성1회, 별도INVESTMENT안전재시작0(기존실행기로준비). Git fixture를 최신자료로 표시하지 않았다.
- 개인원자료·HTML·로그·.local·.venv·영수증은 각PC보존/코드공유제외. 결과Release재발행·중앙Wiki/전체세션수집없음. 이전인계는Git이력/PROJECT_STATE에 보존.

### 2026-10-22 집 인수 점검 기록 (과거; 다음 작업은 당시 계획)

- home Secondary 유지, 최신 main/재사용 작업본 bbf5e0f 안전 수신. 이번 요청은 개발 Primary·정책 전환 또는 CLOSE/commit/push가 아니다. 이 추가 기록은 재사용 작업본에만 있으며 main·원격에 미반영이다.
- 집 DB·입력·보유 캐시 및 연구 DB를 로컬 보존했고 SQLite 일관 백업 무결성 확인. 기존 입력·보유 캐시·설정 해시 유지. 승인된 네이버 검토3종목 갱신1회: 가격10/20→10/21, 관측6개 갱신, 실패종목0. 재무6/30·수급금액9/23은 보존했다.
- 갱신 partial: Yahoo KOSPI 응답의 마지막 유효일10/20과 가격일10/21 불일치. 네 시리즈 공통483개로 관측 수 자체는 충분하다. 추세 cutoff10/20 유지, 임의 추정·검증 완화·반복 수집 없음.
- 새 home 로컬 공개기업 결과 계산·pack/unpack 해시 PASS. 전체시장/검토가격10/21, 검토재무6/30. 실제 오프라인 검색→삼성전자 재무 화면 PASS, JS0·가로넘침0·외부요청0·보유iframe0. 초기 특정기업명 대기 시간초과는 기본 화면에 그 기업이 없는 검사 조건으로 확인 후 실제 검색 UI로 재검증했다.
- 오늘 원격 결과 재발행은 보류: 목적지는 private/ADMIN이고 공통 발행PC=home이나 회사 구버전/다른 발행 세션의 중복 방지 현재 상태는 미확인이다. 기존 서버 시작·중지·재시작·Telegram/DART 실호출·보유전송·CREDIT 작업은 하지 않았다.
- 다음 집 작업: Yahoo KOSPI 완료 관측일이 가격일에 도달했는지 기존 경로의 제한된 재검증으로 확인하고 추세 보류 해소를 판단한다. 회사 신규 결과를 대신 발행하거나 과거 회사 계산 전용 패치를 적용하지 않는다. watch 제한2회/RSS 오류는 이번 필수 기능으로 지정되지 않아 선택 후속으로 남긴다.
- 근거: Git 제외 validation/current/home-final-20261022/receipt.json 및 동 폴더의 갱신·추세·브라우저 개별 영수증. 상세 백업·로컬 결과는 집 개인 이전 기록에 보존. 이번 인수 요청에서는 CREDIT 최신 인계의 다음 행동을 실행하지 않는다.
