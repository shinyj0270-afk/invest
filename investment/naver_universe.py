"""Public domestic discovery data, separate from the reviewed Infomax snapshot.

The published Npay market page uses these listing and industry endpoints. Listing
financial ratios have no period/accounting metadata, so they remain exploratory.
The public, page-linked Wise summary can provide dated accounting labels on demand.
"""
from copy import deepcopy
from datetime import date, datetime
from html.parser import HTMLParser
import calendar
import math
import re
import time
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests

from .naver_reference import number

SCHEMA = 'naver-universe-0.1'
BASE = 'https://stock.naver.com'
WISE = 'https://navercomp.wisereport.co.kr'
TZ = ZoneInfo('Asia/Seoul')
MARKETS = {'KOSPI': '0', 'KOSDAQ': '1'}
FINANCIAL_INDUSTRIES = {'은행', '증권', '생명보험', '손해보험', '기타금융', '창업투자', '카드'}
RAW_NUMBERS = ('nowPrice', 'marketSum', 'eps', 'per', 'pbr', 'roe', 'roa',
    'propertyTotal', 'debtTotal', 'sales', 'salesIncreasingRate', 'operatingProfit',
    'operatingProfitIncreasingRate', 'netIncome', 'tradeVolume', 'tradeAmount',
    'prevChangeRate', 'week52HighPrice', 'week52LowPrice')


def _code(code):
    # Recent KRX codes may contain letters; this independent discovery contract
    # does not silently drop them to fit the older six-digit snapshot contract.
    if not isinstance(code, str) or not re.fullmatch(r'[0-9A-Z]{6}', code):
        raise ValueError('국내 6자리 종목코드 오류')
    return code


def _now():
    return datetime.now(TZ).isoformat(timespec='seconds')


def _timestamp(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('수집 시각 시간대 필요')
    return parsed


def listing_url(market, start=0, size=100):
    if market not in MARKETS or not isinstance(start, int) or start < 0 or not isinstance(size, int) or not 1 <= size <= 100:
        raise ValueError('시장·페이지 범위 오류')
    return BASE + '/api/domestic/market/stock/default?' + urlencode(dict(
        tradeType='KRX', marketType=market, orderType='marketSum', startIdx=start, pageSize=size))


def _get(session, url, *, html=False, headers=None):
    response = session.get(url, timeout=(5, 20), allow_redirects=False,
                           headers=headers or {'Accept': 'application/json'})
    if response.status_code != 200:
        raise ValueError(f'공개 조회 HTTP {response.status_code}')
    if len(response.content) > 5 * 1024 * 1024:
        raise ValueError('공개 조회 응답 크기 초과')
    return response.content.decode('utf-8') if html else response.json()


def _session(session):
    if session is not None:
        return session, False
    session = requests.Session()
    session.trust_env = False
    return session, True


def _ratio(numerator, denominator):
    if numerator is None or denominator is None or denominator <= 0:
        return None
    value = numerator / denominator * 100
    return value if math.isfinite(value) else None


def classify(row):
    """Exclusions are explicit; a retained stock is a candidate, not a verified class."""
    name = row['name']
    industry = row.get('industry', '미분류')
    reasons = []
    kind = row.get('source_security_type')
    if kind is not None and kind != 'ST':
        reasons.append('네이버 주식(ST) 이외 상품')
    if re.search(r'(?:\d+)?우(?:[BC])?$|우선주$', name):
        reasons.append('종목명에 우선주 표기')
    if re.search(r'스팩|기업인수목적|\bSPAC\b', name, re.I):
        reasons.append('기업인수목적회사 표기')
    if re.search(r'리츠|\bREIT', name, re.I):
        reasons.append('리츠 표기')
    if name in ('맥쿼리인프라', 'KB발해인프라'):
        reasons.append('상장 인프라 투자회사')
    if industry in FINANCIAL_INDUSTRIES or any(n in FINANCIAL_INDUSTRIES for n in row.get('industry_source_labels', [])):
        reasons.append('네이버 업종 분류: 금융업')
    if reasons:
        return dict(eligibility='excluded', security_type='excluded', analysis_profile='excluded',
                    classification_verified=False, exclusion_reasons=reasons)
    unknown = kind is None or industry in ('미분류', '기타', '') or row.get('industry_conflict') is True
    return dict(eligibility='unknown' if unknown else 'candidate', security_type='ordinary_candidate',
        analysis_profile='unknown' if unknown else 'nonfinancial_candidate', classification_verified=False,
        exclusion_reasons=['상품 유형 또는 업종 분류 확인 필요'] if unknown else [],
        classification_note='공개 주식 유형·종목명·업종으로 제외 대상을 거른 후보. 법적 주식 종류 전체 검증은 아님.')


def normalize(raw, market, retrieved_at, industry=None):
    if not isinstance(raw, dict) or market not in MARKETS or raw.get('sosok') != MARKETS[market]:
        raise ValueError('목록 시장 불일치')
    code = _code(raw.get('itemcode'))
    name = raw.get('itemname')
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        raise ValueError('목록 기업명 오류')
    observed = _timestamp(retrieved_at)
    values = {key: number(raw.get(key)) for key in RAW_NUMBERS}
    assets, liabilities = values['propertyTotal'], values['debtTotal']
    equity = assets-liabilities if assets is not None and assets >= 0 and liabilities is not None and liabilities >= 0 else None
    per = values['per'] if values['per'] is not None and values['per'] > 0 and values['eps'] is not None and values['eps'] > 0 else None
    pbr = values['pbr'] if values['pbr'] is not None and values['pbr'] > 0 and equity is not None and equity > 0 else None
    metrics = dict(price=values['nowPrice'] if values['nowPrice'] is not None and values['nowPrice'] > 0 else None,
        market_cap_eok=values['marketSum']/1e8 if values['marketSum'] is not None and values['marketSum'] > 0 else None,
        roe_pct=values['roe'], operating_margin_pct=_ratio(values['operatingProfit'], values['sales']),
        debt_ratio_pct=_ratio(liabilities, equity), revenue_growth_pct=values['salesIncreasingRate'],
        per=per, pbr=pbr, eps=values['eps'], change_pct=values['prevChangeRate'])
    row = dict(code=code, name=name, market=market, industry=industry or '미분류',
        source_security_type=raw.get('type') if isinstance(raw.get('type'), str) else None,
        metrics=metrics, raw_source_values=values, source='Npay 증권 공개 시장 목록',
        url=f'{BASE}/domestic/stock/{code}/price', observed_on=observed.astimezone(TZ).date().isoformat(),
        retrieved_at=retrieved_at, price_date=None, financial_period=None, financial_basis=None,
        final=False, status='reference_only',
        metric_basis='목록 제공 재무 요약: 정확한 기간·연결/별도 미표시',
        derived_metrics=dict(operating_margin_pct='목록 영업이익 / 목록 매출 × 100',
                            debt_ratio_pct='목록 부채 / (목록 자산 - 목록 부채) × 100'),
        data_quality=['실적 보고기간·연결/별도 미확인: 기업 발굴 참고용',
                      'PER과 PBR은 공급자 기준·갱신 시점이 다를 수 있음',
                      '목록에 가격 관측 시각 없음: 수집일을 종가 기준일로 대체하지 않음'],
        trading_status={key: raw.get(key) if isinstance(raw.get(key), str) else None
            for key in ('tradeStopYn', 'manageStatusGb', 'marketAlertType', 'marketStatus')})
    row.update(classify(row))
    return row


def fetch_listing(*, markets=('KOSPI', 'KOSDAQ'), session=None, page_size=100,
                  max_pages=100, progress=None, pause=0.05):
    """Follow the same bounded pages as the public list; no DB/cache mutations."""
    if not markets or len(set(markets)) != len(markets) or any(m not in MARKETS for m in markets):
        raise ValueError('국내 시장 지정 오류')
    listing_url(markets[0], 0, page_size)
    if not isinstance(max_pages, int) or not 1 <= max_pages <= 100:
        raise ValueError('페이지 상한 오류')
    session, own = _session(session)
    bundle = dict(schema_version=SCHEMA, source='Npay 증권 공개 시장 목록', retrieved_at=_now(),
        companies=[], market_counts={}, pagination={}, errors=[],
        completeness_note='가격순 페이지를 모두 순회한 관측 집합. 장중 순위 이동으로 누락·중복 가능하며 상장 전체 기준 명부는 아님.')
    seen = set()
    try:
        for market in markets:
            count = 0
            state = dict(pages=0, terminal_page_seen=False, duplicate_count=0, invalid_rows=0)
            bundle['pagination'][market] = state
            for page in range(max_pages):
                try:
                    # startIdx is the page index used by Npay's list UI, not a row
                    # offset.  Passing 100 for page two silently returns the first
                    # page again, so use 0, 1, 2 ... regardless of page size.
                    raw = _get(session, listing_url(market, page, page_size))
                    if not isinstance(raw, list) or len(raw) > page_size:
                        raise ValueError('목록 응답 형식 오류')
                except (requests.RequestException, ValueError, TypeError) as exc:
                    bundle['errors'].append(dict(stage='listing', market=market, page=page, reason=type(exc).__name__))
                    break
                fetched = _now()
                state['pages'] += 1
                for source in raw:
                    try:
                        row = normalize(source, market, fetched)
                    except (ValueError, TypeError):
                        state['invalid_rows'] += 1
                        continue
                    if row['code'] in seen:
                        state['duplicate_count'] += 1
                        continue
                    seen.add(row['code'])
                    bundle['companies'].append(row)
                    count += 1
                if progress:
                    progress(dict(stage='listing', market=market, page=page, loaded=count))
                if len(raw) < page_size:
                    state['terminal_page_seen'] = True
                    break
                if pause:
                    time.sleep(min(max(pause, 0), 2))
            bundle['market_counts'][market] = count
        bundle['retrieved_at'] = _now()
        bundle['retrieved_on'] = _timestamp(bundle['retrieved_at']).date().isoformat()
        bundle['pagination_complete'] = all(p['terminal_page_seen'] for p in bundle['pagination'].values())
        return bundle
    finally:
        if own:
            session.close()


def attach_industries(bundle, *, session=None, progress=None, pause=0.05):
    """Bulk public industry membership with conflicts and collection errors retained."""
    result = deepcopy(bundle)
    session, own = _session(session)
    memberships = {}
    industry_rows = []
    errors = result.setdefault('errors', [])
    try:
        for start in range(0, 5):
            url = BASE + '/api/domestic/market/upjong/list?' + urlencode(dict(startIdx=start, pageSize=100, sortType='changeRate'))
            page = _get(session, url)
            if not isinstance(page, list) or len(page) > 100:
                raise ValueError('업종 목록 형식 오류')
            industry_rows.extend(page)
            if len(page) < 100:
                break
        seen_industries = set()
        for industry in industry_rows:
            if not isinstance(industry, dict):
                errors.append(dict(stage='industry', reason='invalid industry'))
                continue
            no, name = industry.get('no'), industry.get('name')
            if (not isinstance(no, str) or not no.isdigit() or no in seen_industries
                    or not isinstance(name, str) or not name.strip() or len(name) > 100):
                errors.append(dict(stage='industry', reason='invalid industry'))
                continue
            seen_industries.add(no)
            loaded = set()
            finished = False
            # The miscellaneous group includes ETFs/ETNs; still collect membership
            # so genuine unmapped stocks remain visible as unknown, not nonfinancial.
            for start in range(0, 50):
                url = BASE + f'/api/domestic/market/upjong/{no}/stocklist?' + urlencode(dict(
                    marketType='ALL', orderType='marketSum', startIdx=start, pageSize=100))
                try:
                    page = _get(session, url)
                    if not isinstance(page, list) or len(page) > 100:
                        raise ValueError('업종 종목 목록 형식 오류')
                    for raw in page:
                        code = _code(raw.get('itemcode'))
                        memberships.setdefault(code, set()).add(name)
                        loaded.add(code)
                    if len(page) < 100:
                        finished = True
                        break
                except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
                    errors.append(dict(stage='industry', industry=no, reason=type(exc).__name__))
                    break
                if pause:
                    time.sleep(min(max(pause, 0), 2))
            if not finished:
                errors.append(dict(stage='industry', industry=no, reason='pagination incomplete'))
            if progress:
                progress(dict(stage='industry', industry=no, loaded=len(loaded), completed=len(seen_industries), total=len(industry_rows)))
            if pause:
                time.sleep(min(max(pause, 0), 2))
        for row in result['companies']:
            names = sorted(memberships.get(row['code'], set()))
            row['industry'] = names[0] if len(names) == 1 else '미분류'
            row['industry_conflict'] = len(names) > 1
            row['industry_source_labels'] = names
            row.update(classify(row))
        result['industry_count'] = len(seen_industries)
        result['industry_mapped_count'] = sum(r['industry'] != '미분류' for r in result['companies'])
        result['retrieved_at'] = _now()
        return result
    except (requests.RequestException, ValueError, TypeError) as exc:
        errors.append(dict(stage='industry', reason=type(exc).__name__))
        return result
    finally:
        if own:
            session.close()
