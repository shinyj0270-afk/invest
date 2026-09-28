"""Pinned, source-backed reconciliation of additional 2026-Q2 financial accounts.

Official amounts below are KRW millions. XLSX amounts are KRW thousands.
TTM net income is independently reconstructed as FY2025 - H1 2025 + H1 2026.
No inference about provider-wide accounting definitions is made from a match.
"""
import math
import json
from pathlib import Path
from infomax_import import read_grid, parse_info, at, text, day, number, require

HERE = Path(__file__).resolve().parents[1] / 'private_data/infomax'
EXTRAS = {
    'income-extra': ['이자비용', '영업이익', '당기순이익지배기업주주지분'],
    'balance-extra': ['자본', '기말비지배주주지분', '현금및현금성자산'],
    'debt-extra': ['차입금', '사채', '자본'],
}
QUARTERS = ['2026-06-30', '2026-03-31', '2025-12-31', '2025-09-30']
BALANCE_DATES = QUARTERS + ['2025-06-30', '2025-03-31']
SAMSUNG_URL='https://images.samsung.com/is/content/samsung/assets/global/ir/docs/2026_con_quarter02_all.pdf'
HYUNDAI_URL='https://www.hyundai.com/content/dam/hyundai/ww/en/images/company/investor-relations/financial-Information/report-en/2026/2026-q2-consolidated-audit-report-en.pdf'
SK_URL='https://mis-prod-koce-homepage-cdn-01-blob-ep.azureedge.net/web/attach/136258867637359840.pdf'
REFERENCES = {
 '005930': dict(url=SAMSUNG_URL,
  annual_url='https://images.samsung.com/is/content/samsung/assets/global/ir/docs/2025_con_quarter04_all.pdf',
  pdf_pages=dict(balance=[5,6,7], income=[8], equity=[10,12], interest=[53], debt=[6,43,44]),
  annual_income_pdf_page=9,
  equity=579309676, nci=14244936, opening_equity=399561967, opening_nci=10867850,
  cash=92916382, parent_q2=71269468, parent_h1=118370658,
  parent_prior_h1=12962441, parent_fy=44260956, interest_q2=197003, interest_h1=474672,
  profit_q2=89492412,
  debt_components=dict(short_borrowing=13710121,current_long_term_liabilities=1205829,
                       noncurrent_bonds=7668,long_borrowing_including_leases=7485103),
  supplier_borrowing_components=dict(short_borrowing=13710121,long_bank_borrowing=3605834),
  supplier_bond_reference=7668,
  scope='리스는 유동성 장기부채와 장기차입금에 이미 포함. 다시 더하지 않음.'),
 '000660': dict(url=SK_URL,
  annual_url='https://mis-prod-koce-homepage-cdn-01-blob-ep.azureedge.net/web/attach/17049944244349186.pdf',
  pdf_pages=dict(balance=[6,7],income=[8],equity=[9],interest=[57],debt=[6,7,40,42]),
  annual_income_pdf_page=11,
  equity=262693228,nci=312618,opening_equity=87142485,opening_nci=15325,
  cash=26835986,parent_q2=93820236,parent_h1=134150412,
  parent_prior_h1=15104309,parent_fy=42919287,interest_q2=154334,interest_h1=321277,
  profit_q2=60542608,
  debt_components=dict(short_borrowing=2664419,current_long_borrowing=1945289,
                       current_bonds=1249165,long_borrowing=2183825,noncurrent_bonds=10543936,
                       current_leases=526461,noncurrent_leases=2000044),
  supplier_borrowing_components=dict(short_borrowing=2664419,long_borrowing=2183825),
  supplier_bond_reference=10543936,
  scope='차입금 주석 합계에 유동/비유동 리스부채를 별도로 더함. 공급자 차입금+사채에는 유동성 차입금·사채 및 리스 누락.'),
 '005380': dict(url=HYUNDAI_URL,
  annual_url='https://www.hyundai.com/content/dam/hyundai/ww/en/images/company/investor-relations/financial-Information/report-en/2025/2025-q4-consolidated-audit-report-en.pdf',
  pdf_pages=dict(balance=[6,7],income=[8],equity=[10,11],interest=[52],debt=[7,28,39]),
  annual_income_pdf_page=10,
  equity=135416445,nci=13088448,opening_equity=121537114,opening_nci=11259924,
  cash=20256150,parent_q2=2520851,parent_h1=4856197,
  parent_prior_h1=6155597,parent_fy=9445987,interest_q2=179575,interest_h1=337568,
  profit_q2=2850888,
  debt_components=dict(short_borrowing=10838843,current_long_debt_and_bonds=40357613,
                       long_borrowing=21564741,noncurrent_bonds=116043983,
                       current_leases=393808,noncurrent_leases=1219774),
  supplier_borrowing_components=dict(short_borrowing=10838843,long_borrowing=21564741),
  supplier_bond_reference=116043983,
  scope='금융부문 포함 연결 기준. 공급자 사채와 공식 비유동 사채는 333,195백만원 차이: 동일 정의로 취급하지 않음. 순차입금은 공식 잔액으로 재구성.'),
}

def parse_extra(grid, fields, info, dates):
    require(text(at(grid,0,7))=='분기' and text(at(grid,0,9))=='D','Extra: period/order mismatch')
    require(day(at(grid,0,3),'end')=='2026-09-23','Pinned review end mismatch')
    names={v['name']:k for k,v in info.items()}; result={}
    for c in range(0,len(grid[2]),4):
        headers=[text(at(grid,2,c+i)) for i in range(4)]
        if not any(headers): continue
        require(headers==['일자']+fields,'Extra: header mismatch')
        name=text(at(grid,1,c))
        require(name in names and names[name] not in result,'Extra: company mismatch')
        rows={}
        for r in range(3,len(grid)):
            cells=[at(grid,r,c+i) for i in range(4)]
            if not any(text(v) for v in cells): continue
            date=day(cells[0],'quarter')
            require(date not in rows,'Extra: duplicate quarter')
            values=[number(v,f) for v,f in zip(cells[1:],fields)]
            require(all(v is not None for v in values),'Extra: missing value')
            rows[date]=dict(zip(fields,values))
        require(list(rows)==dates,'Extra: incomplete or unordered quarters')
        result[names[name]]=rows
    require(set(result)==set(info),'Extra: incomplete company set')
    return result

def accepted_million(difference):
    return math.isfinite(difference) and abs(difference)*1e6 < 100_000_000

def reconcile(code, data, prefer_infomax=False):
    ref=REFERENCES[code]
    inc,bal,debt=(data[k][code] for k in EXTRAS)
    now=QUARTERS[0]; begin='2025-06-30'
    for date in BALANCE_DATES:
        require(bal[date]['자본']==debt[date]['자본'],'Duplicate equity mismatch')
    observed=dict(equity=bal[now]['자본']/1000,nci=bal[now]['기말비지배주주지분']/1000,
        opening_equity=bal[begin]['자본']/1000,opening_nci=bal[begin]['기말비지배주주지분']/1000,
        cash=bal[now]['현금및현금성자산']/1000,parent_q2=inc[now]['당기순이익지배기업주주지분']/1000,
        parent_h1=sum(inc[d]['당기순이익지배기업주주지분'] for d in QUARTERS[:2])/1000,
        parent_ttm=sum(inc[d]['당기순이익지배기업주주지분'] for d in QUARTERS)/1000,
        interest_q2=inc[now]['이자비용']/1000,
        interest_h1=sum(inc[d]['이자비용'] for d in QUARTERS[:2])/1000,
        profit_q2=inc[now]['영업이익']/1000)
    official={k:ref[k] for k in observed if k!='parent_ttm'}
    official['parent_ttm']=ref['parent_fy']-ref['parent_prior_h1']+ref['parent_h1']
    differences={k:observed[k]-official[k] for k in observed}
    if not prefer_infomax:
        require(all(accepted_million(v) for v in differences.values()),f'{code}: official monetary mismatch {differences}')
    average=((observed['equity']-observed['nci'])+(observed['opening_equity']-observed['opening_nci']))/2
    require(average>0 and observed['interest_q2']>0 and observed['equity']>0,'Invalid ratio denominator')
    official_total_debt=sum(ref['debt_components'].values())
    total_debt=official_total_debt
    supplier_borrowing=debt[now]['차입금']/1000
    borrowing_difference=supplier_borrowing-sum(ref['supplier_borrowing_components'].values())
    bond_difference=debt[now]['사채']/1000-ref['supplier_bond_reference']
    if prefer_infomax:
        total_debt += borrowing_difference + bond_difference
    else:
        require(accepted_million(borrowing_difference), 'Supplier borrowing component match failed')
    policy_notes = ([
        '사용자 결정: 금액 차이는 인포맥스 우선. 인포맥스 차입금·사채를 사용하고 미확보 유동성 부채·리스는 원문에서 보충. 단기금융상품은 미차감.',
        '혼합 출처 추정치: 공급자와 원문 계정의 세부 범위 동일성은 미확인. 보충 항목과 중복 가능성을 배제하지 못함.',
    ] if prefer_infomax else [
        '순차입금은 공식 연결재무상태표의 유동성분·사채·리스를 포함하고 현금및현금성자산만 차감. 단기금융상품은 미차감.'
    ])
    return dict(code=code,status='user_policy_infomax_priority' if prefer_infomax else 'official_reconciled',unit='million KRW',
        official=official,observed=observed,differences_million_krw=differences,
        metrics=dict(roe_pct=observed['parent_ttm']/average*100,
                     interest_coverage_x=observed['profit_q2']/observed['interest_q2'],
                     net_debt_equity_pct=(total_debt-observed['cash'])/observed['equity']*100),
        debt_components_million_krw=ref['debt_components'],total_debt_million_krw=total_debt,
        official_total_debt_million_krw=official_total_debt,
        provider_priority_applied=prefer_infomax,
        provider_adjustments_million_krw=dict(borrowing=borrowing_difference,bonds=bond_difference) if prefer_infomax else {},
        official_amount_checks_within_tolerance=all(accepted_million(v) for v in differences.values()),
        supplier_borrowing_million_krw=supplier_borrowing,
        supplier_bonds_million_krw=debt[now]['사채']/1000,
        supplier_bonds_minus_official_noncurrent_million_krw=debt[now]['사채']/1000-ref['supplier_bond_reference'],
        scope=(ref['scope'].replace('순차입금은 공식 잔액으로 재구성.', '순차입금 계산에는 사용자 선택에 따라 인포맥스 사채를 우선 반영.') if prefer_infomax else ref['scope']),source=ref['url'],annual_source=ref['annual_url'],
        pdf_pages=ref['pdf_pages'],annual_income_pdf_page=ref['annual_income_pdf_page'],
        ttm_reconstruction=dict(fy2025=ref['parent_fy'],h1_2025=ref['parent_prior_h1'],h1_2026=ref['parent_h1']),
        notes=policy_notes+['ROE는 2025-07~2026-06 TTM, 이자보상배율은 2026년 2분기 단독 3개월.',
               '반기/연간으로 TTM 합계를 대조한 것이며 144개 과거 원계정 전체를 개별 대조했다는 뜻은 아님.',
               '계정 숫자 대조는 공급자의 모든 종목·기간 정의 확정을 의미하지 않음.'])

def audit():
    policy=json.loads((HERE.parents[1]/'config/infomax.user-decisions.json').read_text(encoding='utf-8'))
    prefer_infomax=policy.get('financial_source_priority',{}).get('decision')=='prefer_infomax_on_monetary_difference'
    info=parse_info(read_grid(HERE/'info.xlsx')[0]); data={}; sources={}
    for kind,fields in EXTRAS.items():
        grid,sources[kind]=read_grid(HERE/(kind+'.xlsx'))
        data[kind]=parse_extra(grid,fields,info,QUARTERS if kind=='income-extra' else BALANCE_DATES)
    return dict(retrieved_on='2026-09-28',sources=sources,
                companies={code:reconcile(code,data,prefer_infomax=prefer_infomax) for code in info})
