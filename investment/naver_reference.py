"""One-shot public Npay quotes, kept separate from verified Infomax valuations.

The endpoint is used by the public stock.naver.com company page. It is not a
documented stable API. Never fetch accounts, holdings, credentials or forecasts
as substitutes for historical earnings. No polling and no snapshot mutation.
"""
from datetime import datetime
import json
import math
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import requests

from .local_config import load_local

SCHEMA = 'naver-reference-0.1'
SOURCE = 'Npay 증권 공개 참고값'
TZ = ZoneInfo('Asia/Seoul')
NUMBERS = ('per', 'pbr', 'eps', 'bps', 'nowPrice', 'estimatedPer', 'estimatedEps')


def source_url(code):
    if not isinstance(code, str) or not re.fullmatch(r'\d{6}', code):
        raise ValueError('6자리 국내 종목코드 필요')
    return f'https://stock.naver.com/api/domestic/detail/{code}/detail?codeType=KRX'


def number(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = value.strip()
        if not re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?', value):
            return None
        value = value.replace(',', '')
    if not isinstance(value, (int, float, str)):
        return None
    try:
        parsed = float(value)
    except (ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def parse_reference(raw, code, retrieved_at):
    """Normalize the observed endpoint fields. Unknown quarter/basis stay null."""
    url = source_url(code)
    if not isinstance(raw, dict) or raw.get('itemcode') != code or raw.get('type') != 'ST':
        raise ValueError('네이버 종목 식별·주식 유형 불일치')
    name = raw.get('itemname')
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        raise ValueError('네이버 종목명 누락')
    fetched = datetime.fromisoformat(retrieved_at)
    if fetched.tzinfo is None:
        raise ValueError('수집 시각 시간대 필요')
    raw_time = raw.get('tradeTime', '')
    if not isinstance(raw_time, str) or not re.fullmatch(r'\d{14}', raw_time):
        raise ValueError('네이버 가격 관측 시각 누락')
    traded = datetime.strptime(raw_time, '%Y%m%d%H%M%S').replace(tzinfo=TZ)
    if traded > fetched:
        raise ValueError('수집 시각 이후 가격 관측')
    values = {k: number(raw.get(k)) for k in NUMBERS}
    per = values['per'] if values['per'] is not None and values['per'] > 0 and values['eps'] is not None and values['eps'] > 0 else None
    pbr = values['pbr'] if values['pbr'] is not None and values['pbr'] > 0 and values['bps'] is not None and values['bps'] > 0 else None
    reason = '공개 참고값: 정확한 재무기간·연결/별도·수정주가 기준 미확인. 주 분석 수치에 합산하지 않음.'
    if values['eps'] is not None and values['eps'] <= 0:
        reason += ' EPS 0 이하로 PER 비교 제외.'
    if values['bps'] is not None and values['bps'] <= 0:
        reason += ' BPS 0 이하로 PBR 비교 제외.'
    return dict(code=code, name=name, source=SOURCE, url=f'https://stock.naver.com/domestic/stock/{code}/price',
        source_url=url, retrieved_on=fetched.astimezone(TZ).date().isoformat(), retrieved_at=fetched.isoformat(),
        price_date=traded.date().isoformat(), price_time=traded.isoformat(),
        price=values['nowPrice'] if values['nowPrice'] is not None and values['nowPrice'] > 0 else None,
        per=per, pbr=pbr, eps=values['eps'], bps=values['bps'],
        financial_period=None, financial_basis=None, adjustment_basis=None,
        eps_basis='최근 4분기 지배기업귀속 이익 / 수정평균발행주식수 (보통주·우선주 합산)',
        bps_basis='최근 분기 자본총계 / 수정기말유통주식수 (보통주·우선주 합산)',
        venue='KRX', final=False, market_status=raw.get('marketStatus') if raw.get('marketStatus') in ('OPEN', 'CLOSE', 'CLOSED', 'PREOPEN') else 'UNKNOWN',
        status='reference_only', reason=reason, raw_source_values=values,
        estimated_values_excluded=True)


def fetch_references(codes, *, session=None, now=None):
    """Fetch at most 30 explicit symbols once each. Errors never become fake data."""
    codes = list(codes)
    if not codes or len(codes) > 30 or len(set(codes)) != len(codes):
        raise ValueError('중복 없는 1~30개 종목 필요')
    for code in codes:
        source_url(code)
    own_session = session is None
    session = session or requests.Session()
    if own_session:
        session.trust_env = False
    fetched = now or datetime.now(TZ).isoformat(timespec='seconds')
    bundle = dict(schema_version=SCHEMA, retrieved_on=datetime.fromisoformat(fetched).astimezone(TZ).date().isoformat(),
                  retrieved_at=fetched, companies={}, errors={})
    try:
        for code in codes:
            try:
                response = session.get(source_url(code), timeout=(5, 15), allow_redirects=False,
                                       headers={'Accept': 'application/json'})
                if response.status_code != 200:
                    raise ValueError(f'공개 조회 HTTP {response.status_code}')
                if len(response.content) > 2 * 1024 * 1024:
                    raise ValueError('공개 응답 크기 제한')
                observation_time = now or datetime.now(TZ).isoformat(timespec='seconds')
                bundle['companies'][code] = parse_reference(response.json(), code, observation_time)
            except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
                bundle['errors'][code] = type(exc).__name__ + ': 공개 조회·필드 검증 실패'
    finally:
        if own_session:
            session.close()
    if now is None:
        completed = datetime.now(TZ)
        bundle['retrieved_at'] = completed.isoformat(timespec='seconds')
        bundle['retrieved_on'] = completed.date().isoformat()
    return bundle


def cache_path(root):
    config = load_local(root)
    return Path(config['data_dir']) / config['profile'] / 'references' / 'naver_reference.json'


def load_cached_references(root, snapshot):
    """Read only local references for exact current identities; fixtures never load."""
    if snapshot.get('meta', {}).get('data_mode') not in ('user_input', 'live'):
        return {}
    try:
        path = cache_path(root)
        if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
            return {}
        bundle = json.loads(path.read_text(encoding='utf-8'))
        if bundle.get('schema_version') != SCHEMA or not isinstance(bundle.get('companies'), dict):
            return {}
        return sanitize_references(bundle['companies'], snapshot)
    except (OSError, ValueError, TypeError, KeyError):
        return {}


def sanitize_references(references, snapshot):
    """Allowlist records and regenerate URLs/status before any local HTML export."""
    if snapshot.get('meta', {}).get('data_mode') not in ('user_input', 'live') or not isinstance(references, dict):
        return {}
    result = {}
    for row in snapshot['companies']:
        record = references.get(row['code'])
        if not isinstance(record, dict) or record.get('name') != row['name'] or record.get('code') != row['code']:
            continue
        try:
            # Cached status/URL/basis can neither promote a reference nor inject URLs.
            values = record.get('raw_source_values') or {}
            raw = {key: values.get(key) for key in NUMBERS}
            traded = datetime.fromisoformat(record['price_time'])
            if traded.tzinfo is None:
                continue
            raw.update(itemcode=row['code'], itemname=row['name'], type='ST',
                       tradeTime=traded.astimezone(TZ).strftime('%Y%m%d%H%M%S'),
                       marketStatus=record.get('market_status'))
            safe = parse_reference(raw, row['code'], record['retrieved_at'])
            safe['same_price_date'] = safe['price_date'] == snapshot['meta']['price_date']
            result[row['code']] = safe
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
    return result
