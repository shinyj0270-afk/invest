# CURRENT HANDOFF

Updated: 2026-11-09 KST (미병합 브랜치 2개 기록 추가; CLOSE 아님)
Last agent: Claude Code (Opus 5.5, 상위 세션이 시작한 별도 세션)
Last PC: work Primary (DESKTOP-D36HPLT). 이 PC는 2026-11-10까지 사용
Last task: Codex 검토 지적 결함 3건 수정·반영(6b988af), Codex 핵심 로직 심층 검토 7건을 후속 과제로 기록

Completed:
- **Codex 검토 결함 3건 수정(사용자 "1~3번만 고치기", "Saved, go ahead", 2026-11-09)**: (1) `scripts/mobile_dashboard.py` 휴대폰 게이트웨이가 `/holding-market` 쿼리를 `parse_qs`로 해석한 이름으로 검사해 `%72efresh=1` 같은 인코딩 우회를 403으로 막음. (2) `investment/data_backup.py` 같은 초 백업 순서를 시각+숫자 접미사로 판단, 보존 정리로 비워진 접미사 재사용 금지, 방금 만든 백업은 삭제하지 않음. (3) `verify_backup()`이 빈 `files` 목록을 실패로 처리(CLI 종료 코드 1). 새 테스트 5건이 수정 전 실패·수정 후 통과. 전체 `python -B -m unittest discover -s tests -p "test_*.py"` 1643건 중 1641 통과·3 skip·2 오류(`test_daily_ui`·`test_viewer_ui`, 8501 서버 필요한 기존 항목). `tools/validate_share_candidates.py` 통과(453 경로, flagged 0). 원본 main `--ff-only` 반영, 운영 서버(8767)·휴대폰 게이트웨이 미실행이라 재시작 없음(다음 실행 때 새 코드 적용, 실행 확인 안 함).
- **Codex 핵심 로직 심층 검토 기록(사용자 "둘 다 기록", 2026-11-09)**: [review_codex_core_logic_2026-11-09.md](docs/review/review_codex_core_logic_2026-11-09.md)에 7건(높음 1·중간 4·낮음 2) 기록. 코드는 고치지 않음. 원본 보고서는 로컬 절대 경로가 있어 저장소에 넣지 않고 항목·근거만 옮김.
Pending:
- **미병합 브랜치 2개(새 회사 PC에서 검토 후 병합 여부 결정)**: (a) `origin/fix/astra-2026-11-09` `7ab8111`: 아래 후속 3·4·5번 수정안과 테스트(7개 파일 +134/−16). 착수 전 이 브랜치부터 확인. (b) `origin/feat/market-flows-2026-11-09` `cd1e12c`: Codex 구현 시장 자금 흐름 화면(네이버 투자자별 순매수 수량/거래량, ICI 미국 주간 펀드 흐름, [MARKET_FLOWS.md](docs/MARKET_FLOWS.md)는 브랜치에만 있음). Claude Code 확인: 수급 6·인포맥스 9 테스트와 관련 UI·휴대폰·라이브 테스트 통과, 미래 행 주입 시 테스트 실패 확인. 전체 테스트·브라우저 화면·실제 네트워크 갱신은 미확인. 흐름 표시 전용이며 선행성·적중률 미검증, ETF 기관 매매에는 LP 거래가 섞임.
- **Codex 핵심 로직 후속 7건(착수: 11월 말 새 회사 PC 설정 후)**: 1(수기 재무값이 접수번호 무관 주입, `pit_xml_accounts.py:34`)·2(`pit_pool._first_versions` 정정본 제외)는 PIT 설계 결정 필요(아래 PIT 항목과 연결). 3(`trend.py:13` 일반 prices 경로 stale 통과)·4(`valuation.py:94` 첫 후보만 검사)·5(`financial_table.py:91-93` 정정 이력 시 표 비움)는 수정 범위 작음, 테스트 먼저. 6(PER/PBR 출처 우선순위 문서)·7(탐색 시총 하한 문서 850억 vs 코드 1,500억 초과)은 문서 정정.
- **백업 후속(이번 범위 밖)**: `data_backup`이 SQLite 보조 파일(-wal·-shm)을 따로 다루는지 Codex 지적 4번은 미착수.
- **PIT 파일럿 남은 일**: 나머지 연도 문서 요청별 승인, 정정공시·연속 연도 빈티지 검증, 문서 받기 명령 정식화, PIT 품질 점수의 V/B 시점 미기록. 수기값 접수번호 귀속·`PARSER_VERSION` 재생성 정책 미정([result_PIT_parser_fixes_2026-11-05.md](docs/review/result_PIT_parser_fixes_2026-11-05.md) 미해결 5·7).
- **자료 경로 미확정(Q01~Q03)**: 시점별 상장·상폐·주식수, DART 공개 시각·정정 빈티지, 조정계수·정산가 공식 경로. 상세는 [이전 인계](docs/archive/HANDOFF_HISTORY_2026-11-09.md).
- 사용자 행위 필요: KRX OPEN API 키·약관, OpenDART 키, 법령 시행일별 조문 확인.
- 유지: 주간 연구노트 자동화 Claude 재구성 미착수, home Telegram/RSS 후속 미실행, `.venv-codex-backup` 삭제 대기, home PC의 6b988af 수신·실행 미확인.

Next task: 2026-11-10까지 현재 회사 PC에서 남길 작업은 사용자가 정한다. 새 회사 PC 설정 후 첫 코드 작업 후보는 Codex 핵심 로직 후속 3·4·5번(테스트 먼저).
Next action: 사용자가 지정하면 work Primary 작업 워크트리에서 [review_codex_core_logic_2026-11-09.md](docs/review/review_codex_core_logic_2026-11-09.md)의 해당 항목을 읽고, 회귀 테스트로 수정 전 실패를 확인한 뒤 고친다. 1·2번은 정정 처리 방식(사용 차단 vs 불완전 이력 표시)과 수기값 귀속을 사용자와 먼저 정한다. 6·7번은 현재 코드 기준인지 사용자 확인 후 문서를 고친다. 완료 판정: 새 테스트 통과·전체 스위트 결과·`git diff` 검토.
Recommended next agent: Claude Code — 구현·검증·인수인계. Codex는 승인된 기존 검토 계약에 따른 교차 검토만.
Recommended model: 기존 사용자 설정 유지
Recommended reasoning: High (PIT 정정·빈티지 설계), 3·4·5 수정과 문서 정정은 Medium
Escalation condition: 정정 처리 방식이 점수·후보를 바꾸는 경우, 수기값의 원문 접수번호를 확인할 수 없는 경우, divergence·동시쓰기 시 근거를 보존하고 보류
Branch: shinyj0270-afk/invest (재사용 작업 워크트리); main (운영 원본)
Commit: 6b988af444bac6ea9a686ecd6959237fbd991c42 (결함 수정 3건 구현 commit)
Remote status: 6b988af는 HEAD·origin/main·ls-remote main 일치로 pushed (verified, 2026-11-09). 이번 검토 기록 commit은 작업 워크트리 브랜치에만 있고 not pushed(CLOSE·MERGE 요청이 아니라 원본 main 반영·push 보류). 다음 MERGE/CLOSE에서 반영하고 실제 Git 조회로 확인한다.

Notes:
- 이번 원본 반영 1회, 운영 재시작 0회(서버 미실행). 사용량 교대 없음. 인계 누락으로 인한 재질문·재작업 미확인.
- 전체 테스트는 `discover -s tests -t .`로는 `tests/`에 `__init__.py`가 없어 시작되지 않는다. `-s tests -p "test_*.py"`를 쓴다.
- 과거 완료·검증 원문: [HANDOFF_HISTORY_2026-11-09.md](docs/archive/HANDOFF_HISTORY_2026-11-09.md), [HANDOFF_HISTORY_2026-11-06.md](docs/archive/HANDOFF_HISTORY_2026-11-06.md). 당시 기록이며 최신 실행 증거가 아니다.
