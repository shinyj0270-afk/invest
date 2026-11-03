# CURRENT HANDOFF

Updated: 2026-11-04T10:00:00+09:00 (SESSION CLOSE 재작성; 전송 검증 pending)
Last agent: Claude Code (Opus/Sonnet 5.5 세션) — Claude 중심 전환 후 첫 INVESTMENT 작업
Last PC: work Primary (config/local.json profile=work, pc_check finish 확인; 변경 없음)
Last task: .venv Codex 런타임 의존 제거 후 UI 테스트 점검, 역할 문구 전환, 방법론 질문 Q01~Q10 직접 조사와 승인 후 첫 구현 3건

Completed:
- 2026-11-02 `.venv`를 Codex 런타임(Python 3.12.14)에서 시스템 `C:\Python314`(3.14.7)로 교체. `requirements.lock.txt`와 동일 설치, 옛 환경은 `.venv-codex-backup`(Git 제외)에 보존, 운영 서버 재시작 후 build/source 일치.
- UI 테스트: 공식 `tools/validate_share_candidates.py --ui` 23개 중 `test_dashboard_upgrade_ui`·`test_dashboard_stability_ui`가 날짜(10월) 의존으로 실패 → `page.clock.install`로 시계 고정(`80e3391`) 후 23개 모두 PASS.
- 역할 문구: Claude Code 구현·검증·인수인계, Codex 독립 교차 검토로 INVESTMENT 문서 6개 개정(`de85832`). 다른 프로젝트(credit·PIANO-BLOG·BOND-BLOG·YOUNG-PIANIST·novel)는 각 저장소에 push, STUDIO는 Git 밖 파일 한 줄만 수정.
- ChatGPT Deep Research에 질문을 두 번 보냈으나 검색0·인용0·Q01만 답해 **결과 무효**, 어떤 문서에도 반영하지 않음. 대신 Claude Code가 공식 페이지를 직접 열어 Q01~Q10을 조사해 `docs/review/research_Q01~Q10_*.md` 10개 작성(`dd47f78`, 원본 main 반영·push 완료). 논문은 초록 수준, 확인 불가 항목을 문서마다 명시.
- 문서 정정: `ENVIRONMENT.md`의 `.venv` Python 버전(3.12.14 → 3.14.7).
- 사용자 승인(2026-11-03 "바꿀 건 바꾸고, 전송할 건 전송하자") 후 첫 구현 3건. **신규 파일만 추가했고 기존 코드·설정·투자 규칙·DB는 바뀌지 않았다.**
  - 시도 로그(Q06 T1): `investment/trial_log.py`(append-only·해시 연쇄 JSONL, `.local/trial-log/<profile>.jsonl`, Git 제외)와 `tools/trial_log.py`(record/summary). S10 민감도 진단 두 도구(`threshold_sensitivity_report`, `trend_sensitivity_report`)가 평가 전 기록에 사용했고 그 밖의 탐색에는 연결되지 않았다.
  - 겹침 포함률 모의 실험(Q07 T1): `tools/overlap_coverage_sim.py`와 결과 `docs/review/result_Q07_overlap_coverage_sim_2026-11-03.md`(합성 자료). 겹침을 무시한 구간의 실제 포함률은 지평 63/126/252일에서 각각 0.71~0.81/0.55~0.61/0.36~0.45였다.
  - Codex 순서 의존·변이 점검(1번, `gpt-6.1-sol`/high): 순서 의존 0건(단독 93모듈 전부 통과, 전체·역순·무작위 동일 904 통과), 변이 212개 중 138개 생존. 추천 필터 경계·정렬 방향과 시도 로그 연쇄 검증 7건은 직접 재현해 테스트 추가(`tests/test_codex_sweep_survivors.py`, 변이별 검출 확인), 나머지 약 131개는 `docs/review/mutation_sweep_2026-11-03/`에 목록만 보존.
  - Codex 문서-코드 일치 점검(`gpt-6-astra`/medium, 읽기 전용): 지적 11건 중 직접 확인한 것을 정정함 — 추천 필터 통과 5개는 배분 단계 이전의 진단 통과 수이고 편입 상한(5)과 같음(이전 서술 "상한을 못 채움·전부 들어감"은 오류), 겹침 모의는 종목 구성을 모형화하지 않음, 단독 차단 합 9는 상한이 아님, 시도 로그·잠금 파일 쓰기가 있음에도 "파일 쓰기 없음"이라 적은 곳, 낡은 인계 문장들. 실행 수치(로그 31회·파일 124,883개 등)는 당시 실행 보고값이며 재검증에는 로컬 시도 로그와 입력 스냅샷이 필요하다.
  - PIT 연간 재무 투영 핵심(3번, 사용자 승인 "2. 진행"): `investment/pit_annual.py`(순수 함수, 앱·실제 자료 미연결)와 `tests/test_pit_annual.py`(24개). 접수일 다음 거래일부터 사용 가능, 정정본은 별도 행으로 보존해 이전 기준일에 보이지 않음, 같은 사용 가능일의 값 충돌은 차단하고 값 없는 `ambiguous` 표시 행으로 원본 부활을 막음, 회사·회계 기준은 `project`당 하나(`project_all`이 분리), 필드별 검증(불리언·숫자·범위·알 수 없는 키 거부), 달력은 호출자가 검증된 거래일 달력을 공급해야 하며 이 모듈은 휴일을 알 수 없음. Codex 교차 검토(`gpt-6-astra`/medium)의 지적 7건(여러 회사 혼합, 검증 플래그 문자열, 모호한 정정이 원본 부활, 달력 신뢰, 불가능한 기간, 동등성·결정성, 오타 키)과 생존 변이 6종을 모두 테스트로 재현한 뒤 수정했고 변이 10종이 검출됨. 한계: 12월 결산·단일 회사·단일 기준 파일럿, 실제 접수 자료는 아직 없음(OpenDART 키 신청·약관 확인은 사용자 몫), V/B 요인은 여전히 시점 표시 없는 `metrics`를 읽으므로 이 투영만으로 완전한 PIT 품질 점수가 되지는 않음.
  - **분업 방식 전환(사용자 "전반적인 그림만 너가 만들고, 세부는 Codex")**: 큰 구조·계약(테스트)은 Claude Code가 정하고 세부 구현은 Codex(`gpt-6-astra`/medium)가 임시 복사본에서 구현해 패치로 받고, Claude Code가 적용·검증·변이 재검사. 첫 사례: `run-delisted`/`plan-delisted`(보관된 고유번호 파일을 재사용해 폐지 기업 연간 보고서 목록만 최대 2쪽 조회, 12월 결산 여부와 연속 12월 연도 수 보고). 도레이케미칼은 경계 사례(결산월 3월 전환)로만 사용, 4년 시계열용 폐지 기업 후보는 **동아타이어공업**(corp_code `01262458`, 종목 `282690`, 2024-10-08 상장폐지·디엔오토모티브에 흡수합병 — 검색 요약 기반, 12월 결산·연속 연도는 목록 조회 전 미확인). 조회 요청은 최대 2건이며 실행 전 별도 승인.
  - **첫 실호출 2차 실행 완료(승인 "이어서 실행")**: 이번 실행은 새 요청 4건(문서·폐지 후보 corp 목록 등), 누적 요청 총 8건, 중단 조건 없음. 보관 위치 `.local/pit-pilot/`(Git 제외). 결과: 효성중공업(corp_code `01316245`) 연간 보고서 9건(FY2022~FY2025 원본·정정 모두, 정정은 FY2022 1·FY2023 1·FY2024 1·FY2025 2), 최신 원본 `20260311004208`의 `document.xml` zip(770KB: 본문 XML 10.2MB와 연결감사보고서·감사보고서 XML 2개, 모두 DART XML 형식의 TABLE/TR/TD 구조)을 확인. 도레이케미칼(corp_code `00148717`, 상장폐지)은 OpenDART 목록이 조회됨(19건 중 연간 7건)이나 **FY2014 이후 결산월이 3월로 바뀌어**(`사업보고서 (2015.03)`~`(2018.03)`) 12월 결산 4개 연속 연도 조건에 맞지 않는다 — 전환 단기 사업연도 거부 규칙을 시험하는 경계 사례로는 유용하나 4년 시계열 대상으로는 부적합(대체 폐지 기업 선정 또는 경계 사례로만 사용 결정 필요). 다음: 저장된 XML 표본으로 연결 재무제표 표 위치·계정명을 확인해 값 대응표를 확정(요청 없이 로컬 분석), 기존 `parse_viewer`는 HTML 뷰어용이라 XML용 파서가 별도로 필요.
  - **첫 실호출 1차 실행(승인 "실행", 2026-11-03 16:32 KST 로컬 시각)**: 요청 4건(지수 달력 2·고유번호 zip 1·효성중공업 목록 1쪽) 후 스스로 중단. 달력(KOSPI·KOSDAQ 각 934봉)과 고유번호 zip(3.6MB)과 효성중공업 목록 21건은 `.local/pit-pilot/`에 보관됨. 중단 원인은 **실제 데이터가 내 가정과 달랐던 것**: 접수번호 `20230308000776`의 `rcept_dt`가 `20230309`(접수번호 날짜보다 하루 뒤). 기존 가정(접수일 = 접수번호 날짜)과 `fiscal_contract`의 원천 계약도 같은 가정을 쓰지만 PIT 쪽은 이를 "접수번호 날짜 이후 0~7일 늦은 rcept_dt 허용, 늦은 날짜(보수적)가 사용 가능일을 결정"으로 바꿨다(inventory·annual·values·verify 모두, 실제 행을 회귀 테스트로 고정). 또 응답 검증 실패를 `provider_error`로 잘못 표시하던 것을 `response_rejected`로 분리했고, 재실행은 보관된 고유번호·목록·원문을 재사용하고 달력도 실제 요청일 때만 예산을 차감한다. 나머지 계획(원문 1건·폐지 후보 목록 ≤2쪽)은 승인 대기. 효성중공업 21건 목록에는 FY2022~FY2025 사업보고서와 정정본이 모두 있음.
  - PIT 2단계 준비(사용자 "약관 확인 완료, 보수 조건으로 첫 호출 진행"): `investment/pit_live.py`(OpenDART 클라이언트: 요청마다 공유 예산 차감, 키는 환경 변수에서만 읽고 오류·repr에 노출 안 함, 020/429는 `QuotaStop`으로 즉시 중단, 응답 크기 상한, corpCode 파서는 정확 일치만), `investment/pit_first_call.py`(달력 2·고유번호 1·목록≤2쪽·원문 1·폐지 후보 목록≤2쪽, 전부 `.local/pit-pilot/`에 해시 보관), `tools/pit_pilot.py`의 `plan-first`(네트워크 없음)와 `run-first --root --confirm-first-call`(유일한 실호출 경로). 테스트는 가짜 세션·가짜 클라이언트이며 변이 검사 완료. **실호출은 아직 0회, 최종 승인 대기.** 일일 한도 20,000건(개인, 83종 합산)·분당 1,000회 제한 안내는 사용자가 확인해 붙여줌.
  - PIT 수집 어댑터 1단계 구현(사용자 승인 "반영 후 구현", 가짜 응답만, 실제 호출 0): `investment/pit_inventory.py`(OpenDART 목록 쪽 해석·일괄 조립, 원본 건수로 쪽 누락 점검, 정정 접두 분류), `pit_artifacts.py`(내용 주소 불변 보관소, 변경 바이트는 새 버전, 실패·해시 불일치도 행으로 보존), `pit_values.py`(연간 파싱 값→`pit_annual` 수신 형태, 부채는 명시 수용 시에만, 세율·배당은 매핑 안 함), `pit_acquire.py`(후보 선택→내려받기→보관→파싱→매핑 주입식 흐름, 요청 예산), `pit_verify.py`(수용 기준 점검과 미해결 정정 보고), `tools/pit_pilot.py`(오프라인 `project`/`verify`, `--live` 거부), 테스트 `tests/test_pit_*.py`(변이 검사로 생존 변이를 테스트로 보강). **잠정(실제 응답·원문으로 검증 전)**: OpenDART 목록 응답 필드명, `parse_viewer` 키 이름, 접수 목차에서 연결재무제표 노드를 찾는 실제 방법과 기간 계약 구성은 구현하지 않았고 실제 표본이 필요한 2단계 몫. Codex 1차 교차 검토(`gpt-6-astra`/medium)의 지적 12건(반복 취득이 변경된 바이트를 정상으로 만듦·파싱 결과의 접수번호/회사/기준이 요청과 묶이지 않음·검증기가 자기 자신과 비교·정정 누락 구간이 사라짐·잠금 범위·손상된 기존 원문 신뢰·임시 파일 이름 충돌·해시 경로 이탈·목록 응답 모순·제목 문법·탐색 요청이 예산을 우회·입력 형식 오류) 중 직접 재현한 것을 수정함: 보관소에 미해결 상태(`state`/`resolve`)와 한 잠금 아래의 이력 읽기·분류·추가, 취득은 접수번호·회사·기준 일치와 미해결 차단, 검증기는 독립 오라클(접수일 다음 거래일 기대값과 선택 값 비교)과 회사·기간별 미해결 구간 보고, 목록은 쪽 크기·total_page 일치와 모호한 제목을 `uncertain`으로 분리. 변이 검사와 killer 테스트 보강. 2차 교차 검토(12건 중 8건 완료·4건 부분 + 신규 결함)도 반영: 검증기의 유효성 규칙을 `pit_annual`과 독립으로 재기술해 production 검증기 결함을 불일치로 드러내고, 투영 행 집합 전체를 기대값과 정확히 비교(중간에 끼어드는 값·그림자 행·중복 행 검출), 숨긴 차단 기록 검출, 미해결 구간을 회사·실제 사업연도에 묶고 목록 항목의 접수일·회사·기간 불일치를 보고, 합의된 원문을 다시 받으면 미해결이 아님, 이상한 파서 기록이 예외로 새지 않음, 목록의 모순된 메타데이터와 모호한 제목의 회사·기간 힌트 보존, CLI 입력 검증 강화, `trial_log` 잠금이 Windows의 `PermissionError`도 재시도. 알려진 한계: 보관소·검증기의 전체 재스캔은 입력 크기에 대해 이차 비용(실측 안 함), `fsync` 제거 변이는 테스트로 못 잡음(전원 차단 내구성 미증명).
  - PIT 수집 어댑터 설계(사용자 결정: 달력 (a) 네이버 지수 일봉, 대상 효성중공업·롯데케미칼·상장폐지 1곳(잠정 도레이케미칼, 코드·조회 가능 여부 미확인), SK하이닉스 제외, 약관 확인은 사용자): `docs/review/design_PIT_collection_adapter_2026-11-03.md` 개정 1(Codex 교차 검토 8건 반영). 설계·구현 모두 실제 네트워크 호출 0회. 핵심 정정: 기존 `_collect_inventory`는 원본·정정본을 기간 중복으로 거부하므로 PIT 경로는 우회, 원천 `available_at`(접수일)은 유지하고 별도 PIT 입력을 `pit_annual`에 넘김, 취득·계약 구성(`pit_acquire`) 단계 추가, 세율·부채는 근거 전까지 비움, 공개 뷰어 조회 조건도 사용자 약관 확인 범위에 포함.
  - Codex 버그 유형 점검(5번, `gpt-6-astra`/medium, 읽기 전용): 7건 발견(2건 메모리 재현), 제품 코드는 수정하지 않음. 지수 추세 이동평균 비교의 부동소수 불일치(`trend_following.py`)와 보유 시세 갱신 실패 시 후퇴(`holding_market.py`)는 코드 읽기로 직접 확인. 상세 `docs/review/review_codex_bug_class_hunt_2026-11-03.md`. ①(지수 추세 판정 평균)·⑥(보유 시세 실패 시 후퇴)은 main에 반영됨. ②~⑤·⑦(보유 오프라인 대기 수정 덮어쓰기, 연구 세션 낡은 저장, 시장 캐시 정책 파일 무효화, 시장 확장 CLI 잠금, 텔레그램 영수증 원자 게시)도 사용자 승인("5번 나머지 고치기")으로 수정, 회귀 테스트 5개 파일 추가(앱 코드 변경이라 서버 재시작 필요).
  - 실패 테스트 원인(Codex 위임은 읽기 전용 제한으로 실행 불가해 Claude Code가 임시 복사본에서 직접 진단): `test_auto_refresh` 5건 = 테스트 순서 의존(대시보드 AppTest가 `load_local` 패치 중 `batch` 등을 처음 import해 가짜 객체가 남음), 테스트에 import 정리 추가로 21개 통과(제품 코드 문제 아님). 비공식 UI 8건: `test_daily_ui`·`test_viewer_ui`는 포트 8501 서버 필요, 나머지 6건(`holdings_entry`·`discovery_financial`·`financial_table`·`live_dashboard`·`market_refresh`·`workspace_audit`)은 **2026-10-20 커밋(`2f8bdaf`)에서도 동일하게 실패** — 오늘 작업의 회귀가 아니라 이전부터의 문제. Codex(gpt-6.1-sol)가 원인을 규명하고 Claude Code가 임시 복사본에서 독립 재실행해 6건 모두 종료코드 0 확인: 전부 **테스트만의 취약점**(제품 변경 불필요) — 바뀐 문구(`holdings_entry`), SVG 2개로 바뀐 재무 그림(`discovery_financial`), 접힌 증거 표(`financial_table`), 제거된 `#overviewTable`·닫힌 `<details>` 안의 scatter 버튼(`live_dashboard`·`market_refresh`), 검토 모델이 상세 버튼을 켜는 픽스처(`workspace_audit`). 해당 테스트 6개를 수정(이 커밋). 남은 비공식 UI 실패는 포트 8501 서버가 필요한 `test_daily_ui`·`test_viewer_ui` 2개. 임시 복사본은 삭제함.
  - Codex PIT 설계 교차 검토 요약: `docs/review/review_codex_PIT_path_2026-11-03.md` (제안, 미구현, 사용자 승인 전 구현 금지).
  - Codex 독립 재점검(승인 "3개 다 진행"의 일부, 오늘 신규 코드 대상, 읽기 전용) 지적 중 재현된 것을 수정: (1) 추세 상수 진단의 SMA 합산 방식이 `technical()`과 달라 부동소수 경계에서 기준 판정이 어긋남 → 누적합 방식으로 통일, 기준 불일치가 있으면 종료코드 4로 결과 사용 금지; (2) 시도 로그 동시 쓰기 시 같은 index가 두 번 기록될 수 있음 → 교차 프로세스 잠금(.lock, 고아 잠금은 수동 정리); (3) 마지막 줄 개행 없는 로그에 이어 쓰면 손상 → 거부; (4) `top_n` 0/음수 거부; (5) 변이에 살아남던 테스트(부트스트랩 분산, 동순위 평균순위, RS=70 경계) 보강, 평가 전 기록 순서 테스트 추가(`tests/test_codex_review_fixes.py`, 변이 5종 검출). 미수정·보고만: 겹침 모의의 Bartlett/블록 길이 고정에 따른 지속 편향(Q07 문서에 명시), SQLite `mode=ro` 비보장 주장(운영 DB는 롤백 저널 모드로 확인, WAL이면 사이드카 파일 가능), `manifest()`는 메타데이터 비교이며 증명이 아님.
  - 품질 점수(S_long) 표시 보강(승인 "점검 진행"→"보강 진행"): 코드 점검 결과 `quality_score`/`S_long`은 순위·후보 자격·추천 어디에도 쓰이지 않고 표시만 2곳(`app.py` 기존 품질 보기, `report.py` 보고서)이며 실제 자료에서는 계산되지 않는다. `app.py` 캡션에는 "순위·후보 자격·추천에 쓰이지 않는 참고 표시"와 "시점별 연간 재무가 없으면 계산되지 않음"을, `report.py` 보고서에는 앞의 참고 표시 문구만 덧붙였다(점수 계산·규칙 불변). 테스트 `tests/test_quality_score_disclosure.py`(수정 전 실패 확인). 실제 화면을 직접 열어 확인하지는 않음.
  - 추세 상태 내부 상수 민감도(S10 후속, 승인 "진행"): `tools/trend_sensitivity_report.py`가 저장 일봉으로 `price_trend_status`를 상수 하나씩 바꿔 재계산(기준 재계산을 `technical()`과 기업별 대조: 644개 불일치 0, 변이 7종 검출). **변형 18개를 평가 전에 시도 로그에 기록**(전부 rejected, 로그 누적 31회, head_digest `87ce5a85e51a9723ed071323da0d39bcff7d46dcdd34fb835ac7716150b3b7c8`). 데이터 폴더 124,883개 파일·DB 해시 실행 전후 동일. 결과: 후보를 가르는 것은 "종가>50>150>200일선" 배열(빼면 추천 통과 5→20)과 이동평균 길이(중기 180이면 9개, 단기 40이면 구성원 교체), 200일선 상승·지수 초과수익·비교 구간은 영향 없음. 어떤 값도 채택하지 않음, 규칙 변경 근거 아님. 결과 `docs/review/result_S10_trend_status_sensitivity_2026-11-03.md`.
  - 임계값 민감도 진단(S10, 승인 "진행"): `tools/threshold_sensitivity_report.py`가 필터를 하나씩 바꿔 통과 수·유지/추가/탈락과 조건별 단독 차단을 낸다(현재 규칙은 `propose`와 통과 집합 일치를 테스트로 고정, 방향 변이 6종 검출). 실제 시장 모집단에 읽기 전용 실행하고 **변형 13개를 평가 전에 시도 로그에 기록**(전부 rejected, 로그 누적 13회, head_digest `9b3d01d5871ba1c2e7eae8411a8608f8f2e1bf58c3d9bbae1c58e53682e5e60b`, `.local/trial-log/work.jsonl` Git 제외). 데이터 폴더 124,883개 파일·DB 해시 실행 전후 동일. 결과: RS·1개월 RS·200일선 임계값은 후보에 관여하지 않고(단독 차단 0), 후보를 가르는 것은 `price_trend_status` 복합 규칙(628개 탈락, 풀면 5→27)과 재무 컷(매출 YoY 5→7개/20→2개, 부채 150→4개). 어떤 값도 채택하지 않음. 결과 `docs/review/result_S10_threshold_sensitivity_real_pool_2026-11-03.md`.
  - 추천 초안 점수 진단(Q09 후속, 승인 "추가 진행"): `tools/recommendation_score_report.py`가 `propose`의 필터·점수를 재현(테스트로 일치 고정)해 깔때기·구성항 상관·cap·한 항 제거 겹침을 낸다. 실제 시장 모집단(저장 스냅샷+시장 캐시, 새로고침 미실행)에 읽기 전용 실행: **2,428개 중 5개만 통과**(추세 조건 탈락 629개가 최대), 데이터 폴더 124,883개 파일 실행 전후 동일. 점수 가중치는 현재 후보 구성에 영향이 없고 하드 필터가 결정한다. 결과 `docs/review/result_Q09_recommendation_score_real_pool_2026-11-03.md`.
  - 요인 중복 진단(Q09 T1): `tools/factor_overlap_report.py`(요인 간 순위 상관·한 요인 제거 시 상위 N 겹침·점수 미계산 사유). 합성 fixture 실행 후 사용자 승인("실행")으로 **실제 저장 스냅샷에 읽기 전용 실행**했다(SQLite `mode=ro`, 파일 복사 없음, 운영 DB 해시 `10e742e8cd5abe4f…` 전·중·후 동일). 3개 기업 모두 점수 미계산 — **장기 점수 S_long은 현재 실제 자료로는 계산되지 않는다(휴면)**: 실제 적재 경로가 `annual`을 채우지 않아 Q·G·C·V가 결측. 집계는 `docs/review/result_Q09_factor_overlap_real_snapshot_2026-11-03.md`.

Pending:
- **자료 경로 미확정(Q01~Q03)**: 시점별 상장·상폐·상장주식수, DART 공개 시각·정정 빈티지, 조정계수·정산가 공식 경로 미확인. 2008 일별 시총·주식수는 KRX OPEN API(2010~) 범위 밖. 접수시간 개정(2024-04-25, hwp)과 KRX 총수익지수 방법서 미열람.
- **구조 공백**: 시도 로그는 S10 민감도 진단 31회(필터 13 + 추세 상수 18)에만 쓰였고 그 밖의 탐색에는 연결되지 않음(앞으로의 임계값 변형은 모두 기록 후 평가). 겹침 보정 추론은 합성 모의 실험까지만이고 앱·보고에는 반영하지 않음. 시기별 비용 버전표(Q04)와 계획·코호트 간 집계의 분모 표시(Q10) 없음. 장기 점수 S_long은 실제 자료로 계산되지 않음(위 결과). 추천 초안 점수 진단은 실행했고 통과 5개뿐이라 점수 가중치가 후보 구성에 영향을 주지 않음(하드 필터 임계값이 실질 결정 규칙).
- 사용자 행위 필요: KRX OPEN API 키 신청·약관 동의, OpenDART 키, 법령 시행일별 조문(2008 증권거래세율)·농특세 별표 확인.
- 비공식 UI 테스트 8개 중 6개는 테스트 취약점으로 규명·수정했고 2개(`test_daily_ui`, `test_viewer_ui`)는 8501 Streamlit 서버가 필요하다. `tests.test_auto_refresh` 5건은 테스트 순서 의존으로 수정했다.
- `research_sessions.py`는 agent를 Codex/Claude로만 허용하고 작성자≠검토자를 강제한다. Claude 중심 전환: agent 라벨과 model ID가 모순되면(Codex+claude 계열, Claude+gpt/codex/o 계열) 가져오기를 거부하는 검사 추가(`label_matches_model`, 테스트·변이 3종 검출). 역할 고정(저자=Claude, 검토자=Codex 강제)은 하지 않음 — 기존 유연성 유지, 사용자 결정 필요 시 별도.
- 주간 연구노트 등록 Codex 자동화(월 09:00, 옛 경로 `신영재\한국\INVESTMENT`)의 Claude 재구성 미착수. 예약 경로가 새 `.venv`로 동작하는지 미확인.
- 유지: home Telegram watch 2회 실수신·최신 코드 수신·과거 home RSS 원인 확인은 이전 인계 기준 미실행. `.venv-codex-backup` 삭제는 며칠 정상 운영 후 사용자 확인. ChatGPT Pro 종료 전 대화 내보내기 여부 미확인.

Next task: 사용자가 정한다. Codex 교차 검토 결과(PIT 설계 Q01~Q03, 실패 테스트 원인, 오늘 신규 코드 재점검)를 확인하고 반영 범위를 정한다.
Next action: 사용자가 지정하면 work Primary 작업 워크트리에서 기존 정본·상태를 읽고 그 범위만 수행한다. 이동평균 기간 등 투자 규칙은 S10 진단 결과만으로 바꾸지 않는다. 사용자 행위가 필요한 항목(KRX/OpenDART 키·약관·법령 조문 확인)은 대신하지 않는다.
Recommended next agent: Claude Code — 구현·검증·인수인계. Codex 교차 검토는 Q01~Q10 문서의 사실 대조(초록 수준 한계 포함)에 한정하며 승인된 기존 검토 계약에 따른다.
Recommended model: 기존 사용자 설정 유지
Recommended reasoning: High (PIT·편향·자료 계약), 단순 문서 정리는 Medium
Escalation condition: 과거자료 부재·정정 vintage/상폐 정산 미확보·동시쓰기/divergence·지표 변경 필요·약관상 보존/재배포 제한 해석(KRX OPEN API) 필요 시 근거를 보존하고 해당 단계 보류
Branch: shinyj0270-afk/invest (재사용 작업 워크트리); main (운영 원본)
Commit: f86a6321742338b7cd918d505100f97c13090eca (이번 문구 보강 직전 기준, 이전 결과를 push 완료한 SHA)
Remote status: 반영 직전 원본 main·작업본·origin main 모두 f86a632 일치(0/0). 이번 문구 보강·인계 commit/push는 작성 시 verification pending. 최종 보고 및 다음 START 실제 Git로 전송 commit을 확인한다.

Notes:
- 검증(구현): 신규 테스트 `tests.test_trial_log` 5·`test_trial_log_cli` 2·`test_overlap_coverage_sim` 7·`test_factor_overlap_report` 7개 OK. 방향·래그 의존 로직은 일부러 깨뜨려 테스트가 실패하는 것을 확인한 뒤 복원. 관련 기존 `test_dual_pc` 13·`test_research_sessions` 4·`test_research_followup` 8·`test_leader_strategy` 7·`test_portfolio_risk` 14개 OK. `validate_share_candidates.py`(UI 제외) PASS·경고 0. 작업 워크트리에서 `tools/verify_portable.py`를 단독 실행하면 `config/local.json`이 없어 `Explicit matching PC profile required`로 실패하는 것은 기존 동작이며 공식 검증기의 같은 항목은 PASS.
- 검증(앞선 CLOSE 실행): 문서 10개의 상대 링크 존재 확인, `tests.test_dual_pc` 13개·`tests.test_research_sessions` 4개 OK, `git diff --check` 0, `tools/pc_check.py --phase finish` clean(ahead/behind 0, 진행 Git 작업 0, 추적 private 경로 0, 예약 false). 공식 UI 23개 PASS는 `80e3391` 시점 실행 결과이며, 이후 신규 도구·테스트, `app.py`/`report.py` 문구, `research_sessions` 라벨 검사, `trial_log` 보강이 있었고 공식 UI 검증기는 그 이후 재실행하지 않았다.
- 한계: Q01~Q10은 조사 기록이며 지표·비용·배분·임계값 도입 승인이 아니다. 논문 본문 미열람, 네이버 증권·WICS·SSRN은 접근 제한으로 못 열었고 우회하지 않았다. 검색 결과 중 삽입 지시문이 섞인 페이지(cavac.at)는 열지 않았다.
- 원본 반영: 오늘 9회(`80e3391`, `de85832`, `dd47f78`, `c8d8302`, `61fe566`, `d63ef9f`, `3c8e46f`, `c79e8d5`, `f86a632`)+이번 문구 보강 1회 예정(앱 코드 변경이라 안전 재시작 필요). 재시작 1회(`61fe566`의 신규 모듈로 `restart_required=true` → 사용자 입력 보관 확인 후 안전 재시작 HTTP 202, build/source 일치·`restart_required=false` 확인). 신규 모듈·도구는 앱이 import하지 않아 동작 변화 없음. 이후 `3c8e46f`·`c79e8d5` 반영 때도 같은 방식으로 안전 재시작(HTTP 202, build/source 일치). 어제 `.venv` 교체 시 서버 재시작 1회. 사용량 교대 0·비용 미집계. ChatGPT Deep Research 2회 실행(구독 한도 소모, 결과 무효).
- `config/share_candidates.json`에는 Codex 검토 문서 3개만 있고 Q01~Q10 문서는 등록하지 않았다(공유 후보 여부는 별도 결정). 중앙 Wiki 수정 없음. 결과 발행·주문 0. 진단 실행을 위해 저장 DB·시장 캐시·재무자료·저장 일봉을 읽기 전용으로 읽었다(쓰기 없음, 실행 전후 파일 목록·해시 동일).
- 다른 PC(home) 수신·실행 미확인. 집에서는 `fetch` 후 `pull --ff-only`로 받는다. 이번 변경에는 문서뿐 아니라 코드·테스트(진단 도구, 화면 문구, research_sessions 라벨 검사, trial_log 잠금 등)가 들어 있으므로 받은 뒤 해당 테스트와 실행 환경을 별도로 확인해야 한다. 내장 브라우저의 ChatGPT 로그인은 사용자가 직접 한 세션이며 계정·설정은 바꾸지 않았다.
- PROJECT_STATE에 이번 전환·조사 항목을 추가했다. 이전 인계(Codex 11-03 검토 블록)는 Git 이력(`3ac6b2c`)에 보존된다.

---

## [보존] home Orca 작업본(`shinyj0270-afk/invest`) 로컬 전용 기록 — 2026-11-02 머지로 원본에 통합

아래는 집 PC Orca 워크트리(`C:\Users\andrew\orca\workspaces\Investment\invest`)에만 있던 반영되지 않은 로컬 기록이다. 원본 main에 커밋/푸시된 적이 없어 이번에 머지하며 보존 목적으로 통째로 옮겼다. 내용은 작성 당시 그대로이며 이후 실제 상태(원격 behind 수 등)와는 다를 수 있다.

### 로컬 CLOSE 기록 — 2026-10-30 (원격 인계 미완료)

Updated: 2026-10-30T21:52:45+09:00
Last agent: Codex
Last PC: home Secondary (기존 사용자 확인 및 이번 pc_check)
Last task: START/CLOSE 점검 및 Orca 재시작 후 미완료 확인
Completed:
- 10/29 pc_check finish: 원본main clean·진행Git작업0·추적개인경로0·예약false. 집 작업본 CURRENT_HANDOFF 기존 미커밋43줄 보존, diff --check PASS. 새 기능/자료/앱 검증은 실행하지 않았다.
- 10/29 실제fetch/ls-remote로 원격2475bd8b76f0f747527829e0e3105b9c2c54592e 확인, 집HEAD4937bb6 대비 behind8/ahead0. 원격 변경에는 동일 CURRENT_HANDOFF와 기능코드가 포함된다. 원격 인계의 RSS수정/운영반영은 회사 기록이며 집수신/실행 성공으로 표시하지 않는다.
- 10/30 재시작 후 HEAD·원격추적ref·로컬인계 상태 재대조: 새commit/merge/push/마감문서 저장이 재시작 전에 없었음을 확인. 이번에는 로컬 마감기록만 추가한다. 기존 인수정정과 과거기록은 아래 보존한다.
Pending:
- 집 미커밋 인계와 원격 최신 인계의 대조·통합 및 최신코드 수신. 자동stash/reset/clean/덮어쓰기/강제push 없음. 원격인계 미완료, 이번재시작 후 원격 재조회는 하지 않았으므로2475bd8은10/29확인 시점이다.
Next task: 로컬 인계정정과 원격 최신인계를 보존하며 대조·통합하는 별도 작업. 완료 전 자동수신/전송 금지.
Next action: 실제Git/원격을 다시 확인하고 양쪽 인계를 비교한다. 10/23 사용자 인포맥스 유지·불필요한 재검증/공급자전환 금지·결과발행보류 결정을 보존한다. 최신기능을 과거 로컬코드로 덮어쓰지 않는다.
Recommended next agent: Codex
Recommended model: 기존 사용자 설정 유지
Recommended reasoning: High (양쪽 인계 대조)
Escalation condition: 동시쓰기·입력충돌·양쪽내용 손실 가능성 시 보존 후 중단
Branch: shinyj0270-afk/invest (home Orca); main (home 원본)
Commit: 4937bb62d6e7b3e2ca3bcba7313fa7c9c739191d (로컬HEAD, 새commit 없음)
Remote status: 10/29 actual main2475bd8, 로컬behind8. 이번CLOSE commit/push 미실행·원격인계 미완료.
Notes: 인계문서만 로컬저장. 제품코드·서버·개인DB/자료·예약·CREDIT·공통Wiki 변경없음. 재사용작업본과 기존로컬변경 보존.

### 집 인수 최종 정정 — 2026-10-23 (로컬 미커밋, 이번 인계 우선)

Updated: 2026-10-23T17:28:30+09:00 (문서 정리; SESSION CLOSE 아님)
Last agent: Codex
Last PC: home Secondary (기존 사용자 확인 유지; 프로필/개발 역할 변경 없음)
Last task: 사용자 최종 인계와 기존 미커밋 인계 대조·정리

Completed:
- 사용자 2026-10-23 최종 정정을 현재 인계 기준으로 정리했다. 아래 이전 세션 인계와 10/22 검증 기록은 이력으로 보존하며 당시 명령·Next action을 새 실행 지시로 사용하지 않는다.
- 사용자 확인(USER_CONFIRMED): 집에서 인포맥스 로그인 및 1333 기관·외국인 순매수금액 조회가 가능하다. 이번 문서 작업에서 직접 로그인·조회를 시험한 것은 아니다. 현재처럼 인포맥스를 이용하는 것을 기본으로 유지하고 기존 네이버/DART 경로·설정도 그대로 둔다.
- 이직 후 이용 가능성은 미정이나 실제 접근 문제가 생기거나 사용자가 별도 요청할 때만 비상 대비를 다룬다. 가능성만으로 인포맥스를 보조로 낮추거나 배제하지 않으며 새 공급자 조사·개발·시험·결제·확인 일정을 추가하지 않는다.
- 기존 가격/재무/수급·추세 partial 기록은 과거 검증 시점의 관찰로 보존했다. 같은 수집·계산·추세 재확인과 이미 완료된 DART·보유 복구·실행기·백업 검사를 이번 인수의 다음 작업으로 반복하지 않는다.

Pending:
- 최신 발행정책 수신/다른 발행 세션 부재 질문은 사용자가 넘어가기로 한 항목이다. 미확인·새 원격 결과 발행 보류를 유지하고 질문/발행 시험을 다시 열지 않는다. 기존 로컬 결과는 보존한다.
- watch 제한 2회·뉴스룸 RSS 등 이전 미해결은 별도 기능 후속이며 이번 인수의 필수 과제로 전환하지 않는다.
- 이 문서의 미커밋 변경은 재사용 작업본에만 있다. 아래 이전 마감 기록을 수정하거나 원본 main·원격에 반영하지 않았다.

Next task: 사용자 다음 실제 작업 지정. 현재 확인 범위에서 이번 인수 때문에 추가로 수행할 필수 작업은 없음.
Next action: 새 작업이 지정되면 기존 정본·현재 작업 상태·승인된 입력 경로를 읽고 그 요청 범위만 수행한다. 이 인계만으로 갱신·전송·설정 변경·역할 전환을 실행하지 않는다. CREDIT 데일리/빌드/서비스/자료/예약은 이번 인수 범위에서 계속 제외한다.
Recommended next agent: Codex (INVESTMENT 실제 작업이 지정된 경우)
Recommended model: 기존 사용자 설정 유지
Recommended reasoning: 기존 프로젝트 기준 유지
Escalation condition: 동시 변경·진행 Git 작업·입력 충돌은 보존하고 해당 변경만 중단
Branch: shinyj0270-afk/invest (집 재사용 작업본); main (원본)
Commit: 4937bb62d6e7b3e2ca3bcba7313fa7c9c739191d (이번 문서 정리 시작 HEAD; 새 commit 없음)
Remote status: 이번 원격 조회·수신·전송 미실행. 캐시된 origin/main을 현재 원격 최신 확인으로 표시하지 않음.
Notes:
- 이번 검증 범위는 인계 내용·기존 이력 보존·diff 확인뿐이다. 과거 앱/자료 검사를 새 PASS로 기록하지 않는다. 원자료·DB·인증·설정·서버·공통 Wiki를 변경하지 않는다.
- 집 보관/회사 점검에 관한 최종 사용자 정정은 이번 인수 판단의 근거이며 회사 상세 보고나 경로 접근을 추가로 요구하지 않는다. 전체 자료 이전 완료·회사 PC 종료·개발 Primary 전환 승인이 아니다.

### 이전 세션 인계 — 2026-10-22 (home, 과거 기록)

- 재사용작업본과 Git제외 검증/로컬자료 보존. 최종push후 clean/원격0/0 확인하고 대화세션 종료, 다음은 같은작업본의 새세션START. 양서버는 사용자사용을 위해 유지한다. 기존다른브랜치는 삭제하지 않는다.
- 제품코드변경0·예약등록0·회사인증/DB복사0·사용량교대0. 실제생성1회, 별도INVESTMENT안전재시작0(기존실행기로준비). Git fixture를 최신자료로 표시하지 않았다.
- 개인원자료·HTML·로그·.local·.venv·영수증은 각PC보존/코드공유제외. 결과Release재발행·중앙Wiki/전체세션수집없음. 이전인계는Git이력/PROJECT_STATE에 보존.

### 2026-10-22 집 인수 점검 기록 (과거; 다음 작업은 당시 계획)

- home Secondary 유지, 최신 main/재사용 작업본 bbf5e0f 안전 수신. 이번 요청은 개발 Primary·정책 전환 또는 CLOSE/commit/push가 아니다. 이 추가 기록은 재사용 작업본에만 있으며 main·원격에 미반영이다.
- 집 DB·입력·보유 캐시 및 연구 DB를 로컬 보존했고 SQLite 일관 백업 무결성 확인. 기존 입력·보유 캐시·설정 해시 유지. 승인된 네이버 검토3종목 갱신1회: 가격10/20→10/21, 관측6개 갱신, 실패종목0. 재무6/30·수급금액9/23은 보존했다.
- 갱신 partial: Yahoo KOSPI 응답의 마지막 유효일10/20과 가격일10/21 불일치. 네 시리즈 공통483개로 관측 수 자체는 충분하다. 추세 cutoff10/20 유지, 임의 추정·검증 완화·반복 수집 없음.
- 새 home 로컬 공개기업 결과 계산·pack/unpack 해시 PASS. 전체시장/검토가격10/21, 검토재무6/30. 실제 오프라인 검색→삼성전자 재무 화면 PASS, JS0·가로넘침0·외부요청0·보유iframe0. 초기 특정기업명 대기 시간초과는 기본 화면에 그 기업이 없는 검사 조건으로 확인 후 실제 검색 UI로 재검증했다.
- 오늘 원격 결과 재발행은 보류: 목적지는 private/ADMIN이고 공통 발행PC=home이나 회사 구버전/다른 발행 세션의 중복 방지 현재 상태는 미확인이다. 기존 서버 시작·중지·재시작·Telegram/DART 실호출·보유전송·CREDIT 작업은 하지 않았다.
- 다음 집 작업: Yahoo KOSPI 완료 관측일이 가격일에 도달했는지 기존 경로의 제한된 재검증으로 확인하고 추세 보류 해소를 판단한다. 회사 신규 결과를 대신 발행하거나 과거 회사 계산 전용 패치를 적용하지 않는다. watch 제한2회/RSS 오류는 이번 필수 기능으로 지정되지 않아 선택 후속으로 남긴다.
- 근거: Git 제외 validation/current/home-final-20261022/receipt.json 및 동 폴더의 갱신·추세·브라우저 개별 영수증. 상세 백업·로컬 결과는 집 개인 이전 기록에 보존. 이번 인수 요청에서는 CREDIT 최신 인계의 다음 행동을 실행하지 않는다.
