# CURRENT HANDOFF

Updated: 2026-11-05 (PC 역할 결정 기록 CLOSE, 사용자 지시를 상위 총괄 세션이 전달; 앞서 투자 결정 일지 MERGE·CLOSE 3602646 push 확인)
Last agent: Claude Code (Opus 5.5, 별도 세션)
Last PC: work Primary (DESKTOP-D36HPLT, config/local.json profile=work). 사용자는 이 회사 PC를 2026-11-10까지만 사용
Last task: work Primary 새 회사 PC 이전 결정·일정 기록; 그 전에 투자 결정 일지 추가·검증·반영

Completed:
- **2026-11-02·11-09 주간 연구노트 등록(사용자 "둘 다 등록", 2026-11-09)**: 공개 원문 대조 후 기존 import_weekly_research로 work 로컬 DB에 등록. 신규 31(출처7·카드16·가설4·context4), 재실행 inserted0, catalog 31, DB 82→146행·무결성 ok·기존행 변경0. 가설 THESIS-20261102-01/02, THESIS-20261109-01/02(모두 active=연구 중, 실증 전). 검증본 docs/research/INVESTMENT_MASTERS_WEEKLY_2026-11-02.md, -11-09.md. 집 PC DB에는 반영되지 않음(PC별 DB).
- **PC 역할 결정 기록(사용자 "CREDIT, INVESTMENT은 새 회사 PC를 Primary로, 나머지는 모두 집 PC를 Primary로", "기록 + CLOSE까지", 2026-11-05)**: USER_DATA_DECISIONS.md 20번과 PROJECT_STATE 맨 위 절에 기록. work Primary는 11월 말 설정할 새 회사 PC(인포맥스 설치, 이름 미정)로 이전, home Secondary·결과 발행 PC(home)는 유지. 현재 `DESKTOP-D36HPLT`는 2026-11-10(화)까지 사용, 이후 새 PC 설정 전까지 work Primary 공백·인포맥스 Excel 갱신 중단(DART 원문 재무는 home 가능). 새 PC는 docs/PC_MIGRATION.md 절차(clone, `.venv`, `config/local.json` profile=work 직접 설정), 로컬 DB·인증·private_data·Library DB 자동 복사 없음. `config/local.json`·profile 이름·운영/예약/발행 설정 변경 없음(문서만).
Pending:
- **PIT 파일럿 남은 일**: (a) 동아타이어공업 나머지 연도(FY2018~2022) 문서는 필요할 때만 요청별 승인, (b) 정정공시·연속 연도 빈티지 검증, (c) 문서 받기 명령 정식화, (d) PIT 품질 점수는 V/B가 시점 기록 없는 지표를 써서 불완전. 영업손실 양수 표기 기업은 현재 오류로 멈춘다(규칙 확장 시 계약 테스트부터).
- **자료 경로 미확정(Q01~Q03)**: 시점별 상장·상폐·상장주식수, DART 공개 시각·정정 빈티지, 조정계수·정산가 공식 경로 미확인. 2008 일별 시총·주식수는 KRX OPEN API(2010~) 범위 밖. 접수시간 개정(2024-04-25, hwp)과 KRX 총수익지수 방법서 미열람.
- **구조 공백**: 시도 로그는 S10 민감도 진단 31회(필터 13 + 추세 상수 18)에만 쓰였고 그 밖의 탐색에는 연결되지 않음(앞으로의 임계값 변형은 모두 기록 후 평가). 겹침 보정 추론은 합성 모의 실험까지만이고 앱·보고에는 반영하지 않음. 시기별 비용 버전표(Q04)와 계획·코호트 간 집계의 분모 표시(Q10) 없음. 장기 점수 S_long은 실제 자료로 계산되지 않음(위 결과). 추천 초안 점수 진단은 실행했고 통과 5개뿐이라 점수 가중치가 후보 구성에 영향을 주지 않음(하드 필터 임계값이 실질 결정 규칙).
- 사용자 행위 필요: KRX OPEN API 키 신청·약관 동의, OpenDART 키, 법령 시행일별 조문(2008 증권거래세율)·농특세 별표 확인.
- 비공식 UI 테스트 8개 중 6개는 테스트 취약점으로 규명·수정했고 2개(`test_daily_ui`, `test_viewer_ui`)는 8501 Streamlit 서버가 필요하다. `tests.test_auto_refresh` 5건은 테스트 순서 의존으로 수정했다.
- `research_sessions.py`는 agent를 Codex/Claude로만 허용하고 작성자≠검토자를 강제한다. Claude 중심 전환: agent 라벨과 model ID가 모순되면(Codex+claude 계열, Claude+gpt/codex/o 계열) 가져오기를 거부하는 검사 추가(`label_matches_model`, 테스트·변이 3종 검출). 역할 고정(저자=Claude, 검토자=Codex 강제)은 하지 않음 — 기존 유연성 유지, 사용자 결정 필요 시 별도.
- 주간 연구노트는 11-02·11-09분을 수동 등록했다(자동 등록 아님). 주간 연구노트 등록 Codex 자동화(월 09:00, 옛 경로 `신영재\한국\INVESTMENT`)의 Claude 재구성 미착수. 예약 경로가 새 `.venv`로 동작하는지 미확인.
- 유지: home Telegram watch 2회 실수신·최신 코드 수신·과거 home RSS 원인 확인은 이전 인계 기준 미실행. `.venv-codex-backup` 삭제는 며칠 정상 운영 후 사용자 확인. ChatGPT Pro 종료 전 대화 내보내기 여부 미확인.

Next task: 2026-11-10까지 현재 회사 PC에서 남길 작업은 사용자가 정한다(그 전 마지막 CLOSE로 미전송 0 확인). 새 회사 PC 설정 시 docs/PC_MIGRATION.md로 work 작업본을 새로 만든다. 그 밖의 후보: Codex 교차 검토 결과(PIT 설계 Q01~Q03 등) 반영 범위 결정.
Next action: 사용자가 지정하면 work Primary 작업 워크트리에서 기존 정본·상태를 읽고 그 범위만 수행한다. 이동평균 기간 등 투자 규칙은 S10 진단 결과만으로 바꾸지 않는다. 사용자 행위가 필요한 항목(KRX/OpenDART 키·약관·법령 조문 확인)은 대신하지 않는다.
Recommended next agent: Claude Code — 구현·검증·인수인계. Codex 교차 검토는 Q01~Q10 문서의 사실 대조(초록 수준 한계 포함)에 한정하며 승인된 기존 검토 계약에 따른다.
Recommended model: 기존 사용자 설정 유지
Recommended reasoning: High (PIT·편향·자료 계약), 단순 문서 정리는 Medium
Escalation condition: 과거자료 부재·정정 vintage/상폐 정산 미확보·동시쓰기/divergence·지표 변경 필요·약관상 보존/재배포 제한 해석(KRX OPEN API) 필요 시 근거를 보존하고 해당 단계 보류
Branch: shinyj0270-afk/invest (재사용 작업 워크트리); main (운영 원본)
Commit: 360264662a0d5f415011d1202c73de47211a7249 (이번 기록 직전 기준; 투자 결정 일지와 그 인계 기록을 push 완료한 SHA)
Remote status: 3602646은 HEAD·origin/main·ls-remote main 일치로 pushed (verified). 이번 PC 역할 기록 commit은 작성 시 not pushed / verification pending이며 최종 보고와 다음 START의 실제 Git 조회로 확인한다.

Notes:
- 과거 완료·검증·로컬 인계 원문: [HANDOFF_HISTORY_2026-11-06.md](docs/archive/HANDOFF_HISTORY_2026-11-06.md). 당시 기록이며 최신 실행 증거가 아니다.
