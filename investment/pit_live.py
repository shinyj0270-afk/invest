"""Minimal OpenDART client and the plan for the first live PIT call (design: docs/review/design_PIT_collection_adapter_2026-11-03.md).

Everything that touches the network goes through ONE method (`OpenDart._get`) that first charges the shared request budget, then
sends the key as a query parameter, caps the response size, and turns every failure into an exception that never contains the key.
A quota signal (response status '020' or HTTP 429) raises `QuotaStop`: the caller must stop and must not retry. The key is read only
from the OPENDART_API_KEY environment variable and is never stored, printed or logged. This module does not scrape any web viewer.
Constructing the client does no request; tests use a fake session.
"""
import io
import json
import os
import re
import zipfile
from urllib.parse import urlparse
from xml.etree import ElementTree

BASE = 'https://opendart.fss.or.kr/api/'
KEY_ENV = 'OPENDART_API_KEY'
OK_STATUSES = ('000', '013')


class QuotaStop(RuntimeError):
    """The provider signalled a request limit; stop everything and do not retry."""


class BudgetedSession:
    """Wraps any session so every GET (e.g. the calendar fetcher's) is charged to the shared budget before it is sent."""
    def __init__(self, session, budget):
        self.session, self.budget = session, budget

    def get(self, *args, **kwargs):
        self.budget.spend()
        return self.session.get(*args, **kwargs)


def key_from_env(env=None):
    value = (os.environ if env is None else env).get(KEY_ENV)
    if not isinstance(value, str) or not re.fullmatch(r'[0-9A-Za-z]{40}', value.strip()):
        raise ValueError(f'{KEY_ENV} 환경 변수가 없거나 형식이 맞지 않습니다')
    return value.strip()


class OpenDart:
    def __init__(self, key, *, session, budget, timeout=(5, 30), max_bytes=40 * 1024 * 1024):
        self._key, self.session, self.budget, self.timeout, self.max_bytes = key, session, budget, timeout, max_bytes

    def __repr__(self):
        return 'OpenDart(key=***)'

    __str__ = __repr__

    def _get(self, endpoint, params):
        self.budget.spend()                                   # raises BudgetExceeded before any network use
        try:
            response = self.session.get(BASE + endpoint, params=dict(params, crtfc_key=self._key), timeout=self.timeout, stream=True,
                headers={'User-Agent': 'Investment-local-research/1.0'})
            with response:
                if response.status_code == 429:raise QuotaStop('HTTP 429')
                response.raise_for_status()
                chunks, size = [], 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > self.max_bytes:raise ValueError('응답 크기 제한 초과')
                    chunks.append(chunk)
        except (QuotaStop, ValueError):
            raise
        except Exception as exc:                              # never let a message that contains the request URL (and key) escape
            raise ValueError('OpenDART 요청 실패: ' + type(exc).__name__) from None
        return b''.join(chunks)

    @staticmethod
    def _json(data):
        try:payload = json.loads(data.decode('utf-8'))
        except (UnicodeDecodeError, ValueError):raise ValueError('OpenDART 응답이 JSON이 아닙니다') from None
        status = payload.get('status') if isinstance(payload, dict) else None
        if status == '020':raise QuotaStop('OpenDART 요청 제한 초과(020)')
        if status not in OK_STATUSES:raise ValueError(f'OpenDART 응답 상태 {status}')
        return payload

    def corp_code_zip(self):
        data = self._get('corpCode.xml', {})
        if not data.startswith(b'PK'):
            self._json(data)
            raise ValueError('고유번호 응답이 zip이 아닙니다')
        return data

    def list_page(self, corp_code, bgn_de, end_de, page_no, page_count=100):
        if not (isinstance(corp_code, str) and re.fullmatch(r'\d{8}', corp_code)):raise ValueError('법인코드 형식 오류')
        if not all(isinstance(d, str) and re.fullmatch(r'\d{8}', d) for d in (bgn_de, end_de)):raise ValueError('날짜는 YYYYMMDD여야 합니다')
        if not (isinstance(page_no, int) and page_no >= 1 and isinstance(page_count, int) and 1 <= page_count <= 100):raise ValueError('쪽 번호·크기 오류')
        return self._json(self._get('list.json', dict(corp_code=corp_code, bgn_de=bgn_de, end_de=end_de, last_reprt_at='N', pblntf_ty='A',
            page_no=page_no, page_count=page_count)))

    def document_zip(self, rcept_no):
        if not (isinstance(rcept_no, str) and re.fullmatch(r'\d{14}', rcept_no)):raise ValueError('접수번호 형식 오류')
        data = self._get('document.xml', dict(rcept_no=rcept_no))
        if not data.startswith(b'PK'):
            self._json(data)
            raise ValueError('원문 응답이 zip이 아닙니다')
        return data


def corp_candidates(zip_bytes, *, stock_code=None, name=None):
    """Entries of OpenDART's corpCode file matching an exact stock code or exact name. Several matches are returned as they are, never chosen."""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            names = archive.namelist()
            if not names:raise ValueError('고유번호 파일이 비어 있습니다')
            info = archive.getinfo(names[0])
            if info.file_size > 200 * 1024 * 1024:raise ValueError('고유번호 파일이 너무 큽니다')
            root = ElementTree.fromstring(archive.read(names[0]))
    except (zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise ValueError('고유번호 파일을 읽을 수 없습니다') from exc
    out = []
    for item in root.iter('list'):
        row = {k: (item.findtext(k) or '').strip() for k in ('corp_code', 'corp_name', 'stock_code', 'modify_date')}
        if (stock_code is not None and row['stock_code'] == stock_code) or (name is not None and row['corp_name'] == name):out.append(row)
    return out


def plan_first_call(*, today):
    """The exact, small request list of the first live step (no network here). Sizes are unknown until the responses arrive."""
    from .market_history import _request
    requests_ = []
    for symbol in ('KOSPI', 'KOSDAQ'):
        url, _ = _request(symbol, 'index', '2023-01-02', today)
        requests_.append(dict(kind='calendar', host=urlparse(url).netloc, what=f'{symbol} 지수 일봉 2023-01-02~어제 1회(거래일 달력용)'))
    requests_.append(dict(kind='corp_codes', host='opendart.fss.or.kr', what='corpCode.xml 1회(전체 고유번호 zip, 크기 미확인)'))
    requests_ += [dict(kind='list', host='opendart.fss.or.kr', what=f'효성중공업 연간 보고서 목록(정정 포함) {n}쪽 이내') for n in (1, 2)]
    requests_.append(dict(kind='document', host='opendart.fss.or.kr', what='효성중공업 가장 최근 사업보고서 원문 1건(document.xml zip, 크기 미확인)'))
    requests_ += [dict(kind='list', host='opendart.fss.or.kr', what=f'도레이케미칼(상장폐지 후보) 2014~2018 목록 {n}쪽 이내, 고유번호가 확실히 1개일 때만') for n in (1, 2)]
    return dict(max_requests=12, min_interval_seconds=1.0, requests=requests_, viewer_scraping=False,
        storage='<INVESTMENT 작업 폴더>/.local/pit-pilot/ (Git 제외, 원문 전체 로컬 보관)',
        stop_conditions=['응답 상태 020 또는 HTTP 429(요청 제한)', '접속 제한·차단 신호', '요청 12회 도달', '점검·서버 오류(재시도 없이 중단)',
                         '고유번호가 0개이거나 2개 이상(추측하지 않음)'],
        notes=['키는 환경 변수에서만 읽고 출력하지 않음', '공개 DART 뷰어 페이지는 호출하지 않음'])


def plan_delisted_list(*, name, bgn, end):
    """List only: reuse the local corp-code zip and request at most two pages."""
    return dict(max_requests=3, min_interval_seconds=1.0,
        requests=[dict(kind='list', host='opendart.fss.or.kr', what=f'{name} annual reports {bgn}~{end}, page {n}') for n in (1, 2)],
        viewer_scraping=False, storage='<root>/.local/pit-pilot/ (local artifacts, excluded from Git)',
        stop_conditions=['corp-code file missing or name not unique', 'quota (020 or HTTP 429)', 'request budget exhausted',
                         'provider error or rejected response; no retry', 'more than two pages'],
        notes=['Reuse the stored corp-code zip; never download it', 'Read the key only from the environment; never print it', 'No viewer scraping'])
