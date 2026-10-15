# CURRENT HANDOFF

Updated: 2026-10-15T09:20:40+09:00
Handoff version: 2026-10-15-navigation-company-recovery
Last agent: Codex
Last PC: 원본 work (Primary); 개발 워크트리 unknown (설정 없음)
Last task: 메뉴 직접 표시와 SK가스 기업 조회 실패 수정·검증·운영 적용 준비

Completed:
- 사용자 지정 shinyj0270-afk/investment-up 워크트리에서 구현. 시작 기준55ce2d14f0f7d725b6dac3d0f52b501a9b4947e4; 원본 main과 시작 시 같은 commit/clean. 원본 설정/.venv/개인 데이터는 복제하지 않고 같은 PC 기존 .venv를 검증 런타임으로 사용.
- 데스크톱 기본6+추가4 메뉴를 직접 표시. 더보기 클릭 제거, 검색/종가와 메뉴 행 분리, 좁은 화면 줄바꿈·900px 이하 기존22개 목적지 선택기 유지. 아이콘10개·키보드·대비/44px 조작 영역 확인.
- 실제 dashboard/company-view가 HTTP503으로 실패하고 서버 다시 실행 필요 응답을 반환함을 재현. 운영 build/source 불일치. SK가스 CFS 분기6·연간1·가격253개가 저장되어 있어 자료 소실과 구분.
- 기업 지연 조회에20초 제한, 실패/재시작 필요 안내·명시 재시도·탭 전환 시 실패 상태 유지·진행 요청 재사용 적용. 실패가 계속 조회 중으로 보이거나 Promise 거절이 빠지는 문제 회귀.
- 이번 직접 새 검증:503→실패 표시→탭 전환→재시도→추세/상세 연결, 응답 지연 종료, 데스크톱8폭/390·320px, 홈 키보드·대비·22개 모바일 목적지, 위험·상세 UI PASS. 격리 공유358개 경고0·portable27명령·빈 실제 모드 AppTest·합성UI12여정 PASS. 적용/실제 화면 확인은 별도이며 과거 검사를 재실행으로 복사하지 않음.
- 기존 공식 원문 반영 유지: 와이즈/빅웨이브/네오 CFS·글로벌 OFS 총11기간. 원본 재무/실패/PC설정3230개 파일의 반영 시 해시 보존 증거는 validation/current/official-statements/applied.json. 이전 구현/인계 commit1294157/55ce2d1은 원본 main 통합 완료·원격 미전송 상태로 보존.
- 사용자 추가 지시: 수정 검증→원본 main 반영→안전 재시작→실제 SK가스 확인→원격 push 순서 승인. 원격 전송 범위는 검증한 공유 코드·테스트·인계 문서이며 개인 자료/원문/전사본/수치·로그는 제외.

Pending:
- 열린 탭 작성 내용 보관 확인을 요청한 상태. 안전 재시작은 그 확인 후 기존 /restart의 인증·활성 수집·OS 잠금 검사로 실행. 확인 전 drafts_saved=true를 임의 선언하거나 서버 프로세스를 강제 종료하지 않는다.
- 최종 수정의 원본 main 통합, 운영 재시작·실제 HTTP/화면·최신 제공 시세 갱신, 원격 push와 원격 SHA 확인은 아직 대기.
- SK가스 PER/PBR는 저장 시세10-02와 완료종가10-14 날짜 차이로 보류. 날짜 검증을 완화하지 않고 실제 최신 제공 시세 조회 후 확인한다.
- 글로벌08-19 정정 사본의9월 최신성·빅웨이브2024 대시 표시, 스카이 전체/한화 설립 후 실제 원문, 누락 단독분기·TTM·ROE·기존 실패6/과거3/일부누락163 후속 유지. 실패 수를 임의로 해소하지 않는다.
- home Telegram·집 PC 수신/실행·Orca 목록·연구설계 효과 실증은 기존 후속. 보유/DB/키/PC설정/예약·LLM/API 추가 비용·Wiki 변경 없음.

Next task: 검증한 수정본의 원본 main 통합과 안전 재시작 후 실제 SK가스 UI 확인·원격 전송
Next action:
- 실제 Git 상태와 원본 main을 확인하고 검증 소스 해시를 대조해 명시 파일만 commit·fast-forward 통합한다. 변경/충돌이면 보존하고 중단.
- 사용자 입력 보관 확인 후 기존 안전 재시작. health build/source 일치·dashboard/company-view200, SK가스 금액·추세253개/차트·재무 상세·모바일/데스크톱을 실제 저장자료로 확인. 새 테스트 브라우저의 개인 입력 쓰기는 차단한다.
- 최신 제공 시세를 기존 공개 조회 경로로 갱신한 뒤 PER/PBR의 날짜·출처·근사 한계를 확인한다. 기존 완료 일봉/재무 값을 덮어쓰거나 가상 값으로 성공 처리하지 않는다.
- 실제 검증 결과를 이 문서에 기록하고 공유 제외·staged diff·원격 재확인 후 main push 및 실제 원격 SHA 확인. 집 PC 수신/실행은 별도.

Recommended next agent: Codex (운영 복구 확인 및 구현 마감)
Recommended model: 기존 사용자 설정 유지
Recommended reasoning: 기존 설정 유지; 반복 실패/자료 식별 충돌이면 high 검토
Escalation condition: 입력 보관 미확인·수집 잠금·원본/원격 divergence·기업/기간 식별 충돌이면 해당 실행 보존·보류
Branch: shinyj0270-afk/investment-up (수정 개발); 원본 main (수정 통합 대기)
Commit: 55ce2d14f0f7d725b6dac3d0f52b501a9b4947e4 (이번 작업 시작 기준; 새 수정 commit 생성 전)
Remote status: origin/main 2b7fc78645e3e1c0da30d0204f4b4f8b0c5d7b8f, 09:20 KST 원본 clean main에서 fetch 성공; 기존 main ahead2/behind0. 이번 수정 not pushed. 사용자 승인 순서에 따라 운영 확인 후 push 예정. 집 PC 수신/실행 미확인.
Notes: 증거는 Orca validation/current/skgas-debug와 share-candidate-review.json에 로컬 보존. 실제503 재현·실제 저장 자료 조회·합성 회귀·운영 적용을 구분한다. 과거 정기재무 실패·개인 입력·소스 권한 거부는 유지. 후속 기록 commit의 자기 SHA는 미리 쓰지 않고 최종 Git 조회로 검증한다.

## 작업 폴더 기준
- 오늘 개발은 사용자 지정 워크트리, 검증 후 원본 main으로 통합한다.
- 워크트리 삭제는 사용자 확인 후만 한다.
