"""Connect reviewed 2024-25 cash flow, dividend, and a 2025 ROIC proxy."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from investment.core import num, validate_snapshot
from tools.infomax_import import require, write_new

NOTE = ('현금흐름·보통주 배당은 공식 2025 연결보고서의 2024·2025 값. '
        'ROIC는 인포맥스 기말 자본·검토 차입금·현금과 보고서 실효세율을 쓴 참고 계산. '
        '과거 공개 시점·연도별 차입금 세부범위 미검증으로 연구 판정에는 미사용.')


def load_review(review_path, sources_path, pdf_dir):
    """Check saved report identity and transcribed values on the cited PDF pages."""
    from pypdf import PdfReader
    payload = Path(review_path).read_bytes()
    review = json.loads(payload.decode('utf-8-sig'))
    sources = json.loads(Path(sources_path).read_text(encoding='utf-8-sig'))
    annual = {s['code']: s for s in sources if s['kind'] == 'annual'}
    require(set(review['companies']) == set(annual), '공식 연간보고서 종목 집합 불일치')
    result = copy.deepcopy(review)
    for code, item in result['companies'].items():
        source = annual[code]
        pdf = Path(pdf_dir) / source['file']
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
        require(digest == item['pdf_sha256'] == source['sha256'], '공식 PDF 해시 불일치: ' + code)
        reader = PdfReader(pdf)
        pages = item['pages']
        require(all(isinstance(n, int) and 1 <= n <= len(reader.pages)
                    for group in pages.values() for n in group), '공식 PDF 쪽 범위 오류')
        def page_text(kind):
            text = '\n'.join(reader.pages[n-1].extract_text() or '' for n in pages[kind])
            return re.sub(r'\s*,\s*', ',', text)
        for year in ('2024', '2025'):
            for value in item['balances'][year].values():
                require(f'{value:,}' in page_text('balance'), code + ': 재무상태표 대조값 미발견')
            for value in item['cashflow'][year].values():
                require(f'{abs(value):,}' in page_text('cashflow'), code + ': 현금흐름표 대조값 미발견')
            for value in item['dividend'][year]['common_dps_components_won']:
                require(f'{value:,}' in page_text('dividend'), code + ': 배당 주석 대조값 미발견')
        for key in ('pretax_2025', 'tax_expense_2025'):
            require(f"{item[key]:,}" in page_text('income'), code + ': 세전이익·세금 대조값 미발견')
        item['source'] = {k: source[k] for k in ('url', 'file', 'sha256')}
    return result, hashlib.sha256(payload).hexdigest()


def build(base, review, balance_review, review_hash, balance_review_hash):
    validate_snapshot(base)
    require(base['meta']['data_mode'] == 'user_input', '실제 저장자료만 연결 가능')
    require(review['source_priority'] == 'infomax_balance_official_cashflow' and
            review['unit'] == 'million_krw_except_dps' and
            review['period_end'] == '2025-12-31' and
            review['observed_on'] == base['meta']['as_of'], '조회일·단위·자료 기준 불일치')
    require(set(review['companies']) == {r['code'] for r in base['companies']} ==
            set(balance_review['companies']), '종목 집합 불일치')
    result = copy.deepcopy(base)
    result['meta']['returns_history_observed_on'] = review['observed_on']
    if NOTE not in result['meta'].setdefault('warnings', []):
        result['meta']['warnings'].append(NOTE)
    for row in result['companies']:
        code = row['code']
        item = review['companies'][code]
        hist = row.get('observed_financial_history', {})
        require(hist.get('observed_on') == review['observed_on'] and
                bool(hist.get('annual')) and hist['annual'][-1]['period_end'] == review['period_end'],
                code + ': 장기 손익 기준 불일치')
        debt_fields = balance_review['companies'][code]['debt_fields']
        require(debt_fields and len(set(debt_fields)) == len(debt_fields), '차입금 구성 누락·중복')
        capital = {}
        debt_difference = {}
        for year in ('2024', '2025'):
            balance = row['financial_accounts']['balance'][year+'-12-31']
            require(all(num(balance.get(f)) and balance[f] >= 0
                        for f in (*debt_fields, '자본', '현금및현금성자산', '차입금',
                                  '단기차입금(요약재무)', '장기차입금(요약재무)')),
                    code + ': 재무상태표 필수값 결측')
            debt_difference[year] = (balance['차입금']-
                balance['단기차입금(요약재무)']-balance['장기차입금(요약재무)'])*1000
            official = item['balances'][year]
            require(abs(balance['자본']/1000-official['equity']) < 100 and
                    abs(balance['현금및현금성자산']/1000-official['cash']) < 100,
                    code + ': 공식 자본·현금 1억원 이상 차이')
            capital[year] = (balance['자본']+sum(balance[f] for f in debt_fields)-
                             balance['현금및현금성자산'])*1000
            require(capital[year] > 0, '투하자본 분모 오류')
        pretax, tax = item['pretax_2025'], item['tax_expense_2025']
        require(num(pretax) and num(tax) and pretax > 0 and 0 <= tax <= pretax,
                '공식 세율 계산 오류')
        tax_rate = tax/pretax
        op = hist['annual'][-1]['op']
        require(num(op), '2025 인포맥스 영업이익 결측')
        nopat = op*(1-tax_rate)
        debt_checked = all(abs(v) < 100_000_000 for v in debt_difference.values())
        roic = nopat/((capital['2024']+capital['2025'])/2)*100 if debt_checked else None
        roic_reason = None if debt_checked else '2024·2025 차입금과 단기+장기 차입금 대조 차이 1억원 이상'
        annual = []
        for year in ('2024', '2025'):
            cf = item['cashflow'][year]
            require(all(num(cf.get(k)) for k in ('ocf','capex_ppe','capex_intangible')) and
                    cf['capex_ppe'] >= 0 and cf['capex_intangible'] >= 0,
                    '현금흐름 값·취득액 오류')
            dps_parts = item['dividend'][year]['common_dps_components_won']
            require(dps_parts and all(num(v) and v >= 0 for v in dps_parts), '주당배당금 오류')
            annual.append(dict(period_end=year+'-12-31',
                ocf_won=cf['ocf']*1e6, capex_ppe_won=cf['capex_ppe']*1e6,
                capex_intangible_won=cf['capex_intangible']*1e6,
                fcf_won=(cf['ocf']-cf['capex_ppe']-cf['capex_intangible'])*1e6,
                common_dps_won=sum(dps_parts),
                year_end_status=item['dividend'][year]['year_end_status']))
        growth = annual[-1]['common_dps_won']/annual[0]['common_dps_won']-1 if annual[0]['common_dps_won'] > 0 else None
        row['observed_returns_history'] = dict(scope='current_observation',
            observed_on=review['observed_on'], historical_vintages_verified=False,
            annual=annual, common_dps_growth_1y_pct=growth*100 if growth is not None else None,
            roic_proxy_2025_pct=roic, roic_missing_reason=roic_reason,
            debt_split_difference_won=debt_difference, nopat_2025_won=nopat,
            effective_tax_rate_2025_pct=tax_rate*100,
            invested_capital_won=capital, debt_fields=debt_fields,
            source=item['source'], pdf_pages=item['pages'],
            review_sha256=review_hash, balance_review_sha256=balance_review_hash,
            note=NOTE + ' ' + item.get('note', ''))
        row['sources'] = [s for s in row.get('sources',[]) if s.get('kind') != 'observed_returns_history']
        row['sources'].append(dict(kind='observed_returns_history',
            label='공식 연결보고서 현금흐름·배당', **item['source']))
        if NOTE not in row.setdefault('data_quality', []): row['data_quality'].append(NOTE)
    return validate_snapshot(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('base','review','balance-review','sources','pdf-dir','output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    base = json.loads(args.base.read_text(encoding='utf-8-sig'))
    review, review_hash = load_review(args.review, args.sources, args.pdf_dir)
    balance_payload = args.balance_review.read_bytes()
    balance_review = json.loads(balance_payload.decode('utf-8-sig'))
    result = build(base, review, balance_review, review_hash,
                   hashlib.sha256(balance_payload).hexdigest())
    write_new(args.output, result)
    print(json.dumps({r['code']:dict(roic_proxy_pct=round(r['observed_returns_history']['roic_proxy_2025_pct'],2),
        fcf_2025_eok=round(r['observed_returns_history']['annual'][-1]['fcf_won']/1e8),
        dps_2025_won=r['observed_returns_history']['annual'][-1]['common_dps_won'])
        for r in result['companies']}, ensure_ascii=False))


if __name__ == '__main__': main()
