# CURRENT HANDOFF

Updated: 2026-10-16T10:16:18+09:00
Last agent: Codex
Last PC: company Primary/work (사용자 확인)
Last task: 네이버 전환·기업분석 개선·Goose 보고서 연결의 로컬 main 통합

Completed:
- 시장자료는 네이버 기본, 재무는 DART 우선·인포맥스 보충. 기존 수급 금액의 자체 기준일과 재무를 보존하고 수량을 금액으로 환산하지 않는다. USER_DATA_DECISIONS §5/8 참조.
- 기업분석 관측 요약·실적/현금흐름·출처 읽기 개선, 재무 확보 상태 기본 접기. 제외5개 심층 분석은 생성하지 않는다. 일부 기업 상세 재무 미확보는 미확보로 유지한다.
- 선택 기업 뉴스/공시를 구분해 제목·출처·시각·링크를 표시, 각20건/10분 캐시·실패 시 정상자료 보존. 기사 영향 분석은 미포함.
- 외부 HTML을 기업별 로컬 등록·정적 격리 열람. 알려진 내장 JSON에서 원문 출처와 작성자 검토 상태를 읽어 표시하며 우리 사실 검증과 구분한다. 사용법 docs/EXTERNAL_REPORTS.md, 지침 대조 docs/GOOSE_APPLICABILITY_AUDIT.md.
- 다운로드/Goose Reports 폴더에서 내장 코드·기업명·as_of로 자동 등록. 서버 실행 중5초 감시·저장 안정 확인, 목록15초 갱신, 원본 보존·오류 표시·줄바꿈/BOM 중복 처리. 읽기 전용은 감시/등록 금지. OS예약·자동 조사·자동 투자판단 없음.
- 운영 실제 SK하이닉스 보고서·출처32개·작성자 limited·폴더중복·모바일/JS오류0 확인. 실제 사용자 보고서의 사실성 재조사는 하지 않았다. 검증 중 만든 줄바꿈 차이 중복은 에이전트 생성분만 되돌리고 사용자 원본 보존.
- 통합 점검에서 보고서 업로드의 지역 LIMIT가 보유 동기화 경로를 가리는 회귀를 발견해 REPORT_LIMIT로 분리. 보유/보고서19검사 통과. 최종 격리 portable·빈 실제모드 AppTest·합성UI 포함18명령 모두 PASS, 공유376개 경고0. 초기 실패를 숨기지 않고 수정 후 전체 재검증했다.

Pending:
- 구현과 최종 검증은 완료. 이 문서를 포함한 명시34파일을 로컬 main 통합 커밋으로 확정하며 clean investment-up을 같은 HEAD로 ff 정렬한다. 실제 통합 SHA와 완료 상태는 Git 조회 및 완료 보고를 기준으로 확인한다.
- 원격 push 미실행. 원격 최신성은 이번 로컬 통합에서 재확인하지 않았다. home 수신/실행·휴대폰·home Telegram·재무 미확보 후속은 별도다.

Next task: 로컬 통합 완료 후 사용자 요청 우선. 원격 인계는 요청 또는 INVESTMENT CLOSE에서 별도로 진행.
Next action:
1. main의 실제 HEAD/status와 이 문서·PROJECT_STATE.md·USER_DATA_DECISIONS.md를 읽는다. investment-up은 main과 ff 정렬한 코드 작업본이며 운영은 바탕화면 원본의 독립 설정/.venv/자료를 사용한다.
2. 기업 간단분석의 외부 분석 보고서 → 폴더 자동 등록에서 이 PC 경로와 상태를 확인한다. 인식 불가 HTML은 수동 등록한다. 다른 PC의 설정·DB·원자료는 복사하지 않는다.
3. 원격 인계 시 승인 origin 확인→검증/제외 확인→원격 차이 확인→충돌 없을 때 일반 push→실제 원격 SHA 확인. divergence 시 보존·중단. 상대 PC 수신과 실행은 별도로 검증한다.

Recommended next agent: Codex (구현·검증), ChatGPT (설계 판단)
Recommended model: 기존 사용자 설정 유지
Recommended reasoning: 일반 후속 Medium, 회귀/공급자 정의 불일치 High 검토
Escalation condition: 다른 쓰기 세션·divergence·자료 식별/단위/날짜 불일치면 기존 자료를 보존하고 반영 보류
Branch: main (회사 바탕화면 운영 원본); shinyj0270-afk/investment-up (분리 코드 작업본)
Commit: 시작 기준 8c62a8f7dde63cdb320434a76c375bf2c9120cd3. 이 문서를 포함하는 이번 통합 commit의 자체 SHA를 미리 쓰지 않으며 실제 Git HEAD로 확인한다.
Remote status: 이번 push 미실행 / 원격 인계 미완료. 이전 원격 main 관측은 8c62a8f이며 현재 최신성 미확인.

Notes:
- 통합 검증에서 찾은 LIMIT 이름 충돌은 REPORT_LIMIT 별칭으로 수정했다. 최종 수정 운영 안전재시작202·build/source 일치 확인.
- PC 로컬 설정·원자료·DB/WAL/journal·보고서·보유내역·로그·검증 산출물은 stage하지 않는다. 코드를 main에 합치는 것과 실데이터를 공유하는 것은 별개다.
- 최신 정책은 DART 재무 우선과 네이버 시장자료 기본이며 과거 인포맥스 우선 문구보다 USER_DATA_DECISIONS가 우선한다.
- 검증 증거는 원본 validation/current와 orca investment-up/validation/current에 로컬 보존한다. 전체 세션/Wiki 자동 공유 없음.
