# CURRENT HANDOFF

Updated: 2026-10-19T14:15:00+09:00
Handoff version: 2026-10-19-research-drop-folder
Last agent: Claude (사용자 요청으로 회사 재발행 단계 수행)
Last PC: company Primary/work (원본 config/local.json profile=work 확인)
Last task: 회사 조회 결과 재발행 + 자료 투입 폴더(자료 확인 모드) 추가

Completed:
- START 점검: 원본 main·invest·origin/main·remote main=d49e652(Codex CLOSE 기록) clean·0/0, 운영 build=source=8d6cfcc311518b042cf1e599fc6aa90e191f9ce37e024a6411c659dae4c5666e·restart_required=false.
- 첫 발행 시도(13:41)는 운영 서버 자동 종가 갱신이 13:42:12에 refresh snapshot·daily-latest·research.sqlite3를 기록해 "결과 생성 중 코드·자료 변경" 보호로 중단(이전 결과 유지). 갱신 완료(daily-refresh-status complete, 새 완료 거래일 없음) 확인 후 재실행 성공.
- 발행: tag results-20261019T045455Z-627039e4a5b9, 자료기준 2026-10-16, 생성 2026-10-19T04:54:55Z, source_build 8d6cfcc3…(운영 build와 일치), HTML 119,015,812 bytes, SHA256 627039e4a5b92a30f901b6bc6139e90459df4c167b57a848213339b799db4174.
- 원격 검증: invest-results-private PRIVATE·ADMIN, release draft=false·latest=새 tag, asset dashboard.html.gz 89,695,428 bytes(sha256 456a6634…)·manifest.json 353 bytes(sha256 6c5c7e15…). 다운로드 해시가 asset digest와 일치하고, 압축 해제 HTML SHA·크기가 manifest와 일치.
- 결과 HTML 오프라인 열람: 산업 연구 화면·영업이익 증가 기업 비중 포함, 연구 영역 "연구자료가 포함되지 않습니다", Research Library 메뉴 숨김, 외부 요청0·JS오류0·1440/390/320px 넘침0. 확인용 다운로드 파일은 삭제.
- 새 수집·AI 조사·DB/설정 복사·자동 발행 설정 변경 없음.
- 자료 투입 폴더(사용자 결정 2026-10-19): 회사·집 모두 `다운로드/INVESTMENT 자료`(local.json `research_drop_inbox`로 변경 가능). START 4-1단계와 `자료 확인` 호출 때 AI가 미처리 파일을 읽고 report/library/thesis/archive 선택지를 제시, 사용자 선택 후에만 등록. 처리 기록은 PC별 `.local/research-drop/<profile>/ledger.json`(내용 SHA256 기준), 원본 이동·삭제 없음, 예약 없음. 문서 docs/RESEARCH_DROP.md, 스킬 자료 확인 모드, AGENTS 호출어.
- 검증: tests.test_research_drop 등 관련 unittest 78개 OK(skip2), 격리 공유394개 경고0·portable/AppTest PASS. 구현 d5e1458 ff 반영·/restart 202·build=source 782365b3…·restart_required=false·대시보드 HTTP200, push 확인. 회사 PC에 폴더 생성·status pending0 확인.

Pending:
- home 수신·열람·조회모드 전환은 미실행(home PC 필요).
- ROIC/WACC·마진 변화·수주 등 미확보 유지. 월요일09:00 inbox 점검·ChatGPT→inbox 자동 수신 미연결·Telegram·재무/휴대폰 후속은 변경 없음.

Next task: home에서 새 회사 결과 수신·열람 확인 후 조회 모드 전환
Next action:
1. home PC에서 INVESTMENT START. 최신 코드 ff-only 수신(d5e1458·이 기록 commit 포함), docs/SHARED_DASHBOARD.md 확인. START 4-1에서 home의 `다운로드/INVESTMENT 자료` 폴더가 생성·확인된다(투입 자료가 있으면 선택지 제시).
2. home .venv로 `tools\shared_dashboard.py open` 실행. tag results-20261019T045455Z-627039e4a5b9·자료기준 2026-10-16·SHA256 627039e4…4174 일치와 산업 연구 화면·영업이익 증가 비중 표시를 확인한다. 회사 수집·계산·AI 조사는 반복하지 않는다.
3. 실제 수신/열람 성공 뒤에만 home 원본 config/local.json에 shared_dashboard.enabled=true 설정. 실패 시 기존 결과 보존·전환 PENDING 유지.
Recommended next agent: Codex 또는 Claude (home 수신·검증)
Recommended model: 기존 사용자 설정 유지; 자동 전환 없음
Recommended reasoning: Medium; 해시·날짜·권한 불일치는 High
Escalation condition: 다른 쓰기·미커밋 충돌·원격 divergence·해시/자료일 불일치·개인정보 경계 의심이면 보존 후 중단
Branch: shinyj0270-afk/invest (재사용 Orca); main (회사 원본 운영)
Commit: d5e1458fa5e1d924f72fedc2b47630318e3569b0 (자료 투입 폴더 구현·운영 반영 기준)
Remote status: refs/heads/main=d5e1458fa5e1d924f72fedc2b47630318e3569b0 pushed (verified 2026-10-19 14:14 KST). 이 인계 기록 commit 자체의 전송은 최종 보고·다음 START의 실제 Git 조회로 확인한다. 결과 발행은 코드 push와 별개로 위 원격 Release 검증 완료.

Notes:
- 발행 로그·결과 열람 스크립트·스크린샷은 Git 제외 validation/industry-dev에 보존(publish.log=중단 기록, publish2.log=성공).
- 운영 서버가 열려 있으면 자동 종가 갱신과 발행 시점이 겹쳐 보호 중단될 수 있다. 갱신 완료 후 재실행하면 된다.
- DB/WAL·원자료·설정·인증·보유·연구노트·Telegram은 결과·코드에 포함하지 않았다. 주문/매매/잔고 조회·예약·외부 모델 호출 없음.
