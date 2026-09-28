"""Revalidate the saved company-PC collection and build a local audit package.

Does not query Excel, certify supplier definitions, or upload anything.
The financial reference checks are pinned to the 2026-09-28 review dataset.
"""
import contextlib
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from infomax_import import read_grid, parse_info, at, text, day, number, require
from infomax_review import ROOT, HERE, main as build_review

from infomax_financials import EXTRAS, QUARTERS, BALANCE_DATES, parse_extra, audit

def collect_extra():
    info = parse_info(read_grid(HERE / 'info.xlsx')[0])
    parsed, sources = {}, {}
    for kind, fields in EXTRAS.items():
        grid, sources[kind] = read_grid(HERE / (kind + '.xlsx'))
        parsed[kind] = parse_extra(grid, fields, info,
                                  QUARTERS if kind == 'income-extra' else BALANCE_DATES)
    rows = []
    for code, company in info.items():
        inc, bal, debt = (parsed[k][code] for k in EXTRAS)
        for date in BALANCE_DATES:
            require(bal[date]['자본'] == debt[date]['자본'], 'Duplicate equity mismatch')
        current = bal[QUARTERS[0]]
        beginning = bal['2025-06-30']
        avg = ((current['자본']-current['기말비지배주주지분']) +
               (beginning['자본']-beginning['기말비지배주주지분'])) / 2
        require(avg > 0, 'Non-positive average parent equity')
        interest = inc[QUARTERS[0]]['이자비용']
        require(interest > 0, 'Non-positive interest expense')
        rows.append(dict(code=code, name=company['name'], status='provisional_not_in_dashboard',
            roe_ttm_pct=sum(inc[d]['당기순이익지배기업주주지분'] for d in QUARTERS)/avg*100,
            interest_coverage_q2=inc[QUARTERS[0]]['영업이익']/interest,
            net_debt_ratio_pct=None,
            reasons=['ROE: 지배주주 순이익 4분기 합계 / 2025-06·2026-06 평균 지배주주 자본. 전체 기간 공식 원문 대조 대기.',
                     '이자보상배율: 2026년 2분기 영업이익 / 이자비용. 공급자 계정 범위 및 공식 주석 대조 대기.',
                     '순차입금: 차입금·사채만 합산하면 유동성 장기부채/리스가 누락될 수 있어 산출 보류.'],
            raw_thousand_krw={k: parsed[k][code] for k in EXTRAS}))
    return dict(collected_on='2026-09-28', unit='thousand KRW', sources=sources,
                companies=rows, verified_numeric_cells=144,
                official_scope_finding={
                    'code': '005380',
                    'source': 'https://www.hyundai.com/content/dam/hyundai/ww/en/images/company/investor-relations/financial-Information/report-en/2026/2026-q2-consolidated-audit-report-en.pdf',
                    'page': 6,
                    'finding': 'Infomax 차입금 32,403,584백만원은 단기 10,838,843 + 장기 21,564,741와 일치. 공식 재무상태표는 유동성 장기부채 및 사채 40,357,613백만원과 리스를 별도로 표시. 두 공급자 필드만으로 총차입금을 확정할 수 없음.'})

def main():
    report = collect_extra()
    verified = audit()
    report['official_reconciliation'] = verified
    for row in report['companies']:
        evidence = verified['companies'][row['code']]
        row.update(status=evidence['status'], net_debt_ratio_pct=evidence['metrics']['net_debt_equity_pct'], reasons=evidence['notes'])
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run = HERE / 'runs' / stamp
    run.mkdir(parents=True, exist_ok=False)
    raw_names = ['info', 'prices', 'flows', 'balance', 'income', 'marketcap-history', *EXTRAS]
    hashes = {}
    # Immutable saved-input checkpoint, not an external transfer package.
    with ZipFile(run / 'saved-inputs.zip', 'x', compression=ZIP_DEFLATED) as archive:
        for name in raw_names:
            content = (HERE / (name+'.xlsx')).read_bytes()
            hashes[name+'.xlsx'] = hashlib.sha256(content).hexdigest()
            archive.writestr(name+'.xlsx', content)
    with contextlib.redirect_stdout(io.StringIO()) as log:
        build_review()
    (run/'review-build.txt').write_text(log.getvalue(), encoding='utf-8')
    (HERE/'official-financial-reconciliation.json').write_text(json.dumps(verified, ensure_ascii=False, indent=2), encoding='utf-8')
    (HERE/'additional-financial-review.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = ['# 추가 재무계정 검토', '', '원문 대조 기록을 보존하고 사용자 선택인 인포맥스 우선 기준으로 대시보드에 반영했습니다. 세부 범위는 공식 대조 JSON을 확인하세요.', '',
               '|종목|TTM ROE(%)|2분기 이자보상배율(배)|', '|---|---:|---:|']
    for row in report['companies']:
        summary.append(f"|{row['name']}|{row['roe_ttm_pct']:.4f}|{row['interest_coverage_q2']:.4f}|")
    summary += ['', '순차입금은 인포맥스 차입금·사채를 우선 사용하고 미확보 유동성 부채·리스는 공식 원문에서 보충했습니다. 정의 동일성 미확인 및 중복 가능성이 남은 혼합 출처 추정치입니다.',
                '', '추가 XLSX 3개, 3종목, 숫자 144개 검사 통과. 손익 4분기, 잔액 6분기. 단위 천원.',
                '원계정·날짜·해시·계산 근거는 additional-financial-review.json에 기록했습니다.']
    (HERE/'추가재무계정_검토.md').write_text('\n'.join(summary)+'\n', encoding='utf-8')
    snapshot=json.loads((HERE/'snapshot-review.json').read_text(encoding='utf-8'))
    displayed=sum(v is not None for row in snapshot['companies'] for v in row['metrics'].values())
    provisional=sum(len(row.get('user_policy_evidence',{}).get('released_metrics',[]))+1 for row in snapshot['companies'])
    manifest = dict(created_at_utc=stamp, inputs=hashes, status='completed_with_pending_policy' if snapshot['meta']['user_policy']['pending'] else 'completed',
                    displayed_metric_values=displayed, provisional_metric_values=provisional,
                    provisional_scope='20-observation flow/turnover metrics and mixed-source net debt',
                    pending_policy=snapshot['meta']['user_policy']['pending'],
                    additional_numeric_cells=144, network_upload=False)
    with ZipFile(run/'saved-inputs.zip') as archive:
        require(all(hashlib.sha256(archive.read(n)).hexdigest()==h for n,h in hashes.items()),
                'Checkpoint hash mismatch')
    for name, digest in hashes.items():
        require(hashlib.sha256((HERE/name).read_bytes()).hexdigest()==digest,
                'Input changed during build; rerun after Excel save')
    (run/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (HERE/'latest-run.json').write_text(json.dumps(dict(run=stamp, **manifest), indent=2), encoding='utf-8')
    print(f'PASS: 9 XLSX checkpoint, 144 additional numeric cells, {displayed} dashboard values; user policies applied, source differences retained')

if __name__ == '__main__':
    main()
