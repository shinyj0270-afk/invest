"""Company-calculated offline result artifacts, never a raw DB/holdings sync."""
import gzip
import base64
import hashlib
import html
import io
import json
import os
import re
import subprocess
import tempfile
import zlib
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCHEMA = 'investment-dashboard-result-1'
REPOSITORY = 'shinyj0270-afk/invest-results-private'
MAX_HTML = 180 * 1024 * 1024
MAX_GZIP = 100 * 1024 * 1024
MAX_RESULT_EXPANDED = 512 * 1024 * 1024 - 1024
BLOCKED = {'holdings', 'account_number', 'password', 'api_key', 'appkey', 'secretkey',
           'access_token', 'refresh_token', 'authorization', 'cookies', 'channel_registry',
           'telegram', 'investment_notes', 'user_policy_evidence'}


def encode_result_payload(payload):
    """Keep the complete offline result within transport limits without dropping data."""
    from .workspace_export import share_live_text
    payload=deepcopy(payload)
    share_live_text(payload,marker='$t',minimum_bytes=40)
    if 'wire_text' in payload:payload['wire_format']='result-text-v1'
    raw=json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')
    if len(raw)>MAX_RESULT_EXPANDED:raise ValueError(f'회사 결과 복원 크기 제한 초과 ({len(raw)} bytes)')
    compressed=gzip.compress(raw,mtime=0)
    if len(compressed)>MAX_GZIP:raise ValueError('회사 결과 압축 크기 제한 초과')
    return dict(wire_format='result-gzip-v1',wire_bytes=len(raw),
                wire_gzip=base64.b64encode(compressed).decode('ascii'))


def restore_result_payload(wire):
    """Bound decompression before parsing, including malformed length declarations."""
    size=wire.get('wire_bytes');encoded=wire.get('wire_gzip')
    if type(size) is not int or not 0<size<=MAX_RESULT_EXPANDED or not isinstance(encoded,str) or len(encoded)>MAX_GZIP*4//3+4:
        raise ValueError('회사 결과 복원 크기 확인 필요')
    try:
        compressed=base64.b64decode(encoded,validate=True)
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:raw=stream.read(size+1)
        if len(raw)!=size:raise ValueError('회사 결과 복원 길이 불일치')
        result=json.loads(raw)
    except (OSError,EOFError,ValueError,zlib.error) as exc:
        raise ValueError('회사 결과 압축·복원 길이 확인 필요') from exc
    if not isinstance(result,dict):raise ValueError('회사 결과 본문 확인 필요')
    if result.get('wire_format')=='result-text-v1':
        texts=result.pop('wire_text',None);marker='$t'
        if not isinstance(texts,list) or not all(isinstance(value,str) for value in texts):raise ValueError('회사 결과 출처 설명 확인 필요')
        public_data(texts)
        def restore(value):
            if isinstance(value,dict):
                if set(value)=={marker}:
                    index=value[marker]
                    if type(index) is not int or not 0<=index<len(texts):raise ValueError('회사 결과 출처 참조 확인 필요')
                    return texts[index]
                for key,item in value.items():value[key]=restore(item)
            elif isinstance(value,list):
                for index,item in enumerate(value):value[index]=restore(item)
            return value
        restore(result);result.pop('wire_format',None)
    return result


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def public_data(value):
    if isinstance(value, dict):
        if any(str(k).lower() in BLOCKED for k in value):
            raise ValueError('개인 입력·인증·Telegram 자료는 결과 공유에서 제외해야 합니다.')
        for item in value.values():
            public_data(item)
    elif isinstance(value, list):
        for item in value:
            public_data(item)
    elif isinstance(value, str):
        if re.search(r'(?i)((?<![A-Z0-9])[A-Z]:[\\/]|\\\\[^\\]+\\|sk-proj-|github_pat_|ghp_[A-Za-z0-9]|BEGIN [A-Z ]*PRIVATE KEY)', value):
            raise ValueError('로컬 경로·인증정보가 있어 결과를 공유하지 않았습니다.')
        if re.search(r'https?://(?:[^/]+\.)?(?:t\.me|telegram\.(?:me|org|dog))/', value, re.I):
            raise ValueError('Telegram 자료는 결과 공유에서 제외해야 합니다.')


def public_snapshot(snapshot):
    """Explicit financial/market input subset; no research notes or file metadata."""
    meta_keys = ('data_mode', 'price_date', 'flow_start', 'flow_end', 'financial_period',
                 'financial_basis', 'venue', 'universe_label', 'universe_total', 'calendar_basis')
    row_keys = ('code', 'name', 'market', 'industry', 'security_type', 'analysis_profile',
                'metrics', 'annual', 'quarters', 'prices', 'flows', 'financial_accounts',
                'metric_missing_reasons', 'price_venue', 'valuation_basis', 'analysis_venue')
    result = dict(schema_version=snapshot['schema_version'],
                  meta={k:deepcopy(snapshot['meta'][k]) for k in meta_keys if k in snapshot['meta']},
                  companies=[{**{k:deepcopy(r[k]) for k in row_keys if k in r},
                              'history':[], 'evidence':[], 'stages':[], 'sources':[]}
                             for r in snapshot['companies']],
                  sessions=deepcopy(snapshot.get('sessions', [])),
                  benchmarks=deepcopy(snapshot.get('benchmarks', {})))
    public_data(result)
    return result


def payload_from_html(content):
    value = json.JSONDecoder().raw_decode(content.split('const WORKSPACE_DATA=', 1)[1])[0]
    if value.get('wire_format')=='result-gzip-v1':value=restore_result_payload(value)
    live = json.JSONDecoder().raw_decode(content.split('const INVESTMENT_LIVE=', 1)[1])[0]
    if live is not None or value.get('detail_html'):
        raise ValueError('개인 보유 프레임·실시간 연결 없는 결과만 공유할 수 있습니다.')
    public_data(value)
    return value


def pack(content, *, source_build, generated_at=None):
    raw = content.encode('utf-8')
    if len(raw) > MAX_HTML:
        raise ValueError('결과 크기 제한 초과')
    payload = payload_from_html(content)
    meta = (payload.get('discovery') or {}).get('snapshot', {}).get('meta') or payload['analysis_snapshot']['meta']
    manifest = dict(schema=SCHEMA, source_profile='work', generated_at=generated_at or now(),
                    market_as_of=meta['price_date'], data_mode=meta['data_mode'],
                    source_build=source_build, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    compressed = gzip.compress(raw, mtime=0)
    if len(compressed) > MAX_GZIP:
        raise ValueError('압축 결과 크기 제한 초과')
    return manifest, compressed


def unpack(manifest, compressed):
    if (manifest.get('schema') != SCHEMA or manifest.get('source_profile') != 'work'
            or manifest.get('data_mode') not in ('user_input', 'live')
            or not re.fullmatch('[a-f0-9]{64}', str(manifest.get('sha256')))
            or type(manifest.get('bytes')) is not int or not 0 < manifest['bytes'] <= MAX_HTML
            or len(compressed) > MAX_GZIP):
        raise ValueError('회사 실제 결과 형식·크기를 확인하세요.')
    generated = datetime.fromisoformat(manifest['generated_at'])
    if generated.tzinfo is None or generated > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError('결과 생성 시각 확인 필요')
    market_day=datetime.strptime(manifest['market_as_of'], '%Y-%m-%d').date()
    if market_day > generated.astimezone(timezone(timedelta(hours=9))).date():
        raise ValueError('결과 자료 기준일 확인 필요')
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
        raw = stream.read(MAX_HTML + 1)
    if len(raw) != manifest['bytes'] or hashlib.sha256(raw).hexdigest() != manifest['sha256']:
        raise ValueError('결과 해시·길이 불일치 · 이전 정상 결과를 유지합니다.')
    content = raw.decode('utf-8')
    payload=payload_from_html(content)
    meta=(payload.get('discovery') or {}).get('snapshot',{}).get('meta') or payload['analysis_snapshot']['meta']
    if (meta.get('data_mode'),meta.get('price_date')) != (manifest['data_mode'],manifest['market_as_of']):
        raise ValueError('결과 본문과 생성 기록의 자료 모드·기준일 불일치')
    return content


def cache_root(root):
    return Path(root) / '.local' / 'shared-dashboard'


def cached(root):
    base = cache_root(root)
    pointer = json.loads((base / 'current.json').read_text(encoding='utf-8'))
    key = pointer['sha256']
    if not re.fullmatch('[a-f0-9]{64}', str(key)):
        raise ValueError('저장 결과 식별 확인 필요')
    folder = base / key
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['sha256'] != key:
        raise ValueError('저장 결과 식별 불일치')
    unpack(manifest, (folder / 'dashboard.html.gz').read_bytes())
    return manifest, folder


def install(root, manifest, compressed):
    content = unpack(manifest, compressed)
    try:
        old, _ = cached(root)
    except (OSError, ValueError, KeyError, TypeError):
        old = None
    if old and datetime.fromisoformat(old['generated_at']) > datetime.fromisoformat(manifest['generated_at']):
        raise ValueError('원격 결과가 이전 버전입니다. 최신 정상 결과를 유지합니다.')
    if old and old['sha256'] == manifest['sha256'] and (cache_root(root)/old['sha256']/'viewer.html').is_file():
        return cached(root)[1] / 'viewer.html'
    base = cache_root(root)
    base.mkdir(parents=True, exist_ok=True)
    target = base / manifest['sha256']
    received = now()
    banner = ('<aside id="companyResultStatus" role="status" style="padding:14px;background:#fff3cd;color:#302900">'
              '회사에서 계산한 저장 결과 · 자료 기준 ' + html.escape(manifest['market_as_of']) +
              ' · 생성 ' + html.escape(manifest['generated_at']) + ' · 이 PC 수신 ' + html.escape(received) +
              '<br>조회 전용 · 회사 PC가 꺼져 있어도 이 결과를 봅니다. 수신 실패 시 이전 정상 결과를 유지합니다.'
              ' 보유 입력·로컬 연구·새 수집은 이 결과에 포함하지 않습니다.</aside>'
              '<style>[data-page="holdings"],[data-page="portfolio"],[data-page="waterfall"],'
              '[data-page="recommendations"],[data-page="data"],[data-page="research-library"]{display:none!important}</style>')
    viewer = re.sub(r'(<body\b[^>]*>)', lambda match:match[0] + banner, content, count=1)
    # Immutable generations plus one atomic pointer: interrupted downloads never replace good data.
    with tempfile.TemporaryDirectory(dir=base, prefix='receive-') as temp:
        stage = Path(temp)
        (stage/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
        (stage/'dashboard.html.gz').write_bytes(compressed)
        (stage/'viewer.html').write_text(viewer, encoding='utf-8')
        (stage/'received.json').write_text(json.dumps(dict(received_at=received)), encoding='utf-8')
        if not target.exists():
            os.replace(stage, target)
        else:
            for name in ('manifest.json','dashboard.html.gz','viewer.html','received.json'):
                os.replace(stage/name,target/name)
        temp_pointer = base/'current.pending.json'
        temp_pointer.write_text(json.dumps(dict(sha256=manifest['sha256'])), encoding='utf-8')
        os.replace(temp_pointer, base/'current.json')
    return target/'viewer.html'


class ResultRepository:
    def __init__(self, repository=REPOSITORY, run=subprocess.run):
        if repository != REPOSITORY:
            raise ValueError('결과 전용 저장소만 사용할 수 있습니다.')
        self.repository = repository
        self.run = run

    def command(self, *args, json_result=False):
        result = self.run(['gh', *args], capture_output=True, text=True, encoding='utf-8', timeout=90)
        if result.returncode:
            raise ValueError('결과 저장소 연결 대기 · 로그인·접근 권한을 확인하세요.')
        return json.loads(result.stdout) if json_result else result.stdout

    def verify_private(self, write=False):
        value = self.command('api', 'repos/' + self.repository, json_result=True)
        if (value.get('private') is not True or value.get('full_name', '').lower() != self.repository.lower()
                or write and value.get('permissions', {}).get('push') is not True):
            raise ValueError('결과 전용 비공개 저장소·권한 확인 실패 · 전송하지 않습니다.')

    def receive(self, root):
        self.verify_private()
        release = self.command('release', 'view', '--repo', self.repository,
                               '--json', 'tagName,isDraft,isPrerelease', json_result=True)
        tag = release['tagName']
        if release['isDraft'] or release['isPrerelease'] or not re.fullmatch(r'results-[0-9TZ-]+-[a-f0-9]{12}', tag):
            raise ValueError('검증된 결과 릴리스 확인 필요')
        base = cache_root(root)
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base, prefix='download-') as temp:
            self.command('release', 'download', tag, '--repo', self.repository,
                         '--pattern', 'manifest.json', '--pattern', 'dashboard.html.gz', '--dir', temp)
            folder = Path(temp)
            if (folder/'manifest.json').stat().st_size > 8192 or (folder/'dashboard.html.gz').stat().st_size > MAX_GZIP:
                raise ValueError('원격 결과 크기 제한 초과')
            return install(root, json.loads((folder/'manifest.json').read_text(encoding='utf-8')),
                           (folder/'dashboard.html.gz').read_bytes())

    def publish(self, manifest, compressed):
        unpack(manifest, compressed)
        self.verify_private(write=True)
        tag = 'results-' + datetime.fromisoformat(manifest['generated_at']).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + manifest['sha256'][:12]
        with tempfile.TemporaryDirectory(prefix='investment-results-') as temp:
            folder = Path(temp)
            (folder/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
            (folder/'dashboard.html.gz').write_bytes(compressed)
            # Draft assets first. Only a complete release becomes latest; no clobber/force.
            self.command('release', 'create', tag, '--repo', self.repository, '--draft',
                         '--title', 'Dashboard results ' + manifest['market_as_of'],
                         '--notes', 'Company-generated offline results; no raw DB, credentials or holdings.',
                         str(folder/'manifest.json'), str(folder/'dashboard.html.gz'))
            self.command('release', 'edit', tag, '--repo', self.repository, '--draft=false', '--latest')
        return tag


def export_company(root):
    from .local_config import load_local, require_profile
    if require_profile(load_local(root)) != 'work':
        raise ValueError('결과 계산·발행은 work Primary에서만 합니다.')
    from .live_dashboard import saved_data
    from .market_discovery import read_market_cache
    from .company_financials import load_cached
    from .financial_table import load_local_financials, merge_financials
    from .workspace_export import export_workspace
    from .dashboard_build import source_fingerprint
    from .live_dashboard import dashboard_input_version
    before_build=source_fingerprint(root)
    before_data=dashboard_input_version(root)
    snapshot = saved_data(root)['snapshot']
    if not snapshot:
        raise ValueError('회사 실제 저장자료 대기')
    snapshot = public_snapshot(snapshot)
    cache = read_market_cache(root, snapshot)
    rows = {r['code']:r for r in (cache or {}).get('universe', {}).get('companies', []) if r.get('eligibility') == 'candidate'}
    rows.update({r['code']:r for r in snapshot['companies']})
    finances = merge_financials(load_local_financials(root, snapshot),
                                load_cached(root, snapshot, list(rows.values())),
                                as_of=datetime.now().date().isoformat())
    content = export_workspace(snapshot, market_cache=cache, financials=finances, result_view=True)
    if before_build!=source_fingerprint(root) or before_data!=dashboard_input_version(root):
        raise ValueError('결과 생성 중 코드·자료가 바뀌었습니다. 이전 결과를 유지하고 수집 완료 후 다시 발행하세요.')
    return pack(content, source_build=before_build)


def open_home(root, *, repository=None, browser=None):
    from .local_config import load_local, require_profile
    if require_profile(load_local(root)) != 'home':
        raise ValueError('결과 조회 실행기는 home에서만 사용합니다.')
    repository = repository or ResultRepository()
    status = 'received'
    try:
        path = repository.receive(root)
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        try:
            _, folder = cached(root)
            path = folder/'viewer.html'
            status = 'cached'
        except (OSError, ValueError, KeyError, TypeError):
            raise ValueError('회사 첫 결과 발행 대기 · home에서 수집·재계산하지 않았습니다.') from None
    if browser is not None:
        browser(path.resolve().as_uri())
    return path, status
