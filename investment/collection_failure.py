"""Public, bounded collection diagnostics; never expose exception URLs or paths."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def failure_detail(error, *, financial=False):
    now = datetime.now(ZoneInfo('Asia/Seoul'))
    message = str(error)
    known = {
        'identity_mismatch': ('identity', '응답 종목 식별 불일치'),
        'DART 종목 식별 불일치': ('identity', 'DART 검색 결과에서 종목코드 확인 실패'),
        'DART 기업 식별 미확인': ('identity', 'DART 검색 결과가 단일 기업으로 확인되지 않음'),
        'incomplete_sessions': ('calendar', '완료 거래일 누락 또는 날짜 배열 불일치'),
        'price_date_regression': ('calendar', '기존 자료보다 오래된 가격 응답'),
        'corrected_series_invalid': ('validation', '수정주가 전체 이력 검증 실패'),
        '요청 범위의 완료된 일봉 없음': ('availability', '제공처에 요청 기간의 완료 일봉 없음'),
        'DART 재무자료 일부 조회·검증 대기': ('statements', '요청 보고서의 조회·검증을 통과한 재무자료 없음'),
    }
    stage, reason = known.get(message, ('validation', '재무자료 형식·회계 검증 실패' if financial else '가격 응답 형식·범위 검증 실패'))
    if isinstance(error, (OSError, ConnectionError)) or type(error).__name__ in ('Timeout', 'ReadTimeout', 'ConnectTimeout', 'HTTPError', 'ConnectionError'):
        stage, reason = 'network', '공개 제공처 연결·응답 실패'
    return dict(stage=stage, reason=reason, checked_at=now.isoformat(timespec='seconds'),
                retry_at=(now+timedelta(minutes=60 if financial else 30)).isoformat(timespec='seconds'))
