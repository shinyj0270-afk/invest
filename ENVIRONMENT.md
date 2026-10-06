# 현재 환경 안내

현재 실행·설치·검증은 [PC 실행/이전 안내](docs/PC_MIGRATION.md), 실제 최신 상태는 [PROJECT_STATE.md](PROJECT_STATE.md)를 확인한다. 아래 Git 미설정/Wiki 부재/집 PC 미검증 문구는 작성 당시 이력이며 현재 환경 판정에 사용하지 않는다. PC별 인증·설정·데이터는 자동 이전하지 않는다.

---

# PC별 설정 적용 · work13

work14 추가: `manual_snapshot_file`을 PC별 비공개 설정으로 읽는다. 회사 PC는 기존 수동 검토 파일을 계속 사용하고 예시/임시 home 환경은 null로 검증했다. 실제 집 PC의 파일·인증 상태는 확인하지 않았다.

config/local.json은 work와 이 작업본의 실제 project_root, data_dir=data, infomax_manual만 허용, scheduled_jobs_enabled=false로 설정했습니다. 앱/배치/수집기가 공통 investment/local_config.py를 사용합니다. runtime.local.json은 별도 인증·권한 설정 대기이며 다른 PC 프로필이면 수집을 막습니다. .venv와 DB는 각 PC 로컬 자원입니다. Wiki 지정 경로는 이번 확인에서 존재하지 않았습니다. Git 원격 미설정, 집 PC 환경 미검증입니다.

# 실행 환경 · 2026-09-28

- 사용자 지정 프로필: 회사 PC `work`. 대표 폴더: 현재 INVESTMENT. 다른 PC를 탐색하거나 자동 연결하지 않음.
- 프로젝트 `.venv`: Python 3.12.14, Streamlit 1.64.0, pandas 3.0.6, NumPy 2.5.3. 전체 버전은 requirements.lock.txt.
- 기존 Node 24.19.0과 Microsoft Edge 사용. 전역 Python/LLM Wiki 환경 변경 없음.
- 인포맥스 회사 PC 1333 저장파일은 이전 작업에서 확보. 집 PC 로그인 가능은 사용자 확인 사실. 집 PC 설치·연동·동시접속/외부 저장 권한은 검증하지 않음.
- `config/local.json`은 앱 저장소 프로필. 조회 권한 강제는 별도 `config/runtime.local.json`과 Reader에서 적용. 기본 예시는 unknown 및 모두 false.
- 키움 토큰/공식 TR 단위/범위 검토, OpenDART 키/회사 고유번호, 인포맥스 자동 연동 권한은 설정 대기. 비밀값을 검색하거나 출력하지 않음.
- 두 서버는 이 PC loopback만 사용: 기존 검토본 8766, 새 Streamlit 앱 8501. 외부 배포 없음.
- 예약 스크립트만 작성. 실제 등록·상시 서버 지정·PC간 자료/인증 동기화 없음.
