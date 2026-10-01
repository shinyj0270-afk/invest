"""Explicit collection of public financial statements; keys stay in the environment.

Run with --output in the local private_data/infomax directory. No DB/config writes.
The API option cross-checks official XBRL totals and preserves public viewer originals.
"""
import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from investment.dart_statements import parse_viewer, valid_report, amount

COMPANIES = {'005930': ('00126380', '삼성전자'),
             '000660': ('00164779', 'SK하이닉스'), '005380': ('00164742', '현대차')}
REPORTS = {1: '11013', 2: '11012', 3: '11014', 4: '11011'}


def api_check(session, key, corp, year, quarter, basis, record):
    try:
        response = session.get('https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json',
            params=dict(crtfc_key=key, corp_code=corp, bsns_year=year,
                        reprt_code=REPORTS[quarter], fs_div=basis), timeout=(5, 30))
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        # Request exceptions can contain the URL, including the key. Never echo them.
        raise ValueError('OpenDART API 통신 실패') from None
    if data.get('status') != '000':
        status = str(data.get('status', 'unknown'))
        raise ValueError('OpenDART API 상태 ' + (status if re.fullmatch(r'\d{3}', status) else 'unknown'))
    identities = {'assets': ('ifrs-full_Assets', 'ifrs_Assets'),
                  'liabilities': ('ifrs-full_Liabilities', 'ifrs_Liabilities'),
                  'equity': ('ifrs-full_Equity', 'ifrs_Equity')}
    checked = []
    for dest, ids in identities.items():
        matches = [r for r in data.get('list', []) if r.get('account_id') in ids and r.get('sj_div') == 'BS']
        if len(matches) != 1: raise ValueError('OpenDART API 대차 계정 미확인: ' + dest)
        r = matches[0]
        if r.get('rcept_no') != record['receipt'] or r.get('corp_code') != corp:
            raise ValueError('OpenDART API 원문 식별 불일치')
        value = amount(r.get('thstrm_amount', ''))
        if value is None or abs(value-record['values'][dest]) > 1e6:
            raise ValueError('OpenDART API 원문 금액 불일치: ' + dest)
        checked.append(dest)
    record['api_checked'] = checked


def collect(session, code, basis, year, quarter, cache, source, key=None):
    corp, name = COMPANIES[code]
    prefix = f'{code}-{basis}-{year}q{quarter}'
    saved = cache / (prefix + '.html'); metadata = cache / (prefix + '.json')
    if saved.is_file() and metadata.is_file():
        info = json.loads(metadata.read_text(encoding='utf-8'))
        payload = saved.read_bytes()
        if hashlib.sha256(payload).hexdigest() != info.get('sha256'):
            raise ValueError('저장 원문 해시 불일치')
        receipt, url = info['receipt'], info['url']
    else:
        try:
            response = session.post('https://opendart.fss.or.kr/disclosureinfo/fnltt/singl/list.do',
                data=dict(textCrpCik=corp, textCrpNm=name, selectYear=str(year),
                          reportCode=REPORTS[quarter], selectToc='0' if basis=='CFS' else '5'), timeout=(5,30))
            response.raise_for_status()
            iframe = re.search(r'<iframe[^>]+src="([^"]+)', response.content.decode('utf-8'))
            if not iframe: raise ValueError('공개 재무제표 조회 결과 없음')
            url = html.unescape(iframe.group(1))
            if not url.startswith('https://dart.fss.or.kr/'): raise ValueError('공개 원문 출처 불일치')
            receipt = re.search(r'rcpNo=(\d{14})', url).group(1)
            response = session.get(url, timeout=(5,30)); response.raise_for_status()
            payload = response.content
        except requests.RequestException:
            raise ValueError('DART 공개 조회 통신 실패') from None
        if len(payload)>4*1024*1024: raise ValueError('원문 크기 초과')
    record = parse_viewer(payload.decode('utf-8'), code=code, name=name, market='KOSPI',
        basis=basis, year=year, quarter=quarter, receipt=receipt, url=url)
    record['sha256'] = hashlib.sha256(payload).hexdigest()
    if not valid_report(record): raise ValueError('재무제표 검증 실패')
    if source=='api': api_check(session, key, corp, year, quarter, basis, record)
    saved.write_bytes(payload)
    metadata.write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8')
    return record


def main():
    parser = argparse.ArgumentParser(description='DART 실제 연결/별도 재무제표 수집')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--start-year', type=int, default=2023)
    parser.add_argument('--end-year', type=int, default=date.today().year)
    parser.add_argument('--through-quarter', type=int, choices=range(1,5), default=2)
    parser.add_argument('--source', choices=('public','api'), default='public')
    parser.add_argument('--codes', nargs='+', choices=tuple(COMPANIES), default=list(COMPANIES))
    args = parser.parse_args()
    if not 2015<=args.start_year<=args.end_year<=date.today().year:
        parser.error('연도는 2015부터 올해까지 오름차순이어야 합니다.')
    key = os.environ.get('OPENDART_API_KEY')
    if args.source=='api' and (not key or not re.fullmatch(r'[0-9a-fA-F]{40}',key)):
        parser.error('로컬 OPENDART_API_KEY에 40자리 인증키를 설정하세요.')
    cache = args.output.parent/'company-statements-sources'; cache.mkdir(parents=True,exist_ok=True)
    session = requests.Session(); session.headers['User-Agent']='INVESTMENT financial review'
    records=[]; errors=[]
    for code in args.codes:
        for basis in ('CFS','OFS'):
            for year in range(args.start_year,args.end_year+1):
                for quarter in range(1,(args.through_quarter if year==args.end_year else 4)+1):
                    try:
                        records.append(collect(session,code,basis,year,quarter,cache,args.source,key))
                        print('OK',code,basis,year,quarter,flush=True)
                    except (ValueError,KeyError,AttributeError,OSError):
                        errors.append(dict(code=code,basis=basis,year=year,quarter=quarter,error='조회·검증 실패'))
                        print('미확보',code,basis,year,quarter,flush=True)
                    time.sleep(.3)
    bundle=dict(schema='dart-public-statements-1',unit='KRW',retrieved_on=date.today().isoformat(),
                companies={c:dict(reports=[r for r in records if r['code']==c]) for c in args.codes},errors=errors)
    # Failed reruns never replace a complete previous bundle.
    if errors or not records:
        attempt=args.output.with_suffix('.incomplete.json')
        attempt.write_text(json.dumps(bundle,ensure_ascii=False,indent=2),encoding='utf-8')
        print('불완전 결과를 따로 저장했습니다. 기존 연결 파일은 보존합니다.')
        return 1
    temporary=args.output.with_suffix('.tmp')
    temporary.write_text(json.dumps(bundle,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(args.output)
    print('완료:',len(records),'개 재무제표; 인증키는 저장하지 않습니다.')
    return 0


if __name__=='__main__': sys.exit(main())
