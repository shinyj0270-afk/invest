"""Build the 2026-09-28 local review copy from the five saved exports.

Operating margin is released after a rounded official-earnings cross-check.
Additional ratios use official 2026 interim statements and the issuer IR table.
Unverified venue, finality, balance-publication and historical-vintage remain unset.
"""
import json
import hashlib
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'private_data' / 'infomax'
sys.path.insert(0, str(ROOT / 'tools'))
from infomax_import import FIELDS, read_grid, parse_info, parse_history, build_snapshot, at, text, day, number, require
from infomax_financials import audit as audit_financials
from infomax_user_policy import apply_observed_flow_policy

REFERENCES = {
    '005930': dict(date='2026-07-30', revenue=171.5e12, profit=89.5e12, tolerance=0.05e12,
                   url='https://news.samsung.com/global/samsung-electronics-announces-second-quarter-2026-results'),
    '000660': dict(date='2026-07-29', revenue=79.3187e12, profit=60.5426e12, tolerance=0.00005e12,
                   url='https://news.skhynix.com/en/q2-2026-business-results/'),
    '005380': dict(date='2026-07-23', revenue=49215e9, profit=2851e9, tolerance=0.5e9,
                   url='https://www.hyundai.com/content/hyundai/worldwide/en/newsroom/detail/0000001234.html'),
}

# Official statements: KRW millions, 2026-06-30 balances / Q2 three-month income.
# Retrieved 2026-09-28; not an assertion of the original publication date.
SAMSUNG = dict(assets=759480516, equity=579309676, liabilities=180170840,
               current_assets=379711982, current_liabilities=134189617,
               revenue=171499470, previous_revenue=74566317, profit=89492412)
BS_URL = 'https://images.samsung.com/is/content/samsung/assets/global/ir/docs/2026_con_quarter02_bs.pdf'
IS_URL = 'https://images.samsung.com/is/content/samsung/assets/global/ir/docs/2026_con_quarter02_soi.pdf'
HYUNDAI_URL = 'https://www.hyundai.com/content/dam/hyundai/ww/en/images/company/investor-relations/financial-Information/report-en/2026/2026-q2-consolidated-audit-report-en.pdf'
SK_URL = 'https://asia.tools.euroland.com/tools/ia/?companycode=kr-000660&v=redesign&lang=ko-kr'
STATEMENTS = {
    '005930': dict(values=SAMSUNG, bs_url=BS_URL, is_url=IS_URL, label='공식 반기 연결재무제표 · 재무상태표 p.3–5 / 손익 p.6'),
    '005380': dict(values=dict(assets=394512167, equity=135416445, liabilities=259095722,
                              current_assets=129045681, current_liabilities=97136454,
                              revenue=49215328, previous_revenue=48286677, profit=2850888),
                   bs_url=HYUNDAI_URL, is_url=HYUNDAI_URL, label='공식 반기 연결재무제표 · 인쇄 p.4–6 / PDF p.6–8'),
    '000660': dict(values=dict(assets=348862214, equity=262693227,
                              current_assets=156155954, current_liabilities=60257051,
                              revenue=79318746, previous_revenue=22231952, profit=60542607),
                   bs_url=SK_URL, is_url=SK_URL, label='SK하이닉스 공식 IR 내 Euroland 재무표 · 분기별 2026 2Q / 2025 2Q'),
}

AMOUNT_TOLERANCE_WON = 100_000_000

def amount_difference_accepted(difference_won):
    """User policy: absolute monetary differences strictly below KRW 100m."""
    return math.isfinite(difference_won) and abs(difference_won) < AMOUNT_TOLERANCE_WON

def parse_marketcap_history(grid, info, expected_dates):
    """Read the separately exported daily, close-setting market-cap history (KRW)."""
    require(text(at(grid, 0, 0)) == '시작', '시가총액 조건행 누락')
    require([text(at(grid, 0, c)) for c in (7, 9, 11, 13)] == ['일', 'D', '0', '종가'],
            '시가총액 일/내림차순/거래일/종가 설정 불일치')
    require(day(at(grid, 0, 3), '시가총액 종료일') == expected_dates[-1], '시가총액 종료일 불일치')
    names = {v['name']: k for k, v in info.items()}
    result = {}
    for col in range(0, len(grid[2]), 2):
        headers = [text(at(grid, 2, col + i)) for i in (0, 1)]
        if not any(headers):
            continue
        require(headers == ['일자', '시가총액'], '시가총액 헤더 불일치')
        name = text(at(grid, 1, col))
        require(name in names and names[name] not in result, '시가총액 종목 미등록/중복')
        observations = {}
        for row in range(3, len(grid)):
            cells = [at(grid, row, col + i) for i in (0, 1)]
            if not any(text(v) for v in cells):
                continue
            date = day(cells[0], '시가총액 날짜')
            value = number(cells[1], '시가총액 원')
            require(date not in observations, '시가총액 날짜 중복')
            require(value is not None and value > 0, '시가총액 양수 필요')
            observations[date] = value
        require(list(observations) == sorted(expected_dates, reverse=True), '시가총액 관측일/정렬 불일치')
        result[names[name]] = observations
    require(set(result) == set(info), '시가총액 종목 집합 불일치')
    return result

def main():
    user_policy = json.loads((ROOT / 'config/infomax.user-decisions.json').read_text(encoding='utf-8'))
    prefer_infomax = user_policy.get('financial_source_priority', {}).get('decision') == 'prefer_infomax_on_monetary_difference'
    financial_audit = audit_financials()
    grids, provenance = {}, {}
    for kind in ('info', *FIELDS):
        grids[kind], provenance[kind] = read_grid(HERE / (kind + '.xlsx'))
    info = parse_info(grids['info'])
    data = {k: parse_history(grids[k], k, info) for k in FIELDS}
    dates = sorted(data['prices']['005930'])
    for kind in ('prices', 'flows'):
        assert all(sorted(rows) == dates for rows in data[kind].values()), 'Date mismatch'
    assert dates[-1] == '2026-09-23' and len(dates) == 60
    cap_grid, cap_source = read_grid(HERE / 'marketcap-history.xlsx')
    caps = parse_marketcap_history(cap_grid, info, dates)
    provenance['marketcap_history'] = cap_source
    config = json.loads((ROOT / 'config/infomax.example.json').read_text(encoding='utf-8'))
    config.update(as_of='2026-09-28', completed_through=dates[-1], sessions_20d=dates[-20:],
                  financial_period='2026-06-30', market_cap_date='2026-09-28')
    # Observed dates are retained for the review copy, not certified as an official calendar.
    config['review_notes'] = ['20일 날짜는 여섯 가격/수급 블록의 공통 관측일. 공식 달력 미대조.',
                              '확정 여부와 거래소는 미확인. 사용자 결정에 따라 관측일 수급·거래대금 잠정 계산.']
    for company in config['companies'].values():
        company.update(security_type='ordinary', analysis_profile='nonfinancial')
    snapshot = build_snapshot(grids, config, provenance)
    snapshot['meta']['market_cap_date'] = dates[-1]
    snapshot['meta']['market_cap_basis'] = 'Infomax historical daily close-setting observation; venue and revision finality unconfirmed'
    checks = []
    for row in snapshot['companies']:
        code = row['code']
        ref = REFERENCES[code]
        inc = data['income'][code]['2026-06-30']
        revenue, profit = inc['매출액(영업수익)'] * 1000, inc['영업이익'] * 1000
        if not prefer_infomax:
            assert abs(revenue - ref['revenue']) <= ref['tolerance'], (code, 'revenue mismatch')
            assert abs(profit - ref['profit']) <= ref['tolerance'], (code, 'profit mismatch')
        for b in data['balance'][code].values():
            assert abs(b['자산']-b['자본']-b['부채']) <= max(1, b['자산']*1e-8)
        row['metrics']['operating_margin_pct'] = profit / revenue * 100
        row['metrics']['market_cap_eok'] = caps[code][dates[-1]] / 1e8
        row['metric_missing_reasons'].pop('market_cap_eok', None)
        row['market_cap_evidence'] = dict(source=cap_source, date=dates[-1], unit='KRW',
            value_won=caps[code][dates[-1]], observations=len(caps[code]),
            query='IMDH/STK; daily; Quote=종가; real=false', venue=None,
            status='historical_observation', revision_finality_confirmed=False)
        row['metric_missing_reasons'].pop('operating_margin_pct')
        row['metric_missing_reasons']['debt_ratio_pct'] = '잔액 대차 검사는 통과. 해당 잔액의 공개일·공시 원문 대조는 미완료.'
        row['sources'] = [{'label': f"2026년 2분기 공식 실적 발표 ({ref['date']})", 'url': ref['url']}]
        if code in STATEMENTS:
            statement = STATEMENTS[code]
            values = statement['values']
            b = data['balance'][code]['2026-06-30']
            differences = {key: b[field] / 1000 - values[key]
                           for field, key in [('자산', 'assets'), ('자본', 'equity'), ('부채', 'liabilities')]
                           if key in values}
            differences.update(revenue=revenue/1e6-values['revenue'], profit=profit/1e6-values['profit'])
            if 'liabilities' not in values:
                differences['liabilities_derived_assets_minus_equity'] = b['부채']/1000 - (values['assets']-values['equity'])
            if not prefer_infomax and not all(amount_difference_accepted(v * 1_000_000) for v in differences.values()):
                raise ValueError(f'{code}: official statement difference is at least KRW 100m: {differences}')
            row['metrics'].update(
                current_ratio_pct=values['current_assets']/values['current_liabilities']*100,
                revenue_growth_pct=((revenue/1e6 if prefer_infomax else values['revenue'])/values['previous_revenue']-1)*100)
            row['metrics']['debt_ratio_pct'] = b['부채']/b['자본']*100
            for key in ('debt_ratio_pct', 'current_ratio_pct', 'revenue_growth_pct'):
                if row['metrics'][key] is not None:
                    row['metric_missing_reasons'].pop(key, None)
            row['sources'].append({'label': statement['label'], 'url': statement['bs_url']})
            if statement['is_url'] != statement['bs_url']:
                row['sources'].append({'label': '공식 손익계산서 · 3개월 비교열 사용', 'url': statement['is_url']})
            row['statement_evidence'] = dict(values_million_krw=values, retrieved_on='2026-09-28',
                original_publication_date=None, balance_source=statement['bs_url'],
                income_source=statement['is_url'], infomax_minus_official_million_krw=differences,
                amount_tolerance_won=AMOUNT_TOLERANCE_WON, tolerance_comparison='absolute_difference < threshold',
                debt_ratio_basis='Infomax liabilities / equity; missing official liabilities checked as assets minus equity',
                balance_match=('exact' if not any(differences.values()) else
                    'within_user_tolerance' if all(amount_difference_accepted(v*1e6) for v in differences.values()) else 'differs_infomax_selected'),
                selected_source_priority='infomax' if prefer_infomax else 'official_reconciled')
        extra = financial_audit['companies'][code]
        row['metrics'].update(extra['metrics'])
        for key in extra['metrics']:
            row['metric_missing_reasons'].pop(key, None)
        row['additional_financial_evidence'] = extra
        apply_observed_flow_policy(row, data, dates[-20:], user_policy['decisions'])
        row['sources'].extend([
            {'label': '추가 재무 원문 · 반기 연결보고서', 'url': extra['source']},
            {'label': 'TTM 대조 · 2025년 연간 연결보고서', 'url': extra['annual_source']}])
        row['data_quality'] = sorted(set(row['metric_missing_reasons'].values())) + [
            '영업이익률은 인포맥스 연결 단독분기 매출·영업이익으로 계산. 원문 차이는 대조 기록에 보존하며 금액 차이 시 인포맥스 우선.',
            '시가총액은 별도 재조회한 9/23 일별 종가 설정 관측값(원→억원). 9/28 장중 기본정보 값은 사용하지 않음. 거래소 범위·최종 정정 여부는 미확인.',
            '현재 조회 자료 검토용. 과거 시점 데이터 및 정정 이력이 검증된 백테스트 자료가 아님.',
        ]
        row['data_quality'].append('유동자산·유동부채·전년 동분기 매출은 공식 자료에서 보충. 최초 공개일 미확정으로 과거 시점 검증에는 사용하지 않음.')
        row['data_quality'].extend(extra['notes'])
        if 'user_policy_evidence' in row:
            row['data_quality'].extend(row['user_policy_evidence']['labels'])
            row['data_quality'].append(f"20일 지표는 최근 20개 공통 관측일 ({dates[-20]}~{dates[-1]}) 잠정값. 공식 거래일 미대조.")
        row['data_quality'].append(extra['scope'])
        if code == '005380':
            row['data_quality'].append('현대차 연결재무에는 금융부문이 포함됨. 자동차부문 단독 수치와 구분해야 함.')
            row['data_quality'].append('현대차 이자보상배율은 연결 영업이익 / 금융비용 주석의 이자비용. 금융부문 원가에 포함되는 조달비용까지 포괄한 총이자 지급능력 지표로 해석하지 않음.')
        if code == '000660':
            row['data_quality'].append('공식 IR 표 대비 자본·영업이익 각각 +100만 원, 자산−자본으로 대조한 부채 −100만 원. 사용자 기준인 절대 차이 1억 원 미만으로 허용. 영업이익률·부채비율은 인포맥스 값으로 계산.')
            row['data_quality'].append('추가로 확보한 SK하이닉스 공식 반기 연결검토보고서에서는 자본·영업이익이 인포맥스와 정확히 일치. 앞의 100만원 차이는 Euroland IR 표와의 비교 결과.')
        snapshot['meta']['import_audit'][code]['calculated_metrics'] = sum(v is not None for v in row['metrics'].values())
        checks.append(dict(code=code, publication_date=ref['date'], source=ref['url'],
                           operating_margin_pct=row['metrics']['operating_margin_pct'],
                           revenue_difference_won=revenue-ref['revenue'],
                           profit_difference_won=profit-ref['profit'],
                           rounding_tolerance_won=ref['tolerance'],
                           market_cap_evidence=row['market_cap_evidence'],
                           statement_evidence=row.get('statement_evidence'),
                           additional_financial_evidence=extra,
                           calculated_metrics={k:v for k,v in row['metrics'].items() if v is not None}))
    snapshot['meta']['universe_label'] = '인포맥스 3종목 · 사용자 기준 적용 · 수급 잠정값'
    snapshot['meta']['user_policy'] = user_policy
    snapshot['meta']['review_checks'] = checks
    snapshot['meta']['amount_tolerance_policy'] = dict(threshold_won=AMOUNT_TOLERANCE_WON,
        comparison='abs(difference_won) < threshold', scope='Precise financial statement monetary cross-checks',
        rounded_press_release_check='Separate source-precision tolerance retained')
    snapshot['meta']['warnings'] = [
        '저장된 Excel 파일 기반 정적 연결. 자동 갱신 없음.',
        '인포맥스 우선 기준 적용. 원문 차이는 보존하며 1억 원 미만을 경미한 차이로 분류. 20개 관측일 수급·거래대금은 사용자 승인 잠정값.',
        '거래소 범위·확정 여부·공식 거래일 달력 미확인. 관측 날짜만 기록.',
        '종목 분류: 조회한 보통주 코드와 공식 사업 설명 기준의 비금융 기업 분류.',
    ]
    baseline_path = HERE / 'collection_validation.json'
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
        sources = [baseline['info']['source']] + [x['source'] for x in baseline['files'].values()]
        hash_checks = []
        for source in sources:
            current = hashlib.sha256((HERE / source['file']).read_bytes()).hexdigest()
            hash_checks.append(dict(file=source['file'], baseline_sha256=source['sha256'],
                                    current_sha256=current, match=current == source['sha256']))
        snapshot['meta']['baseline_hash_checks'] = hash_checks
        changed = [x['file'] for x in hash_checks if not x['match']]
        if changed:
            message = '최초 수집 기록과 파일 해시 다름: ' + ', '.join(changed) + '. 변경 원인 미확인; 현재 읽은 파일 해시를 별도 기록.'
            snapshot['meta']['warnings'].append(message)
            for row in snapshot['companies']:
                row['data_quality'].append(message)
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2)
    (HERE / 'config-review.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    (HERE / 'snapshot-review.json').write_text(payload, encoding='utf-8')
    html = (ROOT / 'INVESTMENT_Dashboard.html').read_text(encoding='utf-8')
    html = html.replace('20거래일', '20개 관측일')
    html = html.replace('실제 관측값 미포함 · 전 시장 데이터 연결·자동 갱신 미구현',
                        '인포맥스 3종목 저장 자료 · 2026-09-28 검토본 · 자동 갱신 없음')
    html = html.replace('실제 종목 데이터는 브라우저 메모리에서만 처리하며 새로고침하면 제거됩니다.',
                        '이 회사 PC용 사본에는 검토 JSON이 포함되어 새로 열면 복원됩니다. 이후 불러온 자료는 메모리에만 유지됩니다.')
    safe = payload.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    bootstrap = '<script id="local-review-data" type="application/json">' + safe + '</script>'
    bootstrap += "<script>snapshot=validateSnapshot(JSON.parse(document.getElementById('local-review-data').textContent));renderAll();activate('company');</script>"
    html = html.replace('</body>', bootstrap + '</body>')
    (HERE / 'INVESTMENT_실데이터_검토.html').write_text(html, encoding='utf-8')
    (HERE / 'connection_checks.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(checks, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
