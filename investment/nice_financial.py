"""Public NICE company major-finance reference; no login, storage or forecasts."""
from collections import OrderedDict
from copy import deepcopy
from datetime import date, datetime, timezone
from html import unescape
import calendar
import math
import re
import threading
import time
import requests

BASE = 'https://www.nicerating.com'
FIELDS = {'자산총계': 'assets', '총차입금': 'total_borrowings', '순차입금': 'net_borrowings',
          '부채비율(%)': 'debt_ratio', '총차입금의존도(%)': 'borrowing_dependence',
          '순차입금의존도(%)': 'net_borrowing_dependence',
          '총차입금/EBITDA(배)': 'debt_ebitda', '순차입금/EBITDA(배)': 'net_debt_ebitda'}


def canonical(name):
    name = name.upper().replace('에스케이', 'SK').replace('엘지', 'LG').replace('케이티', 'KT')
    return re.sub(r'\s|주식회사|\(주\)|㈜', '', name)


def resolve_company(html, name):
    # Require a unique company overview, exact legal-name normalization and fiscal year end.
    match = re.search(r'<th[^>]*>기업명</th>.*?<tbody>\s*<tr>(.*?)</tr>', html, re.S)
    if not match:
        raise ValueError('기업 식별 미확인')
    cells = [unescape(re.sub('<[^>]+>', '', x)).strip() for x in re.findall(r'<td[^>]*>(.*?)</td>', match[1], re.S)]
    ids = set(re.findall(r'/company/companyMajorFinance\.do\?cmpCd=(\d+)', html))
    if len(cells) != 6 or canonical(cells[0]) != canonical(name) or len(ids) != 1:
        raise ValueError('기업명·NICE 식별자 불일치')
    month = int(cells[5])
    if not 1 <= month <= 12:
        raise ValueError('결산월 미확인')
    return ids.pop(), cells[0], month


def parse_finance(raw, code, name, basis, company_id, year_end_month, retrieved_at):
    data = raw['list']; header = data['header']
    if header['accountName'] != '계정명(억원)':
        raise ValueError('재무 단위 변경')
    fields = {}
    for row in data['data']:
        key = FIELDS.get(row['accountName'])
        if not key:
            continue
        if key in fields or row['screenExpressUnitCode'] != ('4' if key in ('assets', 'total_borrowings', 'net_borrowings') else '9'):
            raise ValueError('계정 중복·단위 불일치')
        fields[key] = row
    columns = []
    for i in range(7):
        field = 'a' + str(i)
        match = re.fullmatch(r'(\d{4})\.(\d{2})\.(\d{2})<br\s*/?>\(K-IFRS\)', header[field])
        if not match:
            raise ValueError('기간·회계기준 미확인')
        end = date(*map(int, match.groups()))
        # Annual-only: interim ratios can be annualized by the provider; never mix them.
        if end.month != year_end_month or end.day != calendar.monthrange(end.year, end.month)[1] or end.isoformat() > retrieved_at[:10]:
            continue
        values = {}
        for key, row in fields.items():
            text = str(row[field]).strip().replace(',', '')
            if text in ('', '-', 'None'):
                values[key] = None
            elif re.fullmatch(r'-?\d+(?:\.\d+)?', text) and math.isfinite(float(text)):
                values[key] = float(text)
            else:
                raise ValueError('재무 수치 형식 변경')
        if any(c['period_end'] == end.isoformat() for c in columns):
            raise ValueError('연간 기간 중복')
        columns.append(dict(period_end=end.isoformat(), values=values))
    return dict(code=code, name=name, basis=basis, currency='KRW', cadence='annual', status='ready' if columns else 'unavailable',
                source='NICE신용평가 · 주요재무지표 (BIZLINE)', source_url=BASE+'/disclosure/companyGradeInfo.do?cmpCd='+company_id,
                retrieved_at=retrieved_at, columns=sorted(columns, key=lambda c: c['period_end']),
                note='NICE 원제공값 · 평가보고서의 재작성 비교재무와 차이가 있을 수 있음 · 공시일 미확인')


class NiceFinancial:
    def __init__(self):
        self.cache = OrderedDict()
        self.lock = threading.Lock()

    def lookup(self, code, basis, name):
        if not re.fullmatch(r'\d{6}', code) or basis not in ('CFS', 'OFS') or not 1 <= len(name) <= 80:
            raise ValueError('기업 식별 확인 필요')
        key = (code, basis, name)
        with self.lock:
            cached = self.cache.get(key)
            if cached and time.monotonic() - cached[0] < 3600:
                self.cache.move_to_end(key)
                return deepcopy(cached[1])
        result = dict(code=code, name=name, basis=basis, status='unavailable', columns=[])
        try:
            with requests.Session() as session:
                session.trust_env = False
                response = session.get(BASE+'/disclosure/companySearch.do', params={'searchText': name}, timeout=10)
                response.raise_for_status(); response.encoding = 'utf-8'
                company_id, legal_name, month = resolve_company(response.text, name)
                response = session.post(BASE+'/company/companyMajorFinanceProc.do', json={'cmpCd': company_id, 'kind': 'CFS' if basis == 'CFS' else 'FLS'}, timeout=10)
                response.raise_for_status()
                result = parse_finance(response.json(), code, name, basis, company_id, month, datetime.now(timezone.utc).isoformat())
                result['legal_name'] = legal_name
        except (requests.RequestException, ValueError, KeyError, TypeError):
            pass
        with self.lock:
            self.cache[key] = (time.monotonic(), result)
            self.cache.move_to_end(key)
            while len(self.cache) > 128:
                self.cache.popitem(last=False)
        return deepcopy(result)
