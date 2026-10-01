"""Map saved market observations into the existing manual holdings contract."""
import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .core import digest, observed_close, validate_snapshot, num
import re


def holdings_input(snapshot, as_of=None, events=None):
    validate_snapshot(snapshot)
    if snapshot['meta']['data_mode'] != 'user_input':
        raise ValueError('실제 저장자료 모드만 보유 입력에 연결할 수 있습니다')
    as_of = as_of or datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    date.fromisoformat(as_of)
    sid = digest(snapshot)
    rows = []
    for row in snapshot['companies']:
        bar = observed_close(row, snapshot['meta']['price_date'])
        # An observed price is not a verified thesis, valuation or disclosure.
        price_label = ('Infomax 저장 관측 종가 · 거래소 ' + (bar['venue'] or '미확인') +
                       (' · 확정' if bar['final'] else ' · 잠정') +
                       ' · 보정 ' + bar['adjustment_basis']) if bar else ''
        rows.append(dict(code=row['code'], issuer_id=row.get('issuer_id') or row['code'],
            name=row['name'], market=row['market'], security_type=row['security_type'],
            analysis_profile=row['analysis_profile'], sector=row.get('industry'), risk_group=None,
            price_krw=bar['close'] if bar else None, price_date=bar['date'] if bar else None,
            price_source=dict(kind='local_snapshot', label=price_label, snapshot_id=sid) if bar else None,
            review=dict(thesis='unknown', business='unknown', finance='unknown',
                valuation='unknown', material_risk='unknown', reviewed_on=None,
                financial_period=snapshot['meta']['financial_period'], positives=[], negatives=[],
                invalidation='', next_review_on=None), evidence=[]))
        if events is not None:
            rows[-1]['pending_events'] = events.get(row['code'], [])
    return dict(schema_version='holdings-portfolio-0.1', mode='user_input', as_of=as_of,
                snapshot_id=sid, cash_krw=None, holdings=[], research=rows,
                market_data_as_of=snapshot['meta']['price_date'])


def holdings_catalog(snapshot, cache, as_of=None):
    """Public identity/dated-price lookup, kept outside private holdings state.

    Candidate classification remains a candidate; public data is not a reviewed
    thesis. Only chosen companies are attached to the private input in the UI.
    """
    base = holdings_input(snapshot, as_of)
    rows = {r['code']: r for r in base['research']}
    if not cache:
        return list(rows.values())
    universe = cache.get('universe') or {}
    if universe.get('schema_version') != 'naver-universe-0.1':
        return list(rows.values())
    histories = (cache.get('history') or {}).get('histories') or {}
    for source in universe.get('companies', []):
        code = source.get('code', '')
        if not isinstance(code, str) or not re.fullmatch(r'\d{6}', code) or source.get('eligibility') != 'candidate':
            continue
        if code in rows:
            continue  # Preserve the existing Infomax identity and observation.
        if not isinstance(source.get('name'), str) or not source['name'].strip() or source.get('market') not in ('KOSPI', 'KOSDAQ'):
            continue
        record = histories.get(code) or {}
        prices = record.get('prices') or []
        bar = None
        if record.get('symbol') == code and record.get('kind') == 'item':
            candidates = [b for b in prices if isinstance(b, dict) and
                isinstance(b.get('date'), str) and b['date'] < base['as_of'] and
                num(b.get('close')) and b['close'] > 0 and b.get('final') is True and
                b.get('venue') == 'KRX' and b.get('adjustment_basis') == 'naver_chart_adjusted']
            if candidates:
                latest = max(b['date'] for b in candidates)
                same = [b for b in candidates if b['date'] == latest]
                if len(same) == 1:
                    try: date.fromisoformat(latest); bar = same[0]
                    except ValueError: pass
        rows[code] = dict(code=code, issuer_id=code, name=source['name'], market=source['market'],
            security_type=source.get('security_type') or 'unknown',
            analysis_profile=source.get('analysis_profile') or 'unknown',
            sector=source.get('industry') or None, risk_group=None,
            price_krw=bar['close'] if bar else None, price_date=bar['date'] if bar else None,
            price_source=dict(kind='public_chart', label='네이버 저장 완료 일봉 · KRX · 차트 보정가격',
                url='https://stock.naver.com/domestic/stock/'+code+'/price') if bar else None,
            review=dict(thesis='unknown',business='unknown',finance='unknown',valuation='unknown',
                material_risk='unknown',reviewed_on=None,financial_period='공개 목록 · 기간/연결 기준 미확인',
                positives=[],negatives=[],invalidation='',next_review_on=None),evidence=[])
    return list(rows.values())


def linked_dashboard(html, snapshot, as_of=None, events=None, initial_input=None, policy=None):
    values = dict(INVESTMENT_HOLDINGS_INPUT=holdings_input(snapshot, as_of, events))
    if initial_input is not None:
        values['INVESTMENT_INITIAL_HOLDINGS'] = initial_input
    if policy is not None:
        values['INVESTMENT_INITIAL_POLICY'] = policy
    payload = json.dumps(values, ensure_ascii=False, allow_nan=False)
    # The JSON is executable-script data; escape HTML delimiters and line separators.
    for char, escaped in [('<', '\\u003c'), ('>', '\\u003e'), ('&', '\\u0026'),
                          ('\u2028', '\\u2028'), ('\u2029', '\\u2029')]:
        payload = payload.replace(char, escaped)
    marker = '<script>'
    if marker not in html:
        raise ValueError('보유 화면 스크립트 시작점을 찾을 수 없습니다')
    return html.replace(marker, '<script>Object.assign(window,' + payload + ');</script>' + marker, 1)
