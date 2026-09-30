"""Dated valuation evidence for the current dashboard, without changing source snapshots.

No share-count inference or net-income/total-equity shortcuts are used. A ratio
needs an explicit positive-denominator declaration, or compatible EPS TTM/BPS.
"""
from copy import deepcopy
from datetime import date

from .core import num, observed_close

METRICS = ('per', 'pbr', 'eps_ttm', 'bps')
FIELDS = ('source', 'observed_on', 'price_date', 'financial_period',
          'financial_basis', 'adjustment_basis', 'period_type', 'venue')


def validate_observations(observations):
    if not isinstance(observations, list) or len(observations) > 100:
        raise ValueError('valuation_observations는 최대 100개 배열입니다')
    identities = set()
    for record in observations:
        if not isinstance(record, dict) or record.get('metric') not in METRICS:
            raise ValueError('평가 지표는 per/pbr/eps_ttm/bps입니다')
        if 'value' not in record or (record['value'] is not None and not num(record['value'])):
            raise ValueError('평가 관측값은 유한 숫자 또는 null입니다')
        if any(not isinstance(record.get(k), str) or not record[k].strip()
               or len(record[k]) > 1000 for k in FIELDS):
            raise ValueError('평가 출처·날짜·기간·기준·거래소를 명시하세요')
        for k in ('observed_on', 'price_date', 'financial_period'):
            try:
                if date.fromisoformat(record[k]).isoformat() != record[k]:
                    raise ValueError()
            except ValueError as exc:
                raise ValueError('평가 날짜는 유효한 YYYY-MM-DD입니다') from exc
        if record['financial_basis'] not in ('CFS', 'OFS'):
            raise ValueError('평가 연결/별도 기준을 확인하세요')
        if record['period_type'] not in ('TTM', 'point_in_time'):
            raise ValueError('평가 기간 종류를 확인하세요')
        if 'denominator_positive' in record and not isinstance(record['denominator_positive'], bool):
            raise ValueError('분모 양수 확인은 true/false입니다')
        identity = tuple(record[k] for k in ('metric',) + FIELDS)
        if identity in identities:
            raise ValueError('동일 출처·날짜·기준의 평가 관측 중복')
        identities.add(identity)
    return observations


def _result(record=None, *, value=None, status='unknown', reason='출처·기간·분모가 확인된 PER/PBR 자료 필요'):
    record = record or {}
    return dict(value=value, status=status, reason=reason, source=record.get('source'),
                basis=record.get('financial_basis'), period=record.get('financial_period'),
                period_type=record.get('period_type'), price_date=record.get('price_date'),
                observed_on=record.get('observed_on'), adjustment_basis=record.get('adjustment_basis'),
                venue=record.get('venue'))


def _check(record, row, snapshot, metric):
    meta = snapshot['meta']
    as_of = meta.get('as_of') or meta['price_date']
    if (record['observed_on'] > as_of or record['price_date'] > record['observed_on']
            or record['financial_period'] > record['observed_on']
            or record['financial_period'] > meta['price_date']):
        return '평가 시점 이후 자료 또는 미래 재무기간', None
    if record['price_date'] != meta['price_date']:
        return '가격 기준일 불일치', None
    if record['financial_basis'] != row.get('financial_basis', meta['financial_basis']):
        return '연결/별도 기준 불일치', None
    expected = 'TTM' if metric == 'per' else 'point_in_time'
    if record['period_type'] != expected:
        return 'PER은 TTM EPS, PBR은 해당 보고일 BPS 필요', None
    bar = observed_close(row, meta['price_date'])
    if bar is None or not bar['final'] or not bar['venue']:
        return '같은 기준일의 확정 가격·거래소 확인 필요', None
    if (record['venue'] != bar['venue'] or record['adjustment_basis'] != bar['adjustment_basis']
            or record['adjustment_basis'] in ('unverified', 'unknown')):
        return '가격의 거래소·수정주가 기준 불일치 또는 미확인', None
    return None, bar


def valuation_records(row, snapshot):
    """Return PER/PBR plus evidence and reasons; every missing result stays null."""
    records = validate_observations(row.get('valuation_observations', []))
    result = {}
    for metric, denominator in (('per', 'eps_ttm'), ('pbr', 'bps')):
        # Prefer Infomax, then the newest observation/report, then a supplied ratio.
        candidates = [r for r in records if r['metric'] in (metric, denominator)]
        candidates.sort(key=lambda r: (
            0 if ('infomax' in r['source'].lower() or '인포맥스' in r['source']) else 1,
            -date.fromisoformat(r['observed_on']).toordinal(),
            -date.fromisoformat(r['financial_period']).toordinal(), 0 if r['metric'] == metric else 1))
        result[metric] = _result()
        if not candidates:
            continue
        record = candidates[0]
        reason, bar = _check(record, row, snapshot, metric)
        if reason:
            result[metric] = _result(record, reason=reason)
            continue
        value = record['value']
        if not num(value):
            result[metric] = _result(record, reason='평가 관측값 결측')
            continue
        if value <= 0:
            reason = ('적자·EPS 0 이하: PER 평가 제외' if metric == 'per'
                      else '자본잠식·BPS 0 이하: PBR 평가 제외')
            result[metric] = _result(record, status='not_meaningful', reason=reason)
            continue
        if record['metric'] == metric:
            if record.get('denominator_positive') is not True:
                result[metric] = _result(record, reason='원천 PER/PBR의 분모 양수 여부 확인 필요')
                continue
            # An explicit contradictory denominator from the same source/date/basis
            # must never make a loss-making/negative-equity company look cheap.
            contradictory = any(r['metric'] == denominator and num(r['value']) and r['value'] <= 0
                and all(r[k] == record[k] for k in FIELDS) for r in records)
            if contradictory:
                result[metric] = _result(record, status='not_meaningful', reason='같은 출처의 EPS/BPS가 0 이하: 원천 비율과 모순')
                continue
            result[metric] = _result(record, value=value, status='observed', reason='출처 제공 비율 · 양의 분모 확인')
        else:
            ratio = bar['close'] / value
            if not num(ratio):
                result[metric] = _result(record, reason='계산 결과가 유한하지 않음')
                continue
            result[metric] = _result(record, value=ratio, status='derived',
                                     reason='동일 기준 확정 종가 ÷ ' + ('TTM EPS' if metric == 'per' else '보고일 BPS'))
            result[metric].update(price=bar['close'], denominator=value)
    return result


def enrich_valuation(snapshot):
    """Enrich a copy. Unsupported legacy ratios are excluded from cheap screens."""
    result = deepcopy(snapshot)
    for row in result['companies']:
        details = valuation_records(row, result)
        row['valuation_details'] = details
        for metric, record in details.items():
            row['metrics'][metric] = record['value']
            reasons = row.setdefault('metric_missing_reasons', {})
            if record['value'] is None:
                reasons[metric] = record['reason']
            else:
                reasons.pop(metric, None)
    return result
