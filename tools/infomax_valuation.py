"""Attach reviewed Infomax valuation observations offline; never overwrite source files.

Input JSON: {"schema_version":"infomax-valuation-0.1", "companies":
{"000001": [{"metric":"eps_ttm", "value":1000, "source":"Infomax",
"observed_on":"2026-09-23", "price_date":"2026-09-23",
"financial_period":"2026-06-30", "financial_basis":"CFS",
"adjustment_basis":"unadjusted", "period_type":"TTM", "venue":"KRX"}]}}
The example is fictional. Direct per/pbr also needs denominator_positive: true;
BPS/PBR uses period_type: point_in_time. Units are KRW/share for EPS/BPS and
multiples for PER/PBR. Definitions must be reviewed against the source export.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from investment.core import validate_snapshot
from investment.valuation import FIELDS, enrich_valuation, validate_observations
from tools.infomax_import import require, write_new


def build(base, observations):
    result = deepcopy(validate_snapshot(base))
    require(observations.get('schema_version') == 'infomax-valuation-0.1', '평가 관측 계약 오류')
    companies = observations.get('companies')
    codes = {r['code'] for r in result['companies']}
    require(isinstance(companies, dict) and companies and set(companies) <= codes, '평가 종목 집합 오류')
    for row in result['companies']:
        if row['code'] not in companies:
            continue
        incoming = validate_observations(companies[row['code']])
        require(incoming, '평가 관측 누락')
        require(all('infomax' in r['source'].lower() or '인포맥스' in r['source'] for r in incoming),
                '이 입력 도구는 인포맥스 출처만 지원합니다')
        key = lambda r: tuple(r[k] for k in ('metric',) + FIELDS)
        merged = {key(r): r for r in row.get('valuation_observations', [])}
        merged.update({key(r): r for r in incoming})
        row['valuation_observations'] = list(merged.values())
    return validate_snapshot(enrich_valuation(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('base', 'observations', 'output'):
        parser.add_argument('--' + flag, required=True, type=Path)
    args = parser.parse_args()
    try:
        for path in (args.base, args.observations):
            require(path.stat().st_size <= 30 * 1024 * 1024, '입력 크기 초과')
        result = build(json.loads(args.base.read_text(encoding='utf-8-sig')),
                       json.loads(args.observations.read_text(encoding='utf-8-sig')))
        write_new(args.output, result)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f'평가 관측 연결 실패: {exc}\n')
    statuses = {}
    for row in result['companies']:
        for record in row['valuation_details'].values():
            statuses[record['status']] = statuses.get(record['status'], 0) + 1
    print(json.dumps(dict(companies=len(result['companies']), statuses=statuses), ensure_ascii=False))


if __name__ == '__main__':
    main()
