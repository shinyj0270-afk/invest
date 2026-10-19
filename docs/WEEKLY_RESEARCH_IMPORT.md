# 월요일 연구노트 등록

`tools/import_weekly_research.py`는 회사/집의 기존 로컬 프로필 DB에 등록한다. 실행만으로 다른 PC의 DB를 동기화하지 않는다. 원본·manifest·ZIP·DB·영수증은 `.local/`에만 보존한다. 외부 검색·모델 호출·주문·공유 승격은 하지 않는다.

## 입력 계약

`.local/research-library/inbox/YYYY-MM-DD/` 아래 원본 `original.md`, 선택 `original.zip`, 구조화한 `manifest.json`을 둔다. JSON은 `research_date`(월요일 YYYY-MM-DD), 원본 바이트의 소문자 SHA256 `markdown_sha256`, `records`를 갖는다. records는 기존 Library API의 `{kind, id, value}` 배열이다. source/master/thesis/evidence만 허용한다. 원문을 DB에 복제하지 않고 출처 식별과 자체 서술을 분리한다. 향후 카드 ID는 `MASTER-YYYYMMDD-NN`처럼 날짜로 구분하며 같은 가설의 의미 변경은 기존 revision 절차로 별도 검토한다.

모르는 발행일은 null, 확인되지 않은 적용 섹터는 미확인으로 둔다. 기존 사람이 검토한 섹터/topic 메타데이터와 같은 값만 자동 연결한다. 사람 검토 완료/curated를 자동 선언하지 않는다. Markdown만 있고 구조화 입력이 없으면 필드와 출처를 대조하여 manifest를 준비해야 한다. 문장 유사도로 대가나 섹터를 추측해 채우지 않는다.

## 실행

```powershell
./.venv/Scripts/python.exe tools/import_weekly_research.py --markdown .local/research-library/inbox/YYYY-MM-DD/original.md --manifest .local/research-library/inbox/YYYY-MM-DD/manifest.json
./.venv/Scripts/python.exe tools/import_weekly_research.py --markdown .local/research-library/inbox/YYYY-MM-DD/original.md --manifest .local/research-library/inbox/YYYY-MM-DD/manifest.json --zip .local/research-library/inbox/YYYY-MM-DD/original.zip --apply
```

첫 명령은 데이터 삽입 없는 검증이며 새 DB가 없으면 기존 Library 초기화가 빈 스키마를 생성할 수 있다. 두 번째는 전체 검증 후 한 SQLite 트랜잭션으로 등록한다. 실패는 모두 rollback한다. 원본 해시·ZIP 바이트·월요일·관측일·필드·참조·권한·ID·URL 충돌을 확인한다. 실제 등록 전 SQLite backup API로 해당 PC의 DB를 `.local`에 보존한다.

정확 URL과 동일 source payload는 기존 ID를 재사용하고 카드/가설/근거의 출처 참조를 바꾼다. 다른 source metadata, 다른 기존 ID 내용, 같은 원본의 상충 구조화 입력은 중단한다. 기존 revision을 자동 변경하지 않는다. 파일명을 바꾸거나 재실행해도 날짜+원본 해시로 중복을 막는다. 동시 재실행도 BEGIN IMMEDIATE로 직렬화한다.

별도 `kind=weekly` 영수증에 입력 해시·추가/재사용 건수·연결을 기록한다. 이는 연구카드 건수와 별도로 센다. 연결 사유는 explicit_reference/same_person/same_strategy/same_sector/same_topic이며 기존 기록과 신규 기록 모두 연결한다. 연결은 재사용 탐색용이고 독립 근거 수·인과·투자 결론의 검증을 의미하지 않는다. UI는 기존 카드 조회를 유지한다. 자동 연결은 CLI 결과 및 weekly 영수증에서 확인한다.

## 월요일 반복 처리

Codex의 이 작업에 연결한 주간 점검이 회사 PC의 inbox에서 준비된 묶음을 확인하고 검증 후 등록한다. PC가 오프라인이면 성공으로 보고하지 않고 다음 접근에서 미처리 파일을 확인한다. 새 자료가 없거나 결과가 바뀌지 않으면 조용히 유지하고, 등록 완료·실패·원본/manifest 누락처럼 사용자 조치가 필요할 때 알린다. 연구노트 작성·원본 첨부를 받는 기능과 DB 등록은 별도다. 자동 DB 복사나 Git commit/push는 반복 처리 범위에 포함하지 않는다.


## 2026-10-19 연결 범위 확인

기존 월요일 09:00 KST의 `월요일 연구노트 DB 등록` heartbeat를 유지한다. 새 예약·예약 변경·OS 작업을 추가하지 않는다. 08:00경의 ChatGPT 노트 생성과 이 PC의 inbox는 별도이며, 생성된 대화 본문/첨부를 자동 수신하는 연결은 없다. 회사 PC/앱 접근과 입력 묶음이 준비돼야 등록할 수 있다. 기존 예약의 ACTIVE 상태는 미래 실행 성공을 보장하지 않는다.

노트가 생성되면 권한 있는 실행자가 원본을 정상 다운로드하거나 자체작성한 새 노트임을 표시하고 inbox에 공급한다. 기존 대화 원본이 없으면 복원본으로 가장하지 않는다. 출처 제목·URL·귀속·발행일을 외부 원문과 대조한다. 발행일 미확인은 null로 두고 확인일로 대체하지 않는다. 서지/목차만 읽은 자료는 그 범위를 기록한다. 기존 URL은 `research_library.py search --query`로 확인하고 immutable source payload를 그대로 재사용한다. 확인일이 달라졌다는 이유만으로 기존 source metadata를 덮어쓰거나 같은 URL을 추가하지 않는다. 재열람 근거는 새 카드/catalog source_note에 남긴다.

`manifest.json`의 source/master/thesis/evidence와 노트 본문을 대조한 뒤 기존 명령으로 검증→DB backup→apply→같은 묶음 재처리 inserted=0→무결성/기존 revision/조회 검사를 순서대로 실행한다. 분류가 필요하면 기존 annotate로 raw/derived, persons, sector, topic, tags, event_id를 추가한다. 동일 catalog는 건너뛰고 다른 내용은 expected_revision을 확인해 사람 판단으로 정정한다. sector는 실제 주도력 관측인지 연구 적용 후보인지 source_note에 구분한다. 사람 검토 없는 curated 승격은 하지 않는다. catalog는 주간 manifest의 자동 등록 대상에 포함되지 않으므로 별도 검증·입력이 필요하다.

상충 ID/URL·의미상 유사 노트·다른 쓰기 세션·권한 미확인·오프라인이면 적용을 보류하고 기존 자료를 보존한다. 등록기의 해시 결합은 출처 사실성이나 저작권/사람 검토를 자동 인증하지 않는다. inbox 공급·외부 원문 대조·의미상 중복 판단·분류 검토는 완전 자동화되지 않았다. Git 공유·다른 PC DB 복사·전체 세션 수집은 예약에 포함하지 않는다.

10월 19일 신규 자체작성 노트는 docs/research/INVESTMENT_MASTERS_WEEKLY_2026-10-19.md다. 원본과 구조화 입력·영수증·DB 백업은 해당 PC의 `.local/research-library/inbox/2026-10-19/`에 둔다. 새 반복 시스템이나 대시보드 개발을 도입하지 않는다.
