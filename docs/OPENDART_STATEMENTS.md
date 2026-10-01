# DART 재무제표 수집

## 현재 회사 PC

2026-10-01 DART 공개 조회에서 3사 연결·별도 84개 원문을 확보했습니다. 새 로컬 파일 `private_data/infomax/company-statements.json`을 재무 내보내기에 연결합니다. 원문 HTML과 해시·조회 메타데이터는 같은 폴더의 `company-statements-sources/`에 보관합니다. 기존 XLSX·DB·설정은 수정하지 않습니다. 인증키와 재무 캐시는 Git 공유 대상이 아닙니다.

## 인증키 설정

**키를 채팅·코드·공유 문서에 넣지 마세요.** Windows 검색에서 **환경 변수 편집 → 사용자 변수 → 새로 만들기**로 `OPENDART_API_KEY`를 만들고 발급받은 키를 값에 입력합니다. 설정 후 Codex와 터미널을 다시 열어야 새 값이 적용됩니다. 다른 PC에는 따로 설정합니다. 키 자체를 출력해서 확인하지 않습니다.

## 수동 수집

프로젝트 폴더에서 실행합니다. 자동 예약은 등록하지 않습니다.

```powershell
# 인증키 없이 공식 공개 재무제표 수집
.\.venv\Scripts\python.exe tools/company_statements.py --source public --start-year 2023 --end-year 2026 --through-quarter 2 --output private_data/infomax/company-statements.json

# 로컬 인증키로 OpenDART API 대차 총계까지 대조
.\.venv\Scripts\python.exe tools/company_statements.py --source api --start-year 2023 --end-year 2026 --through-quarter 2 --output private_data/infomax/company-statements.json
```

`--codes`로 005930·000660·005380 중 필요한 기업을 선택합니다. 마지막 연도는 `--through-quarter`까지, 앞선 연도는 네 분기를 조회합니다. 2026-10-01 회사 PC에서 로컬 환경변수의 키로 실제 인증과 API 모드를 확인했습니다. 3사 연결·별도 84개 공시의 회사·접수번호와 자산/부채/자본 총계 대조가 모두 통과했습니다. 기존 재무 값은 변경되지 않았습니다. 손익/현금흐름 모든 계정의 API 일치까지 검사한 것은 아닙니다. 집 PC의 키 설정과 실제 조회는 별도로 확인합니다.

API 모드는 [전체 재무제표 API](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019020)의 회사·접수번호·대차 총계를 공개 원문과 대조합니다. 세 재무제표의 회사별 계정/단위는 [DART 공개 조회](https://opendart.fss.or.kr/disclosureinfo/fnltt/singl/main.do) 원문을 정규화합니다. 오류 메시지·파일에 키나 키가 포함된 요청 URL을 남기지 않습니다. 일부 조회·검증이 실패하면 `.incomplete.json`에 따로 저장하고 기존 연결 파일을 보존합니다.

## 재생성과 PC 인계

수집 후 기존 HTML 내보내기 또는 대시보드 갱신을 실행합니다. 저장 스냅샷 가격일 이후의 보고서는 화면에 포함하지 않습니다. 집 PC에서는 최신 main 수신 후 같은 수집 명령으로 해당 PC의 캐시를 만들거나 사용자 선택으로 재무 캐시와 원문 폴더만 옮깁니다. PC 설정·DB·키는 복사하지 않습니다. EBITDA 수기값은 별도 입력 JSON으로 옮깁니다.

2015년 이후 확장 조회가 가능하지만 회사별 공시 방식 차이에 따라 추가 계정 정규화가 필요할 수 있습니다. 키만으로 사업부 매출·수주·외국인 지분·장기 수정주가·원 서비스의 독자 값을 모두 받을 수 있는 것은 아닙니다.
