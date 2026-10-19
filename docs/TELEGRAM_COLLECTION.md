# Telegram 개인 연구 수신함·기존 JSON 입력

## 현재 기본 방식 · 사용자 확정 2026-10-19

사용자가 소유한 **별도 비공개 채널**을 개인 연구 수신함으로 삼고 직접 선별한 정보를 모은다.
승도리·트릴리온·스탁이지의 세 방에 한정하지 않는다. 뉴스·공시·기업 IR·보고서·본인 메모 등
사용자가 중요하다고 판단한 정보를 수집한다. 수신 봇 활용은 단계적으로 확장한다.
채널명·링크·식별자와 인증은 로컬에 보존하고 일반 Git에 기록하지 않는다.

### 1단계: 수동 수집

1. 사용자가 Telegram에서 새 채널을 만들고 공개 범위를 비공개로 선택한다. 이름은 자유롭게 정한다.
2. 직접 작성한 메모, 외부 원문 URL, 전달이 허용된 자료를 넣는다. 원문 링크에 중요하다고 생각한
   이유 한 줄을 덧붙이는 것으로 시작한다. 기업·산업 태그는 선택 사항이다.
3. 원문 발행일과 채널에 모은 날짜는 구분한다. 날짜·출처를 모르면 미확인으로 둔다.

예시(가상):

```text
원문: https://example.invalid/company-ir
관심 이유: 설비투자 계획이 실제 매출로 이어지는 시점을 확인하고 싶음
#반도체 #설비투자
```

내보내기·전달이 제한된 방의 설정을 우회하지 않는다. 별도로 열 수 있는 기사·공시 원문은
그 발행처 링크를 모으고, 제한된 게시물의 본문을 복사하는 경로로 바꾸지 않는다.
개인 채널에 보관한 항목은 선별 자료이며, 내용 검증·사람 curate·투자 판단 승인과 구분한다.

### 2단계: 수신 봇 연결 (후속)

사용자 소유 채널 한 곳에 수신 봇을 추가하고 연결 이후 신규 게시물부터 소량 검증한다.
개인 채널 식별자를 고정해 다른 방의 메시지와 섞이지 않도록 하고 출처·수집시각·중복을 확인한다.
원래 전달 출처가 미확인이면 추정해서 채우지 않는다. 과거 게시물 전체 수신을 보장하지 않는다.
Saved Messages를 일반 Bot API로 직접 읽는 방식은 이번 기본 경로로 삼지 않는다.

### 3단계: 연구 연결 (후속)

수신 항목을 미검토함에서 살펴보고 원문 링크·기업·산업을 확인한 뒤 기존 Research Library의
등록 후보로 연결한다. 같은 기사 재전달은 독립 근거로 세지 않는다. 외부 원문 조사와 채널 자체
해석을 구분하며, 원자료별 이용 범위와 기존 외부 모델 입력·공유 경계를 유지한다.
자동 요약·AI 전송·Library 자동 입력·예약 실행은 이번 결정만으로 활성화하지 않는다.

### 현재 상태와 다음 확인

- 사용자 보고(2026-10-19): 비공개 채널 생성·기사 링크 게시·봇 생성과 채널 관리자 추가 완료.
  개인 채널명·봇 사용자명·토큰·채널 ID는 일반 Git에 기록하지 않는다. API 연결·실제 수신은 미실행이다.
- 회사 PC 교체를 고려해 기존 home 전용 처리와 일치하는 집 PC 수신을 기준으로 준비한다.
  코드 개발·합성 검사는 work 작업 워크트리에서 가능하며 현재 PC 프로필은 변경하지 않는다.
- 다음 구현은 지정한 개인 채널의 신규 게시물을 받는 수신 프로그램과 토큰의 로컬 입력이다.
  집 PC에서 본인 봇·대상 채널 식별과 새 링크 수신을 검증한 뒤에만 실제 연결 완료로 보고한다.
  이번 JSON 도구 복원을 수신 봇 구현으로 표시하지 않는다. 자동 시작·예약은 별도 요청 전까지 등록하지 않는다.
- 집 PC와 수신 프로그램이 동작 중이어야 자동 수신한다. Bot API의 미수신 업데이트는 최대 24시간
  보관된다. 장기 중단 후 전체 복구를 보장하지 않으며, 채널에 보관된 과거 게시물과 봇의 대기열을
  구분한다. 집 PC 토큰·개인 설정·수신 자료는 로컬에 보존하고 코드 Git/회사 공유 결과에 넣지 않는다.
- 기존 JSON 준비 도구는 아래 보조 경로로 보존하며 원본의 보호 설정 때문에 실패한 내보내기를
  반복하는 것을 기본 흐름으로 삼지 않는다.

기술 근거(2026-10-19 확인): 봇은 참여 채널의 게시물을 수신한다.
[Bot FAQ](https://core.telegram.org/bots/faq#what-messages-will-my-bot-get).
보호된 메시지 전달 제한은 [Bot API](https://core.telegram.org/bots/api#forwardmessage)를 따른다.
업데이트 보관 기간은 [Getting updates](https://core.telegram.org/bots/api#getting-updates)에 따른다.

## 기존 보조 방식: home JSON 입력 준비 (2026-10-13 구현)

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
