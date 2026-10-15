# CURRENT HANDOFF

Updated: 2026-10-15T15:00:19+09:00
Handoff version: 2026-10-15-new-listing-seasoning
Last agent: Claude (Opus 5.5)
Last PC: company Primary (사용자 확인; 원본 config profile=work)
Last task: 재무 공백 기업 제외·기업 목록 최신화·화면 개선, 신규 상장 5개월 편입 규칙

Completed:
- 시작 4dacba99dcd48a017214bc5428801f34cebf2c57, 분리 invest-rev 워크트리(upstream 없음)를 원격 main까지 ff 수신 후 작업. 원본 main/원격 main과 clean 일치 확인.
- 재점검(읽기 전용): 운영 build/source 일치, 격리 검증 16개 PASS·공유360개 경고0, 실제 운영22페이지×1440/390 JS/HTTP 오류·가로 넘침0, 가격2452개 10-14 종가 저장, 재무 실패/일부누락 기록172건.
- 사용자 결정: 검증 재무자료가 없던 6개사(와이즈플래닛컴퍼니·빅웨이브로보틱스·네오사피엔스·한화머시너리앤서비스홀딩스·스카이랩스·글로벌테크놀로지)를 config/excluded_companies.json 사용자 제외 목록으로 발굴·추세·비교·재무 재시도·복구 목록에서 제외. 원자료/가격 이력은 삭제하지 않음. 목록에서 지우면 복구.
- 화면: 홈 결론 카드 상단 정렬, 데스크톱 CSV 버튼을 자료 상태 줄 오른쪽으로 이동(모바일 바 유지), 효과 없는 iframe sandbox 제거로 경고 제거.
- RED→GREEN: test_naver_universe(사용자 제외·형식 검증·공유 목록), test_data_recovery(복구 목록 제외), 신규 test_layout_polish_ui. 최종 격리 검증 17개 PASS·공유362개 경고0.
- 운영: 구현 15841399e8f87009aa28bc0c81151420df74a81a 원본 main ff·안전 재시작202·build/source 일치. 네이버 목록 --listing-only 갱신(조회 2026-09-30→2026-10-15T14:40, 2764개, 신규3·상장폐지/스팩7 제외, 6개사 사용자 제외 저장). 기존 목록 백업 data/work/market-expansion/universe.backup-20261015-before-listing-refresh.json. 실제 운영44화면 오류/넘침/sandbox 경고0, 발굴940개, 복구 목록에 제외 6개사0. 재시작 직후 재무 자동 점검 중 첫 로딩27~33초, 점검 완료 후 5.1~5.3초.

- 후속(사용자 결정): 멜콘(179880)·브릴스(468670) 사용자 제외 추가. 신규 상장은 공식 상장일(FnGuide 기업개요, PC 로컬 market-expansion/listing-dates.json)로부터 5개월 후 발굴 후보로 편입. 가격 이력이 이력 기간 첫날부터 있으면 조회 생략, 상장일 미확보면 확인 대기로 제외. 읽기 시 적용, universe.json·일봉 수집 불변, 재무 자동 수집·복구 목록 대상 아님. RED→GREEN test_listing_seasoning·test_data_recovery. 격리17개 PASS·공유364개 경고0.
- 운영: 구현 8969df67a6043202c1201e2378a64f1f8978aaee 원본 main ff·상장일122개 수집(실패0)·안전 재시작202·build/source 일치. 편입 대기18개(발굴 규모: 마키나락스 10-20, 덕산넵코어스 2027-02-28 편입), 발굴936개. 실제44화면 오류/넘침0. 재시작 직후 수 분은 첫 로딩28~34초, 이후5.2초.

Pending:
- 보유 화면 시장자료 2026-09-23은 인포맥스 단말 일별 Excel 조회·저장(Ctrl+S)이 있어야 갱신된다. 자동 API 없음. 사용자 저장 후 반영 필요.
- 새 기업 목록 갱신 시 tools/expand_market.py --listing-only가 필요한 상장일을 함께 수집한다. 편입 대기 기업은 검색·발굴에서 보이지 않는다.
- 기존 재무 일부누락·원인 미기록 기록, 사용자 기존 탭 새로고침, 집 PC 수신/실행·휴대폰 미확인 유지. 보유 실제 화면은 동기화 차단으로 이번에 검증하지 않음.

Next task: 사용자 새 요청 우선; 인포맥스 저장 후 보유 시장자료 반영
Next action:
1. INVESTMENT START로 Git/PC/원격 main을 확인하고 PROJECT_STATE.md, 이 문서, AGENTS.md, SYNC_CONTRACT.md, docs/DUAL_PC_WORKFLOW.md를 읽는다.
2. 사용자가 인포맥스 일별 파일을 저장했다면 대시보드 새로고침 또는 tools/refresh_infomax.py로 반영하고 보유 화면 시장자료 날짜를 확인한다.
3. 제외 목록 변경 요청은 config/excluded_companies.json만 수정하고 test_naver_universe를 실행한다.

Recommended next agent: Codex (구현·검증); 설계 판단이 필요하면 ChatGPT
Recommended model: 기존 사용자 설정 유지
Recommended reasoning: 기존 설정 유지; 반복 실패·식별 충돌·큰 구조 변경이면 high 검토
Escalation condition: 원본/원격 divergence·예상 밖 로컬 변경·수집 잠금·자료 식별 충돌이면 보존하고 해당 작업 보류
Branch: shinyj0270-afk/invest-rev (분리 개발); 원본 main (통합 완료)
Commit: 8969df67a6043202c1201e2378a64f1f8978aaee (신규 상장 5개월 규칙 구현; 이전 제외·화면 구현 1584139 포함)
Remote status: refs/heads/main 8969df67a6043202c1201e2378a64f1f8978aaee pushed (verified), 2026-10-15T15:00 ls-remote 확인. 이 인계 문서 commit 자체의 전송은 최종 보고/다음 START의 실제 Git 조회로 확인한다. 집 PC 수신/실행 미확인.
Notes:
- 검증 증거는 공유 제외 validation/current/recheck/(live-receipt.json, live-status.json, 화면 캡처)와 polish-validate.log에 보존.
- 인증·PC 설정·보유/현금·DB·원자료·시세·로그는 코드 원격에 넣지 않았다. 입력 쓰기·보유 동기화는 검증 브라우저에서 차단. Wiki/예약/외부 AI 호출 없음.
