"""Dated disclosure/news metadata and local review state. No article bodies."""
import json
import re
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import requests
from .adapters import Reader, SetupPending
from .core import digest
from .local_config import load_local, require_profile

KST = ZoneInfo('Asia/Seoul')
IMPORTANT = ('정정', '실적', '배당', '자기주식', '유상증자', '감자', '합병', '영업정지',
             '횡령', '배임', '공급계약', '투자', '인수')
SAMSUNG_RSS = 'https://news.samsung.com/kr/feed'


def safe_url(value):
    if not isinstance(value, str) or len(value) > 4000:
        raise ValueError('출처 URL 형식 오류')
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or any(c.isspace() for c in value)):
        raise ValueError('공개 HTTPS 출처 필요')
    return value


def normalize(item, codes, now):
    if not isinstance(item, dict) or item.get('code') not in codes:
        raise ValueError('이벤트 종목 확인 필요')
    code = item['code']
    if not re.fullmatch(r'\d{6}', code) or item.get('kind') not in ('news', 'disclosure'):
        raise ValueError('이벤트 종류/코드 오류')
    published = date.fromisoformat(item['published_on'])
    if published > now.astimezone(KST).date():
        raise ValueError('미래 발표 자료')
    title, source = item['title'], item['source']
    if any(not isinstance(v, str) or not v.strip() or len(v) > cap
           for v, cap in [(title, 1000), (source, 200)]):
        raise ValueError('제목/출처 오류')
    url = safe_url(item['url'])
    published_at = item.get('published_at')
    if published_at:
        stamp = datetime.fromisoformat(published_at)
        if stamp.tzinfo is None or stamp > now or stamp.astimezone(KST).date() != published:
            raise ValueError('발표 시각/날짜 오류')
        published_at = stamp.astimezone(KST).isoformat()
    # Do not accept imported review flags or derived buy/sell opinions.
    return dict(id=digest(dict(code=code, kind=item['kind'], url=url)), code=code,
        kind=item['kind'], title=title.strip(), source=source.strip(), url=url,
        published_on=published.isoformat(), published_at=published_at,
        needs_review=item['kind']=='disclosure' or any(k in title for k in IMPORTANT),
        correction='정정' in title, mapping_basis=(item.get('mapping_basis')
            if item.get('mapping_basis') in ('DART stock_code', 'issuer_newsroom_feed') else 'supplied_code'))


def dart_items(rows, code):
    result = []
    for row in rows:
        if row.get('stock_code') != code:
            continue
        receipt = row['rcept_no']
        if not re.fullmatch(r'\d{14}', receipt):
            raise ValueError('DART 접수번호 오류')
        day = datetime.strptime(row['rcept_dt'], '%Y%m%d').date().isoformat()
        result.append(dict(code=code, kind='disclosure', title=row['report_nm'], source='OpenDART',
            published_on=day, published_at=None,
            url='https://dart.fss.or.kr/dsaf001/main.do?rcpNo='+receipt,
            mapping_basis='DART stock_code'))
    return result


def samsung_items(payload):
    if len(payload) > 2*1024*1024 or b'<!DOCTYPE' in payload.upper() or b'<!ENTITY' in payload.upper():
        raise ValueError('RSS 크기/형식 제한')
    root = ElementTree.fromstring(payload)
    if root.tag != 'rss' or root.find('channel') is None:
        raise ValueError('RSS 응답 필요')
    result = []
    for item in root.findall('./channel/item')[:100]:
        stamp = parsedate_to_datetime(item.findtext('pubDate'))
        if stamp.tzinfo is None:
            raise ValueError('뉴스 발표 시간대 필요')
        url = safe_url(item.findtext('link'))
        if urlsplit(url).hostname != 'news.samsung.com':
            raise ValueError('뉴스룸 출처 범위 불일치')
        result.append(dict(code='005930', kind='news', title=item.findtext('title'),
            source='삼성전자 공식 뉴스룸', published_on=stamp.astimezone(KST).date().isoformat(),
            published_at=stamp.isoformat(), url=url, mapping_basis='issuer_newsroom_feed'))
    return result


def fetch_samsung():
    with requests.get(SAMSUNG_RSS, timeout=(5, 15), allow_redirects=False, stream=True) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError('RSS 응답 상태 오류')
        parts, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > 2*1024*1024:
                raise ValueError('RSS 크기 제한')
            parts.append(chunk)
    return samsung_items(b''.join(parts))


class EventStore:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS market_event_versions(
                version TEXT PRIMARY KEY,event_id TEXT,code TEXT,seen TEXT,payload TEXT,reviewed INTEGER)''')

    def ingest(self, items, codes, now=None):
        now = now or datetime.now(KST)
        if now.tzinfo is None:
            raise ValueError('수집 시각 시간대 필요')
        now = now.astimezone(KST)
        if not isinstance(items, list) or len(items) > 5000:
            raise ValueError('이벤트 배열/건수 제한')
        normalized = [normalize(item, codes, now) for item in items]
        added = 0
        with self.store.connect() as db:
            for item in normalized:
                added += db.execute('INSERT OR IGNORE INTO market_event_versions VALUES(?,?,?,?,?,0)',
                    (digest(item), item['id'], item['code'], now.isoformat(),
                     json.dumps(item, ensure_ascii=False))).rowcount
        return added

    def list(self, code, as_of=None):
        as_of = as_of or datetime.now(KST).date().isoformat()
        date.fromisoformat(as_of)
        with self.store.connect() as db:
            rows = db.execute('SELECT version,seen,payload,reviewed FROM market_event_versions '
                              'WHERE code=? ORDER BY seen DESC,rowid DESC', (code,)).fetchall()
        result, seen = [], set()
        for version, observed, payload, reviewed in rows:
            item = json.loads(payload)
            if (observed[:10] > as_of or item['published_on'] > as_of or item['id'] in seen):
                continue
            seen.add(item['id'])
            result.append(dict(item, version=version, first_seen_at=observed, reviewed=bool(reviewed)))
        return sorted(result, key=lambda e:(e['published_on'], e.get('published_at') or ''), reverse=True)

    def mark_reviewed(self, version, reviewed=True):
        with self.store.connect() as db:
            db.execute('UPDATE market_event_versions SET reviewed=? WHERE version=?', (int(reviewed),version))

    def pending(self, codes, as_of=None):
        return {code:[{k:e[k] for k in ('id','title','url','published_on')}
                     for e in self.list(code,as_of) if e['needs_review'] and not e['reviewed']][:100]
                for code in codes}


def refresh_events(root, store, codes, providers=None, now=None):
    now = now or datetime.now(KST)
    if now.tzinfo is None:
        raise ValueError('수집 시각 시간대 필요')
    now = now.astimezone(KST)
    events = EventStore(store)
    if providers is None:
        local = load_local(root)
        require_profile(local)
        config = local.get('market_events') or {}
        providers = {}
        if '005930' in codes:
            providers['samsung_news'] = fetch_samsung
        def dart(code):
            if 'dart' not in local['enabled_data_adapters']:
                raise SetupPending('DART 연결 설정 대기')
            runtime = Path(root)/'config/runtime.local.json'
            if not runtime.is_file():
                raise SetupPending('DART 연결 설정 대기')
            settings = json.loads(runtime.read_text(encoding='utf-8-sig'))
            require_profile(local, settings['profile'])
            corp = config.get('dart_corp_codes', {}).get(code)
            if not isinstance(corp, str) or not re.fullmatch(r'\d{8}', corp):
                raise SetupPending('DART 법인 고유번호 설정 대기')
            rows = Reader(local['profile'],settings['permissions']).dart('disclosures',dict(
                corp_code=corp,bgn_de=(now-timedelta(days=30)).strftime('%Y%m%d'),
                end_de=now.strftime('%Y%m%d'),last_reprt_at='N'))
            return dart_items(rows,code)
        for code in codes:
            providers['dart:'+code] = lambda code=code: dart(code)
    receipt = dict(checked_at=now.isoformat(), sources={}, added=0,
                   coverage='설정된 DART 공시 및 삼성전자 뉴스룸 최신 RSS; 전체 언론·전체 종목 포괄 아님')
    for name, fetch in providers.items():
        try:
            items = fetch()
            added = events.ingest(items, codes, now)
            receipt['added'] += added
            receipt['sources'][name] = dict(status='complete',received=len(items),added=added)
        except Exception as error:
            receipt['sources'][name] = dict(status='setup_pending' if isinstance(error,SetupPending) else 'failed',
                                             error=type(error).__name__)
    statuses = [s['status'] for s in receipt['sources'].values()]
    receipt['status'] = 'complete' if statuses and all(s=='complete' for s in statuses) else 'partial' if 'complete' in statuses else 'unavailable'
    store.save_setting('market_events_refresh',receipt)
    return receipt


def import_events(payload, events, codes, now=None):
    if (not isinstance(payload, dict) or payload.get('schema_version') != 'market-events-0.1'
            or payload.get('data_mode') != 'user_input'):
        raise ValueError('실제 이벤트 입력 계약 필요')
    return events.ingest(payload['items'], codes, now)
