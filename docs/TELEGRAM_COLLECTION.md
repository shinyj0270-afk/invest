# 집 PC Telegram 자료 입력

## 선택한 방식

Telegram Desktop의 채널별 **Export chat history → JSON**을 사람이 실행하고,
`tools/telegram_export.py`로 로컬에서 참조 메타데이터를 준비한다. 공개·비공개
broadcast channel을 지원한다. 계정 전체 내보내기·개인 대화·그룹 파일은 거부한다.
초기 기간은 사용자가 지정하고 이후 필요할 때 기간을 나누어 실행한다. 예약이나
실시간 수집은 등록하지 않는다. 내보내기 기능이 제한된 채널은 우회하지 않는다.

- 공식 내보내기: https://telegram.org/blog/export-and-more
- 공식 JSON 구현: https://github.com/telegramdesktop/tdesktop/blob/dev/Telegram/SourceFiles/export/output/export_output_json.cpp
- 메시지 링크 형식: https://core.telegram.org/api/links#message-links
- 콘텐츠 이용조건: https://telegram.org/tos/content-licensing
- API 조건: https://core.telegram.org/api/terms

2026-10-13 확인. 내보내기 제공과 AI 이용 허용은 별개다. 이 도구는 네트워크·AI
호출 없이 개인이 제공한 로컬 파일에서 메타데이터만 추출한다. Telegram 원문을
모델에 일괄 전달하지 않는다. 기존 registry의 권한을 만들거나 변경하지 않는다.

## 사용

1. 해당 작업본의 `config/local.json`에서 명시적으로 home 프로필을 설정한다.
2. 각 채널에서 내보내기를 선택하고 사진·영상·파일 선택을 해제한다. JSON 결과를
   `.local/telegram-research/inbox/<channel-key>/` 아래에 날짜별 새 폴더로 저장한다.
3. `.local/telegram-research/channels.json`에 선택한 채널만 등록한다. `expected_name`은
   실제 내보내기 이름과 같아야 한다. 최초 `expected_id: null`은 ID 확인 대기다.
   첫 결과의 `chat_id`와 메시지 링크를 사람이 확인한 뒤 해당 숫자를 고정한다.
4. 기존 PC의 Python 환경에서 실행한다.

```powershell
python tools/telegram_export.py --channels .local/telegram-research/channels.json --channel channel-a --input .local/telegram-research/inbox/channel-a/result.json --start 2026-10-12 --end 2026-10-13 --output .local/telegram-research/prepared/channel-a-001.json
```

채널 설정 형식(실제 이름과 ID는 로컬에만 입력):

```json
{"channels":[{"key":"channel-a","expected_name":"Synthetic channel","expected_id":null}]}
```

## 검토와 기존 Library 연결

출력은 UTC 게시 시각, KST 게시일, 채널·메시지 ID, 접근 제한이 유지되는 `t.me/c/`
링크, 명시적으로 연결된 외부 HTTPS 출처, 수정 시각, 본문 변경 감지용 digest를
포함한다. 원문 본문·첨부·발신자 정보는 출력에 복사하지 않는다. 입력 원본은
이동하거나 수정하지 않으며, 같은 출력 파일을 덮어쓰지 않는다.

`--previous`에 동일 채널·동일 기간의 이전 결과를 주면 신규·동일·수정·미등장 ID를
대조한다. 미등장 또는 ID 간격을 삭제/누락 확정으로 해석하지 않는다. 내보내기
기간 선택이 잘못되어도 지정 KST 기간 밖 항목은 제외한다. 완전성은 항상 미확인이다.

출력의 `batches`는 기존 `tools/research_library.py telegram` 입력 계약이며 각 배치는
최대 1,000건이다. ID·날짜·링크와 기존 채널별 이용 근거를 검토한 후 각 배치를
별도 `.local` JSON으로 저장해 기존 CLI로 입력한다. `comparison.changed_ids`가 있으면
기존 게시물 덮어쓰기를 시도하지 말고 변경 내용을 검토한다. preparation은 DB 등록
또는 사람의 curate를 뜻하지 않는다. 같은 원출처의 여러 채널 전달은 독립 근거가 아니다.

원본/메타데이터/설정/연구노트는 home의 `.local`에만 보존한다. 코드·합성 테스트·공통
사용법만 공유 후보에 들어간다. 이 절차는 기존 START/CLOSE, Git 및 worktree 규칙을 유지한다.
