# INVESTMENT 상태 요약

마지막 갱신일: 2026-11-09 (결함 수정 6b988af·Codex 핵심 로직 검토 기록)

## 현재 상태
- work Primary는 11월 말 설정할 새 회사 PC로 이전 예정. 현재 회사 PC는 2026-11-10까지 사용하며 home Secondary·결과 발행 PC(home)는 유지한다.
- 2026-11-09 Codex 지적 결함 3건(휴대폰 게이트웨이 인코딩 우회, 같은 초 백업 보존, 빈 백업 검증)을 고쳐 6b988af로 push 확인. 운영 서버는 미실행이라 재시작 없음.
- Codex 핵심 로직 검토 7건은 코드 수정 없이 [검토 기록](docs/review/review_codex_core_logic_2026-11-09.md)에 후속 과제로 남김.
- 근거: [PROJECT_STATE](PROJECT_STATE.md) 맨 위 「PC 역할」「투자 결정 일지」 절과 [현재 인계](CURRENT_HANDOFF.md). 원격 최신성과 실행 상태는 실제 Git/PC 조회가 필요하다.

## 다음 할 일
- 2026-11-10까지 남길 작업은 사용자 지정 대기. 새 PC 설정 후 첫 코드 작업 후보는 검토 3·4·5번(테스트 먼저). 새 PC 설정은 [PC 이전 절차](docs/PC_MIGRATION.md). Next action·권장 담당·중단 조건은 [현재 인계](CURRENT_HANDOFF.md).

## 미해결
- 검토 1·2번(수기값 접수번호 귀속, 정정본 반영)은 PIT 설계 결정 필요. PIT 자료 경로·정정 빈티지·연속 연도 검증, 사용자 키/약관, home 수신·Telegram/RSS 후속은 [현재 인계 Pending](CURRENT_HANDOFF.md).

## 핵심 결정과 근거
- PC 이전 시 로컬 DB·인증·private_data 자동 복사 없음, profile 이름 변경 없음: [PROJECT_STATE 최신 PC 역할 절](PROJECT_STATE.md), [사용자 결정 20번](USER_DATA_DECISIONS.md).
- 이동평균 등 투자 규칙은 S10 진단만으로 변경하지 않는다: [현재 인계](CURRENT_HANDOFF.md).
- 전체 상태 원본은 PROJECT_STATE, 다음 실행 기준은 CURRENT_HANDOFF다. 이 요약과 충돌하면 원본을 우선한다.
