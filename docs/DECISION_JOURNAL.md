# 투자 결정 일지

매수·매도를 검토하기 전에 가설, 틀렸다고 볼 조건(반증 조건), 근거 출처, 다시 점검할 날짜를 먼저 적어 두고, 점검일이 지나면 결과와 대조해 판단 품질을 돌아보는 기록이다. 새 저장소를 만들지 않고 [Research Library](RESEARCH_LIBRARY.md)의 로컬 DB에 `decision`·`decision_review` 기록 종류를 추가했다(`investment/decision_journal.py`).

## 범위와 보관

- 주문·자동매매·잔고 조회와 연결하지 않는다. 수량·매입가·계좌 필드는 받지 않는다(허용 필드 외 입력은 거부).
- 저장 위치는 PC별 `.local/research-library/<profile>/user_input/research_library.sqlite3`이다. `.local/`은 `.gitignore` 대상이고 `config/share_candidates.json`에 들어 있지 않으며 보유내역 비공개 동기화·결과 발행·백업 대상도 아니다. 회사·집 일지는 서로 자동 공유되지 않는다.
- 공유되는 것은 코드·시험·이 문서뿐이다. 입력 JSON도 `.local/` 아래에만 둔다(CLI가 다른 경로를 거부).

## 기록 항목

일지(`decision`, 작성 후 수정 불가):

| 필드 | 내용 |
|---|---|
| written_on | 작성일(KST, 미래 불가) |
| code·name·market·kind | 국내 6자리 코드, 종목명, KOSPI/KOSDAQ, stock/etf |
| review_type | watch(관찰)·buy_review(매수 검토)·sell_review(매도 검토) |
| hypothesis | 가설 |
| invalidation | 반증 조건 목록(1개 이상) |
| source_ids | Library에 먼저 등록한 출처 ID(1개 이상). 출처의 확인일(accessed_on)이 작성일보다 늦으면 거부 |
| review_on | 점검일(작성일 이후) |
| score_snapshot | 선택. `{"as_of": 기준일, "model": 모형 이름, "values": {이름: 숫자}}`, 기준일은 작성일 이전 |
| thesis_id·thesis_revision | 선택. 연결할 기존 산업 가설과 revision |

사후 평가(`decision_review`, 수정 불가, 여러 번 가능): decision_id, reviewed_on(작성일 이후), outcome(결과), assessment(held 가설 유지·refuted 반증 발생·undecidable 판단 불가), reasoning, 선택 score_snapshot(점검 시점 점수).

점검일 이후 날짜로 평가가 기록되지 않은 일지는 "점검일 지난 결정 일지"에 남는다. 점검일 전에 적은 중간 평가는 목록을 지우지 않는다.

## 사용법

원본 main 작업본(설정된 work/home 프로필)에서 실행한다.

```powershell
.\.venv\Scripts\python.exe tools\research_library.py source --id src-1 --input .local\src-1.json
.\.venv\Scripts\python.exe tools\research_library.py decision --id d-2026-11-05-1 --input .local\decision.json
.\.venv\Scripts\python.exe tools\research_library.py due
.\.venv\Scripts\python.exe tools\research_library.py decision-review --id r-1 --input .local\review.json
.\.venv\Scripts\python.exe tools\research_library.py history --kind thesis --id thesis-1
```

`due`는 오늘(KST) 기준이며 `--today 2026-12-31`로 기준일을 바꿀 수 있다. 대시보드의 Research Library 화면 상단에도 같은 목록이 읽기 전용 표로 보인다(입력은 CLI만).

입력 예시(가상 값):

```json
{"written_on": "2026-11-05", "code": "000001", "name": "가상 종목", "market": "KOSPI", "kind": "stock",
 "review_type": "buy_review", "hypothesis": "가상: 2개 분기 내 영업이익률 회복",
 "invalidation": ["가상: 영업이익률 2개 분기 연속 하락"], "source_ids": ["src-1"], "review_on": "2027-02-15"}
```

## 한계

- 모형 점수 스냅샷은 사용자가 값을 옮겨 적는 방식이다. 저장된 품질점수를 자동으로 읽어 오지 않는다.
- 출처 삭제·제외 분류가 일지 목록을 숨기지는 않는다(산업 가설 화면의 의존 숨김과 다름).
- 휴대폰 읽기 전용 화면도 같은 Research Library 응답을 쓰므로 로그인한 휴대폰에서 점검 목록이 보인다.
