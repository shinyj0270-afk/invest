# 소프트 UI 11-A · 통합 대시보드 적용

## 선택

- 2026-10-08 사용자 선택: 시안 11-A 코랄 ↔ 틸 소프트 UI(USER_CONFIRMED). 이전 오로라 글라스(docs/AURORA_GLASS_DESIGN.md)를 대체한다.
- 사용자 결정: 상단 가로 메뉴(주요 6개 + 더보기 14개), 전체 화면 테마 적용. 배치 변경은 홈만.
- 시안의 예시 기업·수치는 운영 화면에 쓰지 않는다. 모든 값은 기존 저장 payload에서 읽고 없으면 자료 대기로 표시한다.

## 변경 범위

- src/soft_ui.css: 뉴모피즘 면(배경과 같은 색 + 밝은/어두운 그림자), 코랄 버튼·링크, 틸 보조색, 얇은 지수 숫자. 보유 iframe(soft-legacy)과 인쇄·모바일 포함. src/aurora_glass.css 제거.
- src/home_dashboard_ui.js: 오늘의 결론, 압축 지수 카드, 섹터 맵, 업종 후보, 추천 도넛, KPI 칩.
- src/workspace.html / src/workspace.js: 상단 메뉴·검색, 상태 칩 + KPI 그룹, 홈 벤토 배치. 사이드바 자료 안내는 ‘자료 기준·연결 상태’로 이동.
- src/dashboard_upgrade_ui.js: 자료 확보를 막대로 표시. src/dashboard_journey.js: 쓰지 않게 된 홈 업종 버튼 렌더러 제거.
- investment/workspace_export.py, investment/dashboard_build.py: 새 CSS/JS 삽입, 준비 화면 색.

## 홈 판정 규칙(투자 신호 아님)

- 오늘의 결론: 기존 시장 설명 자료의 지수 방향과 200일선 위 기업 비율로만 헤드라인을 고른다. 우선순위는 좁은 상승 → 약세 → 참여 유지 약세 → 혼조 → 강세이며, 강세는 판단 가능한 모든 시장이 강할 때만. 자료가 없는 시장은 판단에서 제외하고 ‘판단 자료 대기’로 표시한다.
- 섹터 맵: 1개월 업종 RS 상위 8개. 크기 = 유효 기업 수, 색 = 표시 업종 안의 상대 21거래일 수익률(낮음 틸 ↔ 높음 코랄). 음수 수익률도 상대 비교로 표시한다.
- 업종 후보: 같은 시장·산업, 발굴 허용, 1개월 RS 내림차순 최대 5개. 추천이 아니다.
- 시장 설명 전문(분모·출처·판정 기준)은 홈 카드의 ‘해석·판정 기준’과 추세추종 화면에 그대로 유지한다.

## 검증(2026-10-08 work, 이번 실행)

- node tests/test_home_dashboard.js: 판정 규칙·색 척도·후보 선택·이스케이프·자료 대기. 구현 전 실패(모듈 없음) 확인 후 PASS.
- 격리 사본(임시 data 폴더, 실자료·DB 미사용) tools/verify_portable.py 22개 명령 PASS.
- 홈 관련 UI 6개(dashboard_home/upgrade_panels/dashboard_upgrade/dashboard_stability/market_trend_changes/dashboard_journey) PASS. 홈 구조 변경에 맞춰 3개 테스트의 확인 대상을 갱신했다.
- 합성 자료 21개 메뉴 × 1440/390px JavaScript 오류0·가로 넘침0. 운영 서버 payload를 GET으로만 읽어 새 화면에 렌더(쓰기 요청 차단): 헤드라인·타일8·후보5·KPI 표시, 오류0. 섹터 타일 글자 대비 최소 7.28, 보조 글자 4.95, 링크 5.04.
- 운영 서버 재시작·commit/push·home PC 수신은 별도 단계이며 이 문서 작성 시점에 미실행.
