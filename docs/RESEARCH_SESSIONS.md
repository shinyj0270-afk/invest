# 기존 Codex/Claude 세션으로 연구하기

2026-10-14 사용자 결정: 추가 비용을 내지 않는다. API 연결 계획은 철회했다. `agent_providers.generate/worker`와 기존 API CLI run은 키가 있어도 차단한다. 키 탐색·생성·설정은 다음 작업이 아니다.

현재 Codex 세션이 구현·검토를 맡고 기존 Claude 세션이 초안·보조 검토를 맡는다. 자료와 결과를 로컬 파일로 주고받으며 Python은 자료 검증·단계·저장만 관리한다. 별도 Codex 설치, 구독 변경, 유료 API, 자동 재귀 호출은 필요하지 않다. 최초 역할은 바꿀 수 있지만 초안과 검토는 서로 다른 agent여야 한다.

기존 구독 로그인이어도 추가 사용량/usage credits가 켜져 있으면 한도 초과 후 추가 비용이 발생할 수 있다. Claude 설정 → 사용량에서 추가 사용량을 꺼 두고 한도 소진 시 중단한다. 계정 설정을 확인하기 전에는 자동 모델 호출을 하지 않는다. CLI의 --max-budget-usd나 명령 숨김을 구독 과금 차단 장치로 간주하지 않는다. API 키를 환경에 주입하지 않는다.

## 실행 흐름

기존 docs/RESEARCH_AGENTS.md의 입력 형식과 공개 source ID 검증을 재사용한다. 입력·초안·결과는 .local 아래에 둔다. 기존 .venv에서:

```powershell
python tools/research_sessions.py prepare --input .local/agents/input.json
python tools/research_sessions.py packet --run-id RUN_ID
```

packet의 제한된 입력을 기존 Claude 또는 Codex 세션에서 처리한다. 세션은 프로젝트 지침을 읽고 사람이 고른 공개 관측만 사용한다. 결과 envelope는 아래 형식으로 .local/agents/draft.json에 저장한다. value는 packet에 명시된 JSON 구조다. agent/model 표시는 세션에서 제공한 기록이며 독립 인증이 아니다.

```json
{"agent":"Claude","model":"unknown","value":{"title":"...","hypothesis":"...","conditions":["..."],"invalidation":["..."],"claims":[{"statement":"...","stance":"context","source_ids":["SOURCE_ID"]}],"missing_evidence":["..."]}}
```

```powershell
python tools/research_sessions.py draft --run-id RUN_ID --input .local/agents/draft.json
python tools/research_sessions.py packet --run-id RUN_ID
```

두 번째 packet을 다른 기존 세션이 검토한다. review.json은 agent/model/value envelope이며 value는 verdict(pass 또는 revise), issues(문자열 배열), summary(문자열)다.

```powershell
python tools/research_sessions.py review --run-id RUN_ID --input .local/agents/review.json
python tools/research_sessions.py show --run-id RUN_ID
python tools/research_sessions.py approve --run-id RUN_ID --input .local/agents/approval.json
```

최종 approve는 사람이 정확한 review_digest와 검토자/일자/확인 필드를 직접 검토한 뒤 실행한다(기존 RESEARCH_AGENTS.md의 승인 JSON). 초안은 자동으로 curated/활성 가설이 되지 않는다. agent_note 기록과 기존 운영 연구자료는 구분한다. 실행 이력은 `.local/agents/session-runs/{profile}/user_input`에 보존한다. 실패/강제종료 후 남은 transition.lock은 진행 중 프로세스 확인 뒤 수동 복구한다. 기존 API run과 섞지 않는다.

모델 검토 결과가 revise이면 packet에 기존 초안과 수정 사유가 포함된다. 원래 작성 에이전트가 수정한 전체 draft envelope를 제출한다.

```powershell
python tools/research_sessions.py packet --run-id RUN_ID
python tools/research_sessions.py revise --run-id RUN_ID --input .local/agents/revised-draft.json
python tools/research_sessions.py review --run-id RUN_ID --input .local/agents/new-review.json
```

수정 전 초안·검토는 attempts에 보존한다. 수정 후에는 새 모델 검토가 필요하며 이전 digest는 사용할 수 없다. 지침은 저자 의견/실증 관측, 근거 부족/반증, 가설과 반증조건, 자체 제안 기준/출처 수치를 구분한다.

사람 승인 후 저장한 agent_note는 Research Library의 **사람 검토 연구노트**에서 통합 검색, 출처, 검토자/일자, 조건·반증조건·미확보 근거로 조회한다. 승인 전 실행 파일은 운영 목록에 노출하지 않는다. 출처의 삭제·제외·접근 변경·분류 revision 변경은 기존 승인노트를 숨기며 다시 확인한 자료로 재검토한다. 조회는 DB 읽기 전용이며 활성 가설과 curated 승격은 별도다.

새 CLI에는 네트워크·모델 프로세스 호출이 없다. 합성 통과와 실제 구독 실행 결과를 구분한다. 현 단계는 파일 인계 방식이며 완전 자동 호출은 포함하지 않는다. 2026-10-14 실제 공개 주주서한 관측으로 Claude 초안·Codex 검토·Claude 수정·Codex 재검토를 수행했다. 해당 연구 메모는 사람 승인 대기이며 정책 채택이나 효과 실증이 아니다.

공식 참고: [Codex 인증](https://learn.chatgpt.com/docs/auth), [Claude 구독 사용](https://support.claude.com/en/articles/11145838-use-claude-code-with-your-pro-or-max-plan), [추가 사용량](https://support.claude.com/en/articles/12429409-manage-usage-credits-for-paid-claude-plans).
