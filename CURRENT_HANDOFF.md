# CURRENT HANDOFF

Updated: 2026-10-20T10:56:44+09:00
Handoff version: 2026-10-20-work-credit-switcher-merged
Last agent: Codex
Last PC: work Primary (기존 profile 유지)
Last task: 상단 로고에서 주식·채권 크레딧 전환 구현·운영 반영·전송

Completed:
- 상단 INVESTMENT 선택 → 주식/채권·크레딧 전환 구현. 주식 DOM과 CREDIT iframe을 유지해 각 입력·선택을 보존한다. 기존 CREDIT loopback4580 식별 확인 후 연결, 미실행/잘못된 응답 안내·재시도. CREDIT 코드·Excel·빌드·예약은 변경하지 않았다. 오프라인 회사 결과/읽기 전용 서버는 로컬 CREDIT 연결 없음.
- 관련 unittest17개, 전환 UI, 공유425개 경고0·portable/빈 실제모드/합성UI24명령 PASS. 실제 CREDIT 연결 및 실제 운영 전환·주식 복귀·1440/390/320px·JS오류0·바깥 넘침0(보유/개인 연결·쓰기 요청 차단 브라우저) PASS. 증거는 validation/current/credit-switcher-operation-*.png 및 share-candidate-review.json.
- 2f8bdaf2fdf7c2553877a05805374ac780d0be9f 원본 main ff-only 반영·/restart202·실행/소스 build ac87a34de66e88ab9abd6ae6dca46f2ad2782807eb963eb7a22c6c024b4315ee 일치·restart_required=false·push·실제 remote SHA 일치 확인. 이전 동일 세션의 사용자 입력 보관 완료·재시작 확인을 적용했다.
- 앞선 배포 HTML 소스 일치 복원·회사 결과 발행은 완료 상태 유지. 결과 tag results-20261019T230634Z-efa2efff53d7, 자료기준2026-10-16, HTML SHA256 efa2efff53d7d6d261f31e9a5cd504ede4fc7d01f8e18e471e65e6c4ecb68547. 이번 기능으로 결과를 다시 발행하지 않았다.

Pending:
- 별도 기존 보유 iframe 오류: 실제 입력의 종목당 출처 최대75개와 src/engine.js validateSnapshot의50개 제한 불일치. 전환 모듈 없는 보유 HTML 단독으로 동일 오류 재현. 크레딧 전환 기능과 구분하며 이번에 출처 절삭·검증 우회·데이터 변경을 하지 않았다.
- home 최신 결과 수신·열람 미확인. Telegram 실제 채널 확인·소량 실수신은 사용자 결정대로 집 PC에서 진행한다. 2단계 수신기 구현 완료, 실제 연결·3단계 연구 연결 미실행.
- 2026-10 운영 점검 및 기존 ROIC/WACC·마진/수주·국면/전략 기준값·HRP/사후성과·ChatGPT→inbox 자동수신 등 범위 밖 pending 유지.

Next task: 회사 기존 보유 iframe 출처 개수 검증 오류를 별도 범위로 수정 (새 사용자 지시 우선)
Next action:
1. START 후 최신 상태와 src/engine.js, src/ui.js, investment/workspace_export.py의 export_holdings_frame, Python snapshot 계약을 읽고 출처 한도를 대조한다.
2. validation/current/check_legacy_source_limit.py의 기존 단독 프레임 재현을 확인한다. 출처75개 입력으로50개 제한 오류를 고정하는 합성 회귀를 만든 뒤 원문 출처를 보존하는 호환 경계를 설계한다. 임의 절삭/완화로 숨기지 않는다. 이번 기록은 수정 승인이나 착수 완료를 뜻하지 않는다.
3. 집 PC에서는 기존 결과 수신/해시/열람만 확인하고 회사 계산·AI 조사를 반복하지 않는다. Telegram은 docs/TELEGRAM_COLLECTION.md에 따라 집 환경변수에 토큰 직접 입력→discover 확인→expected_id 잠금→poll 소량 검증. 토큰을 채팅/코드에 넣지 않는다.
Recommended next agent: Codex (회사 출처 계약/회귀), 사용자 (집 Telegram 토큰·채널 식별)
Recommended model: 기존 사용자 설정 유지; 자동 전환 없음
Recommended reasoning: Medium; 출처 보존 계약·실데이터 경계 불일치는 High 검토
Escalation condition: 원격 divergence·동시쓰기·출처 손실 위험·PC 경로 결합·채널 식별/인증 문제이면 해당 작업 보존·보류
Branch: shinyj0270-afk/invest (재사용 Orca); main (work 원본)
Commit: 2f8bdaf2fdf7c2553877a05805374ac780d0be9f (검증·반영·push 완료한 화면 전환 구현 SHA; 이 후속 기록의 자기 SHA 아님)
Remote status: refs/heads/main=2f8bdaf2fdf7c2553877a05805374ac780d0be9f pushed (verified, HEAD=origin/main=실제 remote main 확인). 이 후속 문서 기록 자체의 전송은 최종 보고 및 다음 START 실제 Git 조회로 확인한다.

Notes:
- 작업 워크트리는 재사용하며 이번 작업은 CLOSE가 아니다. 중앙 Wiki 수정·전체 세션 공유·자동 /wiki-sync·예약 변경 없음.
- 최초 운영 전환 검사에서 보유 iframe50개 오류가 함께 포착되어 전체 JS오류0으로 보고하지 않았다. 전환 모듈 없는 보유 HTML에서 별도 재현한 뒤, 보유 연결을 차단한 운영 전환 검증의 JS오류0만 완료 범위로 기록했다.
- 반영 직전 fetch 권한 실패 후 다음 명령이 이어진 절차 오류는 허용된 실행으로 원격4cc434c·로컬1/0 재확인 후 운영 검증·push로 마무리했다. 원격 덮어쓰기·자동 병합·강제 작업은 없었다.
