# API 기반 중앙 실행관리

> **2026-10-14 정책 변경:** 추가 비용을 원치 않는 사용자 결정으로 API 실행을 코드에서 차단했다. 아래 API 설정·실행 설명은 보존된 이전 설계이며 현재 사용하지 않는다. 현재 흐름은 [기존 Codex/Claude 세션](RESEARCH_SESSIONS.md)을 따른다. API 키 연결은 다음 작업에서 제외한다.

Python 실행관리자가 Research → Review 순서와 검증·저장을 관리한다. 역할별 provider/model 설정으로 확장하며 모델이 다음 에이전트나 도구를 임의로 실행하지 않는다. 초기 흐름은 Claude 초안, OpenAI 검토다. Collector는 기존 결정론적 수집을 유지하고 Synthesis 자동화는 후속이다.

Research Library의 **공개·independent 출처 ID**와 사람이 직접 작성한 관측만 명시적으로 선택한다. URL 원문을 자동 조회하지 않으며 원문 전체·보유내역·DB·Telegram·유료/비공개 자료를 모델 입력으로 보내지 않는다. 입력 선언은 사람의 자료 검토를 대신하지 않는다. 질문과 관측에도 비밀이나 개인정보를 넣지 않는다.

실제 API 접근은 아직 키와 모델 권한을 해당 PC에서 검증해야 한다. Codex/Claude 앱 로그인과 API 인증은 별개다. 모델 ID를 임의로 고정하지 않고 해당 계정에서 쓸 ID를 설정한다. 프로젝트 기존 requests만 사용한다.

## 설정과 실행

키는 실행 프로세스의 `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` 환경변수로 제공한다. 키를 코드·명령행 인수·공유 문서에 넣지 않는다. `.local/agents/config.json`에 다음 구조를 작성하되 model은 실제 사용 가능한 ID로 지정한다.

```json
{
  "research": {"provider": "anthropic", "model": "YOUR_CLAUDE_MODEL", "timeout_seconds": 60, "max_output_tokens": 3000},
  "review": {"provider": "openai", "model": "YOUR_OPENAI_MODEL", "timeout_seconds": 60, "max_output_tokens": 2000}
}
```

`.local/agents/input.json` 예시(출처는 먼저 기존 Library에 등록):

```json
{
  "question": "선택한 관측이 어떤 조건부 가설을 지지하는가?",
  "as_of": "2026-10-14",
  "observations": [{"source_id": "YOUR_PUBLIC_SOURCE_ID", "observation": "직접 확인한 공개 자료의 관측을 자체 서술"}],
  "external_model_allowed": true,
  "independent_analysis": true,
  "no_personal_data": true
}
```

회사/집의 해당 프로젝트 `.venv`에서 실행한다. config/local.json의 명시된 work/home 프로필을 사용한다.

```powershell
.\.venv\Scripts\python.exe -B tools/research_agents.py doctor
.\.venv\Scripts\python.exe -B tools/research_agents.py run --input .local/agents/input.json
.\.venv\Scripts\python.exe -B tools/research_agents.py show --run-id RUN_ID
```

doctor는 키 존재 여부만 출력하며 API 연결 성공을 의미하지 않는다. run은 두 번의 유료 요청을 수행할 수 있다. 출력 토큰 256~8192, 요청별 시간 5~120초, 관측 최대12개를 제한한다. 자식 프로세스 종료로 요청별 설정+2초의 대기 상한을 둔다. 서버측 처리/과금 취소까지 보장하지 않는다. HTTP 자동 재시도·모델 대체·에이전트 재귀 호출은 없다. 실패 시 새 run으로 수동 재실행하며 이미 수행한 호출도 다시 과금될 수 있다.

단계 결과·시간·공급자가 보고한 토큰 사용량을 `.local/agents/runs/{profile}/user_input/{id}/run.json`에 보존한다. 금액은 산정하지 않아 null, 확인 불가 사용량도 null이다. 프로세스가 강제 종료되면 마지막 `*_running` 상태가 남으므로 완료로 간주하지 않는다. 실패 응답 본문·인증 헤더는 저장하지 않는다. OpenAI는 store=false, 두 공급자 모두 모델 도구를 제공하지 않는다.

## 사람 검토 후 저장

`awaiting_human`은 모델 검토 통과이며 사람 승인이 아니다. 출처·초안·반증조건·검토 결과를 실제로 읽은 사람이 해당 run의 review_digest를 사용해 `.local/agents/approval.json`을 작성한다.

```json
{
  "review_digest": "EXACT_REVIEW_DIGEST",
  "reviewer": "검토자",
  "reviewed_on": "2026-10-14",
  "human_reviewed": true,
  "independent_analysis": true,
  "no_personal_data": true
}
```

```powershell
.\.venv\Scripts\python.exe -B tools/research_agents.py approve --run-id RUN_ID --input .local/agents/approval.json
```

승인은 내용을 다시 검증하고 Research Library의 별도 `agent_note` 기록으로 저장한다. 같은 승인 반복은 중복 삽입하지 않는다. 활성 thesis, evidence, curated 카드로 자동 승격하지 않는다. 현재 기존 세션 경로의 승인노트는 Research Library 화면에서 검색·조회할 수 있다. digest는 변경 감지 수단이며 악의적인 로컬 파일 변경에 대한 인증 서명이 아니다. 검토 중 출처 메타데이터가 바뀌면 새 실행·검토가 필요하다. 기존 Library의 approved-result/공유 승인은 별도다.

공식 API 계약 확인: [OpenAI structured output](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses), [Claude Messages](https://platform.claude.com/docs/en/api/messages/create). 네트워크·실모델 테스트와 합성 테스트를 구분한다. 키/출력/DB/로컬 설정은 Git 공유에서 제외한다.
