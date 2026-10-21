# 투자연구함 정리

사용자는 Telegram의 본인 비공개 채널에 외부 원문 링크를 모으고, 파일·본인 메모는
`다운로드/INVESTMENT 자료`에 둔다. Telegram 수신기가 켜져 있어야 링크가 집에 들어온다.
현재 수신기는 본문·첨부를 저장하지 않으므로 링크 없는 게시물은 읽기 대기로 표시한다.

이후 **투자연구함 정리해**라고 요청한다. 현재 AI 세션이 새 자료를 묶어 읽고 기업/산업,
관측과 해석, 기존 연구와의 연결, 반대 근거, 미확보를 정리한다. 처리 결과는 집의
`.local/research-inbox/knowledge/`에 저장한다. 다음 세션은 필요한 지식을 검색해 재사용한다.
이는 별도 자료 저장·검색이며 모델 자체를 재훈련하는 기능이 아니다.

기본 처리 단위는20건이며 남은 자료를 다음 묶음으로 이어간다. 같은 URL의 추적 매개변수·fragment는
중복으로 묶고 다른 메시지 출처를 함께 보존한다. 비밀성 query가 있는 URL은 자동 열람 대상에서
제외한다. 처리한 URL/파일 해시는 새 정리에서 재선정하지 않는다. 동일 기사의 새 내용·재검토가
필요하면 기존 결과를 덮어쓰지 않고 명시적으로 새 revision을 준비한다.

```powershell
.\.venv\Scripts\python.exe tools\research_inbox.py prepare
.\.venv\Scripts\python.exe tools\research_inbox.py status
.\.venv\Scripts\python.exe tools\research_inbox.py search 반도체
.\.venv\Scripts\python.exe tools\research_inbox.py reopen --id ITEM_ID --reason "새 공시와 기존 해석 비교"
.\.venv\Scripts\python.exe tools\research_inbox.py finish --batch ID --input .local/research-inbox/results.json
```

Python 명령은 목록·해시·처리이력·검색만 관리한다. 네트워크·AI 프로세스·예약을 실행하지 않는다.
추가 API 비용 없이 기존 세션으로 처리하며 해당 세션의 사용량은 소비한다. 정리 명령이 없거나
세션이 끝나면 AI 연구도 계속되지 않는다. 토큰·구독·profile·예약·모델 설정은 바꾸지 않는다.

`prepare`의 packet은 batch별 immutable 파일이다. 선택한 모든 항목에 명시적 결과를 요구한다.
원문/상태가 바뀌면 기존 packet의 저장을 거부한다. 재저장은 같은 결과일 때 중복0이며 상충 결과는
보존·중단한다. 완료 결과의 provenance는 로컬 영수증·원문 URL·파일 해시와 연결한다.

결과 JSON은 아래 객체의 배열이다. `outcome`은 `read`/`metadata_only`/`blocked`,
`reading_basis`는 `full_text`/`metadata`/`unavailable`다. 미열람 결과의 summary/observations/
interpretation은 빈 값으로 둔다. URL을 읽었으면 해당 원문을 source_urls에 포함한다.

```json
{
  "id": "packet의 source.id",
  "outcome": "read",
  "reading_basis": "full_text",
  "title": "확인한 원문 제목",
  "summary": "자체 서술 요약",
  "observations": ["기사에서 보도한 관측; 독립 확인 여부 구분"],
  "interpretation": "AI 해석·기존 지식과의 연결",
  "counterpoints": ["반대 근거나 성립하지 않을 조건"],
  "open_questions": ["미확보 근거"],
  "tags": ["산업/주제"],
  "companies": [],
  "source_urls": ["https://example.invalid/article"]
}
```

모든 결과는 `human_reviewed=false`, `status=ai_draft`다. Library의 사람이 승인한 연구노트와
분리한다. 공개 링크를 Telegram에서 받았다는 provenance와 집 로컬 보존 경계를 유지하며 회사
결과/공개 Git/외부 AI 일괄 전달에 포함하지 않는다. 일반 접근 가능한 자료의 묶음 연구·초안 저장은
사용자 승인 범위다. 보호 콘텐츠·중요한 출처 충돌·검토 불가 자료만 별도로 알린다.
