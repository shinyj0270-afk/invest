# 자료 투입 폴더 · 2026-10-19

사용자 결정(2026-10-19): 회사·집 PC 모두 `다운로드/INVESTMENT 자료` 폴더에 적용하고 싶은 아이디어·전략·관심기업 분석 자료를 넣는다. AI는 INVESTMENT START와 `자료 확인` 호출 때 새 파일을 읽고 대시보드 반영 방법을 **최종 선택지**로 제시한다. 사용자가 고르기 전에는 등록하지 않는다. 예약 점검은 두지 않는다.

## 폴더와 처리 기록

- 기본 위치 `%USERPROFILE%\Downloads\INVESTMENT 자료`. 다른 위치는 그 PC의 비공개 `config/local.json`에 `research_drop_inbox`로 지정한다(상대 경로는 프로젝트 루트 기준).
- 맨 위 단계의 일반 파일만 본다. 하위 폴더, 숨김 파일, `~$` 임시 파일, `.crdownload/.part/.tmp/.download/.lnk`는 건너뛴다. 50MB 초과는 읽지 않고 `too_large`로 표시한다.
- 처리 여부는 파일 내용 SHA256으로 판단한다. 이름을 바꿔도 같은 내용이면 다시 묻지 않고, 같은 이름이라도 내용이 바뀌면 새 자료다.
- 선택 결과는 그 PC의 `.local/research-drop/<profile>/ledger.json`에만 기록한다. 원본 파일은 이동·삭제·수정하지 않는다. 다른 PC로 동기화하지 않는다.

```powershell
.\.venv\Scripts\python.exe tools\research_drop.py status
.\.venv\Scripts\python.exe tools\research_drop.py record --sha <SHA256> --decision report|library|thesis|archive --note "<선택 요약>"
```

## AI가 제시하는 선택지

자료마다 내용을 읽고 다음 중 해당하는 선택지를 화면 변화와 함께 제시한다.

| 선택 | 등록 위치 | 대시보드에서 보이는 곳 |
|---|---|---|
| report | 외부 분석 보고서(docs/EXTERNAL_REPORTS.md). HTML이 아니면 등록 가능한 단일 HTML 변환 여부를 함께 제시 | 기업 분석 → 간단 분석 → 외부 분석 보고서 |
| library | Research Library source/master/thesis/evidence(+catalog 분류)(docs/RESEARCH_LIBRARY.md, WEEKLY_RESEARCH_IMPORT.md) | Research Library, 산업 연구 → 관련 연구·원문(종목 연결 또는 확정 산업 대응표) |
| thesis | 종목 투자 논리 config/business_theses.json(기준값 guideline_thresholds.json) | 보유·추천 종목의 투자 논리 점검(재검토 권고/유지 점검/자료 부족) |
| archive | 등록하지 않고 처리 기록만 남김 | 없음 |

선택지에는 출처·발행일 확인 결과, 원문과 자체 해석의 구분, 미확보 항목, 연결할 산업·종목 후보, 예상 위험(유료·Telegram·개인 자료 여부)을 적는다. 하나의 자료를 여러 곳에 나누는 조합도 제시할 수 있다.

## 등록 원칙

- 사용자 선택 후 기존 경로로만 등록한다. Library는 DB 백업 → 검증 실행 → apply → 같은 묶음 재처리 inserted=0 확인. 투자 논리는 config 변경이므로 Git 반영·테스트·안전 재시작 절차를 따른다.
- 발행일 미확인은 null, 가설은 검증 전, 사람 검토(curated) 자동 선언 없음. 문장 유사도로 대가·섹터·종목을 추측해 채우지 않는다.
- Telegram 유래·유료·비공개 자료는 기존 권한 규칙을 따르며 work에서는 Telegram 자료를 등록하지 않는다. 외부 모델 전송은 별도 승인 없이 하지 않는다.
- 자료와 처리 기록은 Git·결과 공유·다른 PC로 자동 전달되지 않는다. 회사에서 등록한 연구는 회사 DB에만 있다.
