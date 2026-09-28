"""Connect current observations of historical income; never invent publication dates."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from investment.core import continuous, num, validate_snapshot
from tools.infomax_import import day, require, write_new
from tools.infomax_financial_snapshot import INCOME, read_accounts

FIELDS = {'revenue':'매출액(영업수익)', 'op':'영업이익',
          'parent_income':'당기순이익지배기업주주지분'}
NOTE = '장기 실적은 현재 조회본: 단독분기 합산 연간 실적·CAGR·TTM. 최초 공개일·과거 정정 이력 미검증, 과거 시점 연구 판정에는 미사용.'


def build(base, accounts, observed_on, provenance, review):
    validate_snapshot(base)
    require(base['meta']['data_mode']=='user_input', '실제 저장자료만 연결 가능')
    observed_on = day(observed_on, '조회일')
    require(observed_on == base['meta']['as_of'], '스냅샷과 장기 재무 조회일 불일치')
    require(review['observed_on']==observed_on and review['source_priority']=='infomax', '조회일·인포맥스 우선 검토 필요')
    codes = {r['code'] for r in base['companies']}
    require(set(accounts)==codes==set(review['companies']), '종목 집합 불일치')
    result = copy.deepcopy(base)
    result['meta']['financial_history_source'] = provenance
    result['meta']['financial_history_observed_on'] = observed_on
    warnings = result['meta'].setdefault('warnings', [])
    if NOTE not in warnings: warnings.append(NOTE)
    for row in result['companies']:
        source = accounts[row['code']]
        dates = sorted(source)
        require(len(dates)>=24 and continuous([{'period_end':d} for d in dates], len(dates)), '연속 분기 24개 이상 필요')
        require(dates[-1]==base['meta']['financial_period'] and dates[-1]<=observed_on, '검토된 최신 재무기간과 불일치')
        quarters = []
        for end in dates:
            values = {k:source[end][v] for k,v in FIELDS.items()}
            require(all(num(v) for v in values.values()) and values['revenue']>0, '필수 손익 결측·매출 범위 오류')
            quarters.append(dict(period_end=end, basis='CFS', available_at=None,
                                 **{k:v*1000 for k,v in values.items()}))
        by_date = {q['period_end']:q for q in quarters}
        overlap = []
        for old in row.get('quarters', []):
            require(old['period_end'] in by_date, '기존 분기 누락')
            for field in FIELDS:
                require(num(old.get(field)), '기존 분기 원자료 결측')
                diff = by_date[old['period_end']][field]-old[field]
                require(abs(diff)<100_000_000, '기존 검토 분기와 1억원 이상 차이: 재검토 필요')
                overlap.append(dict(period_end=old['period_end'], field=field, difference_won=diff))
        annual = []
        excluded = []
        for year in sorted({d[:4] for d in dates}):
            part = [q for q in quarters if q['period_end'].startswith(year)]
            if len(part)!=4 or part[0]['period_end'][5:]!='03-31' or part[-1]['period_end'][5:]!='12-31':
                excluded.append(year)
                continue
            annual.append(dict(period_end=year+'-12-31', basis='CFS', available_at=None,
                               **{k:sum(q[k] for q in part) for k in FIELDS}))
        require(continuous(annual,6,annual=True), '완료된 연속 6개 연도 필요')
        checked = review['companies'][row['code']]
        require(checked['period_end']==annual[-1]['period_end'], '최신 완료 연도 공식 대조 필요')
        require(checked.get('source',{}).get('sha256') and checked.get('pdf_page'), '공식 출처와 대조 위치 필요')
        comparison = []
        for field in FIELDS:
            official = checked['official_million_krw'][field]
            require(num(official), '공식 대조 금액 결측')
            observed = annual[-1][field]
            diff = observed-official*1e6
            comparison.append(dict(field=field, observed_won=observed, official_won=official*1e6,
                                   difference_won=diff, within_tolerance=abs(diff)<100_000_000))
        row['observed_financial_history'] = dict(
            scope='current_observation', observed_on=observed_on, basis='CFS',
            income_basis='standalone_quarters', historical_vintages_verified=False,
            quarters=quarters, annual=annual, incomplete_years_excluded=excluded,
            source=provenance, annual_comparison=comparison,
            official_source=checked['source'], official_pdf_page=checked['pdf_page'],
            overlap_comparison=overlap, note=NOTE)
        row['sources'] = [s for s in row.get('sources',[]) if s.get('kind')!='observed_financial_history']
        row['sources'].append(dict(label='인포맥스 장기 손익 저장본', kind='observed_financial_history', **provenance))
        if NOTE not in row.setdefault('data_quality', []): row['data_quality'].append(NOTE)
    return validate_snapshot(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base','income','review','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    base = json.loads(args.base.read_text(encoding='utf-8-sig'))
    review_bytes = args.review.read_bytes()
    review = json.loads(review_bytes.decode('utf-8-sig'))
    accounts, provenance = read_accounts(args.income, INCOME,
        {r['code']:r['name'] for r in base['companies']}, base['meta']['as_of'], '순')
    provenance['review_sha256'] = hashlib.sha256(review_bytes).hexdigest()
    result = build(base, accounts, base['meta']['as_of'], provenance, review)
    write_new(args.output, result)
    print(json.dumps({r['code']:dict(quarters=len(r['observed_financial_history']['quarters']),
        annual=len(r['observed_financial_history']['annual'])) for r in result['companies']}, ensure_ascii=False))


if __name__=='__main__':
    main()
