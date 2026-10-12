"""Offline long-horizon research records. No retrieval, model calls, or trading."""
from copy import deepcopy
from datetime import date, datetime, timezone, timedelta
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl
import ipaddress

from .core import digest, validate_snapshot
from .store import Store

STRATEGIES = ('value', 'growth', 'cycle', 'trend')
MASTERS = {
    'buffett': ('워런 버핏', 'value'), 'munger': ('찰리 멍거', 'value'),
    'marks': ('하워드 막스', 'cycle'), 'lynch': ('피터 린치', 'growth'),
    'druckenmiller': ('스탠리 드러켄밀러', 'cycle'),
    'mauboussin': ('마이클 모부신', 'value'),
    'minervini': ('마크 미너비니', 'trend'), 'oneil': ('윌리엄 오닐', 'trend'),
}


def text(value, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError('Nonempty bounded text required')
    return value.strip()


def day(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError('ISO day required')
    if value > datetime.now(timezone(timedelta(hours=9))).date().isoformat():
        raise ValueError('Future dates are not research observations')
    return value


def url(value):
    parts = urlsplit(text(value))
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
        raise ValueError('Public HTTPS reference required')
    if parts.fragment: raise ValueError('Canonical reference without fragment required')
    host = parts.hostname.lower()
    if host == 'localhost' or host.endswith(('.localhost', '.local')): raise ValueError('Public host required')
    try: ipaddress.ip_address(host)
    except ValueError: pass
    else: raise ValueError('Public named source host required')
    for name, _ in parse_qsl(parts.query):
        if re.search(r'(?i)(token|secret|password|auth|api.?key|session|signature|^key$|^sig$|^utm_)', name):
            raise ValueError('Sensitive/tracking query parameters forbidden')
    return value


def fields(record, required, optional=()):
    if not isinstance(record, dict) or set(record) - set(required) - set(optional) or set(required) - set(record):
        raise ValueError('Record fields do not match the allowlist')


def strings(values):
    if not isinstance(values, list) or not values or len(values) > 30:
        raise ValueError('Nonempty bounded list required')
    return [text(v) for v in values]


def record_day(timestamp):
    return datetime.fromisoformat(timestamp).astimezone(timezone(timedelta(hours=9))).date().isoformat()


def instruments(values):
    if not isinstance(values, list) or len(values) > 30: raise ValueError('Instrument list required')
    for item in values:
        fields(item, ('code', 'market', 'kind'))
        if not re.fullmatch(r'\d{6}', item['code']) or item['market'] not in ('KOSPI', 'KOSDAQ') or item['kind'] not in ('stock', 'etf'):
            raise ValueError('Domestic stock/listed ETF identity required')


class Library:
    """Separate local DB; reuse Store's transactional connection lifecycle.

    Real records require a configured work/home profile. Fixtures use a distinct DB.
    Immutable revisions and expected_revision prevent stale writes from overwriting.
    """
    connect = Store.connect

    def __init__(self, root, profile, mode='user_input'):
        if profile not in ('home', 'work') or mode not in ('user_input', 'fixture'):
            raise ValueError('Explicit PC profile and research mode required')
        self.profile, self.mode = profile, mode
        base = Path(root).resolve()
        self.path = base / profile / mode / 'research_library.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS records(kind TEXT, id TEXT, revision INTEGER, created TEXT, payload TEXT, PRIMARY KEY(kind,id,revision))')

    def _put(self, kind, key, value, expected_revision=0):
        text(key, 100)
        if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 0:
            raise ValueError('Expected revision required')
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT MAX(revision) FROM records WHERE kind=? AND id=?', (kind, key)).fetchone()[0] or 0
            if current != expected_revision:
                raise ValueError('Revision conflict; preserve both inputs and reread')
            db.execute('INSERT INTO records VALUES(?,?,?,?,?)', (kind, key, current+1, datetime.now(timezone.utc).isoformat(), payload))
        return current+1

    def history(self, kind, key):
        if kind in ('channel', 'coverage', 'telegram'):
            self._home()
        with self.connect() as db:
            return [dict(revision=r[0], recorded_at=r[1], value=json.loads(r[2])) for r in db.execute(
                'SELECT revision,created,payload FROM records WHERE kind=? AND id=? ORDER BY revision', (kind, key))]

    def get(self, kind, key):
        rows = self.history(kind, key)
        if not rows:
            raise ValueError('Referenced record not found: '+kind)
        value = rows[-1]['value']
        if kind == 'source' and value.get('origin') == 'telegram': self._telegram_allowed(value['channel_id'])
        if kind in ('source', 'master', 'thesis', 'evidence'):
            metadata = self.history('catalog', digest([kind, key]))
            if metadata and metadata[-1]['value']['stage'] == 'deleted':
                raise ValueError('Record logically deleted; history retained for explicit recovery')
        return value

    def _home(self):
        if self.profile != 'home':
            raise ValueError('Telegram records may only be processed on home')

    def _telegram_allowed(self, channel_id):
        from .telegram_research import permission
        self._home()
        registry = self.get('channel', 'registry')
        channel = next((c for c in registry['core']+registry['auxiliary'] if c['id'] == channel_id), None)
        if not channel or not channel['enabled']: raise ValueError('Telegram channel permission unavailable or revoked')
        return permission(channel['permission'])

    def source(self, key, value, expected_revision=0):
        if expected_revision != 0: raise ValueError('Sources are immutable; create a new source ID for corrections')
        fields(value, ('title', 'url', 'published_on', 'accessed_on', 'access', 'origin', 'locator'), ('channel_id',))
        value = deepcopy(value)
        value['title'] = text(value['title'], 300); value['locator'] = text(value['locator'], 200)
        value['url'] = url(value['url'])
        day(value['accessed_on'])
        if value['published_on'] is not None:
            day(value['published_on'])
            if value['published_on'] > value['accessed_on']: raise ValueError('Source not yet available')
        if value['access'] not in ('public', 'paid', 'private') or value['origin'] not in ('independent', 'telegram'):
            raise ValueError('Source access/origin required')
        host = urlsplit(value['url']).hostname.lower()
        telegram_host = any(host == suffix or host.endswith('.'+suffix) for suffix in ('t.me', 'telegram.me', 'telegram.dog'))
        if value['origin'] == 'telegram':
            permissions = self._telegram_allowed(text(value.get('channel_id'), 100))
            if permissions['terms_checked_on'] > value['accessed_on']: raise ValueError('Permission was not confirmed at access time')
        elif telegram_host or 'channel_id' in value:
            raise ValueError('Telegram source cannot be labelled independent')
        return self._put('source', key, value, expected_revision)

    def master(self, key, value, expected_revision=0):
        if expected_revision != 0: raise ValueError('Master cards are immutable; create a new card ID for corrections')
        fields(value, ('master', 'strategies', 'source_ids', 'principle', 'conditions', 'counterexamples', 'interpretation'))
        if value['master'] not in MASTERS or not set(strings(value['strategies'])) <= set(STRATEGIES):
            raise ValueError('Known master and strategies required')
        for sid in strings(value['source_ids']):
            source = self.get('source', sid)
            if source['origin'] == 'telegram': self._home()
        text(value['principle']); strings(value['conditions']); strings(value['counterexamples'])
        if value['interpretation'] != 'own_paraphrase': raise ValueError('Original paraphrase only; no source body')
        return self._put('master', key, value, expected_revision)

    def thesis(self, key, value, expected_revision=0):
        fields(value, ('title', 'sector', 'theme', 'claim', 'conditions', 'invalidation', 'as_of', 'status', 'change_reason', 'instruments', 'master_ids', 'seed_source_ids'))
        for k in ('title', 'sector', 'theme', 'claim', 'change_reason'): text(value[k])
        strings(value['conditions']); strings(value['invalidation']); day(value['as_of'])
        if value['status'] not in ('active', 'invalidated', 'retired'): raise ValueError('Explicit thesis lifecycle required')
        if not isinstance(value['master_ids'], list) or len(value['master_ids']) > 30: raise ValueError('Master IDs list required')
        for mid in value['master_ids']: self.get('master', mid)
        instruments(value['instruments'])
        if not isinstance(value['seed_source_ids'], list) or len(value['seed_source_ids']) > 30: raise ValueError('Seed sources list required')
        for sid in value['seed_source_ids']:
            text(sid, 100)
            src = self.get('source', sid)
            if src['accessed_on'] > value['as_of']: raise ValueError('Future source cannot seed a past thesis')
        old = self.history('thesis', key)
        if old and value['as_of'] < old[-1]['value']['as_of']: raise ValueError('Thesis dates must not move backward')
        if value['status'] == 'invalidated' and not any(e['stance'] == 'refute' and e['observed_on'] <= value['as_of'] for e in self.evidence_for(key)):
            raise ValueError('Invalidation requires recorded refutation; otherwise retire with reason')
        for mid in value['master_ids']:
            for sid in self.get('master', mid)['source_ids']:
                src = self.get('source', sid)
                if src['accessed_on'] > value['as_of']: raise ValueError('Future master research cannot support past thesis')
        return self._put('thesis', key, value, expected_revision)

    def evidence(self, key, value, expected_revision=0):
        if expected_revision != 0: raise ValueError('Evidence is immutable; create a new evidence ID for corrections')
        fields(value, ('thesis_id', 'thesis_revision', 'source_ids', 'stance', 'observation', 'reasoning', 'observed_on'))
        if value['stance'] not in ('support', 'refute', 'context'): raise ValueError('Evidence stance required')
        revisions = self.history('thesis', value['thesis_id'])
        revision = value['thesis_revision']
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1 or revision > len(revisions):
            raise ValueError('Existing thesis revision required')
        day(value['observed_on'])
        if value['observed_on'] < revisions[revision-1]['value']['as_of']: raise ValueError('Evidence predates thesis revision')
        for sid in strings(value['source_ids']):
            src = self.get('source', sid)
            if src['origin'] == 'telegram': self._home()
            if src['accessed_on'] > value['observed_on']: raise ValueError('Evidence was unavailable at observation time')
        text(value['observation']); text(value['reasoning'])
        return self._put('evidence', key, value, expected_revision)

    def evidence_for(self, key, revision=None):
        with self.connect() as db:
            ids = [r[0] for r in db.execute("SELECT DISTINCT id FROM records WHERE kind='evidence' ORDER BY id")]
        results = []
        for eid in ids:
            item = self.get('evidence', eid)
            if item['thesis_id'] == key and (revision is None or item['thesis_revision'] == revision):
                for sid in item['source_ids']:
                    if self.get('source', sid)['origin'] == 'telegram': self._home()
                results.append(dict(id=eid, recorded_at=self.history('evidence', eid)[-1]['recorded_at'], **item))
        return results

    def draft(self, key):
        """Deterministic independent writing outline; claims remain unverified drafts."""
        history = self.history('thesis', key); current = self.get('thesis', key)
        evidence = self.evidence_for(key, history[-1]['revision'])
        old_refutations = [e for e in self.evidence_for(key) if e['thesis_revision'] < history[-1]['revision'] and e['stance'] == 'refute']
        all_sources = {s for e in self.evidence_for(key) for s in e['source_ids']}
        for revision in history:
            all_sources.update(revision['value']['seed_source_ids'])
            for mid in revision['value']['master_ids']: all_sources.update(self.get('master', mid)['source_ids'])
        restricted = any(self.get('source', sid)['origin'] == 'telegram' or self.get('source', sid)['access'] != 'public' for sid in all_sources)
        parts = ['# '+current['title'], '독립 글쓰기 초안 · 검증/발행 전 · 투자 결론 미확정',
                 f"기준일 {current['as_of']} · revision {history[-1]['revision']} · 상태 {current['status']} · 변경사유: {current['change_reason']}",
                 f"기록일 {history[-1]['recorded_at']} · 기준일과 다른 소급 입력은 당시 예측의 증거가 아닙니다.",
                 '가설: '+current['claim'], '적용 조건: '+'; '.join(current['conditions']),
                 '반증 조건: '+'; '.join(current['invalidation'])]
        if restricted: parts.insert(1, '공유 제한: telegram/paid/private 출처 포함 · 외부 모델/회사 공유 금지')
        for stance, label in (('support', '지지 근거'), ('refute', '반박 근거'), ('context', '배경')):
            parts.append(label)
            selected = [e for e in evidence if e['stance'] == stance]
            parts.extend(e['observation']+' — '+e['reasoning']+f" (관측 {e['observed_on']}; 기록일 {e['recorded_at']}; {'소급 입력; ' if record_day(e['recorded_at']) > e['observed_on'] else ''}{', '.join(e['source_ids'])})" for e in selected)
            if not selected: parts.append('미확보 · 추가 확인 필요')
        source_ids = set(s for e in evidence for s in e['source_ids'])
        source_ids.update(current['seed_source_ids'])
        if old_refutations:
            parts.append('이전 revision 반박 근거 · 현재 가설 재평가 필요 (현재 근거로 자동 승격하지 않음)')
            for e in old_refutations:
                parts.append(f"r{e['thesis_revision']}: {e['observation']} — {e['reasoning']} (관측 {e['observed_on']}; 기록일 {e['recorded_at']}; {'소급 입력; ' if record_day(e['recorded_at']) > e['observed_on'] else ''}{', '.join(e['source_ids'])})")
                source_ids.update(e['source_ids'])
        for mid in current['master_ids']: source_ids.update(self.get('master', mid)['source_ids'])
        historical_sources = all_sources - source_ids
        parts.append('출처')
        for sid in sorted(source_ids):
            src = self.get('source', sid)
            if src['origin'] == 'telegram': self._home()
            parts.append(f"{sid}: {src['title']} ({src['published_on'] or '발행일 미확인'}, {src['locator']}): {src['url']}")
        if historical_sources:
            parts.append('이전 revision 출처 · 현재 가설의 근거로 자동 승격하지 않음')
            for sid in sorted(historical_sources):
                src = self.get('source', sid)
                parts.append(f"{sid}: {src['title']} ({src['published_on'] or '발행일 미확인'}, {src['locator']}): {src['url']}")
        return '\n\n'.join(parts)

    def propose(self, value):
        """Generate an unverified research question from distinct original observations."""
        fields(value, ('sector', 'theme', 'as_of', 'observations', 'conditions', 'invalidation', 'instruments', 'master_ids'))
        text(value['sector']); text(value['theme']); day(value['as_of'])
        strings(value['conditions']); strings(value['invalidation'])
        instruments(value['instruments'])
        if not isinstance(value['master_ids'], list) or len(value['master_ids']) > 30: raise ValueError('Master IDs list required')
        for mid in value['master_ids']:
            for sid in self.get('master', mid)['source_ids']:
                if self.get('source', sid)['accessed_on'] > value['as_of']: raise ValueError('Future master cannot seed past research')
        if not isinstance(value['observations'], list) or not 2 <= len(value['observations']) <= 30:
            raise ValueError('At least two bounded observations required')
        seen = set()
        for observation in value['observations']:
            fields(observation, ('source_id', 'observation', 'stance'))
            src = self.get('source', observation['source_id'])
            if src['origin'] == 'telegram': self._home()
            if src['accessed_on'] > value['as_of']: raise ValueError('Future source cannot seed a past hypothesis')
            text(observation['observation'])
            if observation['stance'] not in ('support', 'refute', 'context'): raise ValueError('Observation stance required')
            seen.add(src['url'])
        if len(seen) < 2: raise ValueError('Different sources required; independence still unverified')
        candidate = dict(title=value['sector']+' · '+value['theme'], sector=value['sector'], theme=value['theme'],
                         claim=value['sector']+'에서 '+value['theme']+'가 장기 투자성과를 설명할 수 있는지 검증한다.',
                         conditions=deepcopy(value['conditions']), invalidation=deepcopy(value['invalidation']),
                         as_of=value['as_of'], status='active', change_reason='연결 연구자료로 생성한 검증 전 가설 초안',
                         instruments=deepcopy(value['instruments']), master_ids=deepcopy(value['master_ids']),
                         seed_source_ids=sorted({o['source_id'] for o in value['observations']}))
        restricted = any(self.get('source', sid)['origin'] == 'telegram' or self.get('source', sid)['access'] != 'public' for sid in candidate['seed_source_ids'])
        return dict(status='unverified_candidate', thesis=candidate, observations=deepcopy(value['observations']),
                    restricted=restricted, sharing='공유 제한: 출처 제한 포함 · 회사/외부 모델 공유 금지' if restricted else 'local_draft_review_required',
                    note='인과·출처 독립성 미검증. 저장 전 가설을 구체화하고 각 revision의 evidence로 연결하세요.')

    def approved_result(self, key, review):
        """Explicit per-result review; no DB/channel/paid/private/Telegram data export.

        Permission assertions are recorded, not independently certified. Inspect the
        exact draft before approval. No automatic file writes or Git actions.
        """
        fields(review, ('reviewer', 'reviewed_on', 'content_digest', 'independent_analysis', 'no_personal_data', 'redistribution_allowed'))
        text(review['reviewer']); day(review['reviewed_on'])
        if any(review[k] is not True for k in ('independent_analysis', 'no_personal_data', 'redistribution_allowed')):
            raise ValueError('Explicit result review required')
        draft = self.draft(key)
        if digest(draft) != review['content_digest']: raise ValueError('Approval is stale or for different content')
        thesis = self.get('thesis', key)
        sources = {s for e in self.evidence_for(key) for s in e['source_ids']}
        # Provenance of earlier claims cannot disappear by removing a card on revision.
        for revision in self.history('thesis', key):
            sources.update(revision['value']['seed_source_ids'])
            for mid in revision['value']['master_ids']: sources.update(self.get('master', mid)['source_ids'])
        if not sources: raise ValueError('Referenced public research required for sharing')
        for sid in sources:
            src = self.get('source', sid)
            if src['origin'] != 'independent' or src['access'] != 'public': raise ValueError('Restricted derivation stays local')
        if review['reviewed_on'] < thesis['as_of']: raise ValueError('Review predates thesis')
        dates = [record_day(r['recorded_at']) for r in self.history('thesis', key)]
        for e in self.evidence_for(key): dates.extend([e['observed_on'], record_day(e['recorded_at'])])
        if review['reviewed_on'] < max(dates): raise ValueError('Review predates included research records')
        return dict(schema=1, mode=self.mode, status='reviewed_draft', draft=draft,
                    review={k:v for k,v in review.items() if k != 'reviewer'})


def analysis_context(thesis, snapshot, research=None, tables=None, monitor_entries=None):
    """Reference existing engines; ETF identity links never pretend stock metrics apply."""
    from .workspace_research import build_research
    from .trend_following import build_trend_following
    from .thesis_monitor import evaluate, validate_thesis
    validate_snapshot(snapshot)
    facts = research if research is not None else build_research(snapshot)
    trends = build_trend_following(snapshot, facts)
    rows = {r['code']: r for r in snapshot['companies']}
    trend_rows = {r['code']: r for r in trends['rows']}
    result = []
    for link in thesis['instruments']:
        code = link['code']; row = rows.get(code)
        item = dict(**link, status='pending', as_of=snapshot['meta']['price_date'], thesis_as_of=thesis['as_of'],
                    context='current_review_not_historical_replay', mode=snapshot['meta']['data_mode'])
        if row and row['market'] == link['market'] and ((row['security_type'] == 'etf') == (link['kind'] == 'etf')):
            item['identity_status'] = 'matched'
            item['research'] = deepcopy(facts.get('rows', {}).get(code))
            item['trend'] = deepcopy(trend_rows.get(code)) if link['kind'] == 'stock' else None
            item['status'] = 'linked' if item['research'] else 'pending'
            if link['kind'] == 'stock' and code in (monitor_entries or {}):
                entry = validate_thesis(monitor_entries[code])
                item['monitor'] = evaluate(entry, (tables or {}).get(code), (item['research'] or {}).get('technical'), item['trend'])
        item['note'] = 'ETF: 기존 종목 엔진의 재무/추세 적용 범위 밖; 분석 공급자 연결 대기' if link['kind'] == 'etf' else '기존 저장 분석 연결; 신규 투자 판단 아님'
        result.append(item)
    return result


def trend_comparison(context):
    """Map stored engine checks without claiming full proprietary strategy equivalence."""
    return dict(engine='investment.trend_following.build_trend_following',
                minervini=dict(scope='기존 가격 기반 8조건 변형 · 원 전략 동일성 미검증', observations=deepcopy(context)),
                oneil=dict(scope='부분 비교: 자체 RS/추세 관측만 재사용',
                           pending=['EPS', '연간 이익', '신제품/촉매', '수급', '기관', 'FTD/시장 방향']),
                attribution_status='source_card_required')
