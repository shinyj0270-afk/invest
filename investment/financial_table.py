"""Dated, read-only financial tables. All monetary inputs use KRW."""
import json
from datetime import date
from pathlib import Path
from .core import num, ratio
from .local_config import load_local

ROWS = [
    ('revenue', '매출액', '억원', 'amount'),
    ('operating_profit', '영업이익', '억원', 'amount'),
    ('net_income', '당기순이익', '억원', 'amount'),
    ('ebitda', 'EBITDA', '억원', 'amount'),
    ('borrowings', '차입금', '억원', 'amount'),
    ('total_borrowings', '총차입금', '억원', 'amount'),
    ('operating_margin', '영업이익률', '%', 'ratio'),
    ('ebitda_interest', 'EBITDA/이자비용', '배', 'ratio'),
    ('debt_ebitda', '총차입금/EBITDA', '배', 'ratio'),
    ('debt_ratio', '부채비율', '%', 'ratio'),
    ('borrowing_dependence', '차입금의존도', '%', 'ratio'),
]
INPUTS = {'revenue','operating_profit','net_income','ebitda','borrowings','total_borrowings',
          'equity','liabilities','assets','interest_expense','cost_of_sales','gross_profit','sga',
          'finance_income','finance_cost','other_income','other_cost','pretax','tax','parent_net','nci_net','eps',
          'current_assets','noncurrent_assets','current_liabilities','noncurrent_liabilities','parent_equity','nci',
          'cash','retained_earnings','ocf','cash_generated','noncash_adjustments','noncash_cost','noncash_income',
          'working_capital','icf','financing_cf','cash_change','cash_start','cash_end','capex_ppe','capex_intangibles'}

def valid_day(value):
    try:
        return isinstance(value,str) and date.fromisoformat(value).isoformat()==value
    except ValueError:
        return False

def values(record, cadence):
    raw={k:record.get(k) if num(record.get(k)) else None for k in INPUTS}
    result={k:raw[k]/1e8 if raw[k] is not None else None for k,_,_,kind in ROWS if kind=='amount'}
    result.update(operating_margin=ratio(raw['operating_profit'],raw['revenue'],100),
        ebitda_interest=ratio(raw['ebitda'],raw['interest_expense']),
        debt_ratio=ratio(raw['liabilities'],raw['equity'],100),
        borrowing_dependence=ratio(raw['total_borrowings'],raw['assets'],100),
        # A quarter's EBITDA must not be labelled as annual debt-servicing capacity.
        debt_ebitda=ratio(raw['total_borrowings'],raw['ebitda']) if cadence=='annual' else None)
    return result

def build_table(row, snapshot, supplemental=None, max_columns=6):
    cutoff=snapshot['meta']['price_date'];records=[]
    fixture=snapshot['meta']['data_mode']=='fixture'
    for cadence,key in [('annual','annual'),('quarter','quarters')]:
        for item in row.get(key,[]):
            # Research rows have an explicit date and KRW unit contract.
            records.append(dict(period_end=item.get('period_end'),available_at=item.get('available_at'),
                basis=item.get('basis'),cadence=cadence,source='가상 연구자료' if fixture else '저장 연구자료',
                revenue=item.get('revenue'),operating_profit=item.get('op'),net_income=item.get('net_income'),
                ebitda=item.get('ebitda'),interest_expense=item.get('interest_expense'),
                borrowings=item.get('borrowings'),total_borrowings=item.get('total_borrowings'),
                assets=item.get('assets'),equity=item.get('equity'),liabilities=item.get('liabilities')))
    notes=[]
    if supplemental:
        if (supplemental.get('code'),supplemental.get('name'),supplemental.get('market'))==(row['code'],row['name'],row['market']):
            records.extend(supplemental.get('periods',[]));notes.extend(supplemental.get('notes',[]))
        else:
            notes.append('추가 재무자료의 종목 식별이 달라 연결을 보류했습니다.')
    groups={};seen=set()
    for r in records:
        end=r.get('period_end');available=r.get('available_at');basis=r.get('basis');cadence=r.get('cadence')
        if not valid_day(end) or end>cutoff or basis not in ('CFS','OFS') or cadence not in ('annual','quarter','cumulative'):
            continue
        if available is not None and (not valid_day(available) or available>cutoff):
            continue
        # Duplicate period/basis/cadence is ambiguous; never silently add or overwrite it.
        identity=(end,basis,cadence)
        if identity in seen:
            return dict(groups=[],rows=ROWS,notes=['동일 기간·기준의 재무자료가 중복되어 표 연결을 보류했습니다.'])
        seen.add(identity)
        cell_notes={k:v for k,v in r.get('cell_notes',{}).items() if k in {x[0] for x in ROWS} and isinstance(v,str)}
        if cadence!='annual':cell_notes['debt_ebitda']='연간 EBITDA가 필요합니다. 분기·누적 EBITDA를 연간으로 환산하지 않습니다.'
        groups.setdefault((basis,cadence),[]).append(dict(period_end=end,available_at=available,
            source=r.get('source','저장 재무자료'),values=values(r,cadence),
            statement_values={k:r.get(k)/(1 if k=='eps' else 1e8) if num(r.get(k)) else None for k in INPUTS},
            source_url=r.get('source_url'),receipt=r.get('receipt'),
            filing_available_at=r.get('filing_available_at',available),
            interest_expense_eok=r.get('interest_expense')/1e8 if num(r.get('interest_expense')) else None,cell_notes=cell_notes))
    result=[]
    for (basis,cadence),columns in groups.items():
        result.append(dict(id=basis+'-'+cadence,basis=basis,cadence=cadence,
            columns=sorted(columns,key=lambda r:r['period_end'])[-max_columns:]))
    notes.extend(['금액: 억원. 손익은 표시 기간의 실적, 차입금은 기말 잔액입니다.',
        '부채비율 = 부채/자본, 차입금의존도 = 총차입금/자산. 분모가 0 이하이면 표시하지 않습니다.',
        '미확보 항목은 —로 표시합니다. EBITDA는 직접 입력하거나 동일 기간 상각비로 계산할 수 있습니다.'])
    if records and any(r.get('available_at') is None for r in records):
        notes.append('공개일을 확인하지 못한 저장 재무자료가 포함됩니다. 과거 시점 검증용 자료가 아닙니다.')
    return dict(groups=result,rows=ROWS,notes=list(dict.fromkeys(notes)))

def load_local_financials(root, snapshot):
    """Read the existing manual input folder; no retrieval, writes, or DB access."""
    if snapshot['meta']['data_mode']!='user_input':return {}
    local=load_local(root);manual=local['manual_snapshot_file']
    if not manual:return {}
    folder=manual.parent
    required=['config-review.json','info.xlsx','income.xlsx','balance.xlsx']
    if not all((folder/name).is_file() for name in required):return {}
    try:
        from tools.infomax_import import read_grid,parse_info,parse_history,UNITS
        config=json.loads((folder/'config-review.json').read_text(encoding='utf-8-sig'))
        if (config.get('mode')!='user_input' or config.get('financial_basis')!='CFS'
            or config.get('income_comp')!='순' or config.get('balance_comp')!='누적' or config.get('units')!=UNITS):
            return {}
        info=parse_info(read_grid(folder/'info.xlsx')[0]);data={};sources={}
        for kind in ('income','balance'):
            grid,sources[kind]=read_grid(folder/(kind+'.xlsx'));data[kind]=parse_history(grid,kind,info)
        for name,kind,fields in [('income-extra','income',['이자비용','영업이익','당기순이익지배기업주주지분']),
                                 ('balance-extra','balance',['자본','기말비지배주주지분','현금및현금성자산']),
                                 ('debt-extra','balance',['차입금','사채','자본'])]:
            if (folder/(name+'.xlsx')).is_file():
                grid,sources[name]=read_grid(folder/(name+'.xlsx'))
                data[name]=parse_history(grid,kind,info,fields=fields)
        result={}
        for row in snapshot['companies']:
            code=row['code'];identity=info.get(code,{})
            if (identity.get('name'),identity.get('market'))!=(row['name'],row['market']):continue
            periods=[]
            for end,inc in data['income'][code].items():
                bal=data['balance'][code].get(end,{})
                extra=data.get('income-extra',{}).get(code,{}).get(end,{})
                debt=data.get('debt-extra',{}).get(code,{}).get(end,{})
                more_balance=data.get('balance-extra',{}).get(code,{}).get(end,{})
                if debt and debt.get('자본')!=bal.get('자본'):raise ValueError('자본 대조 불일치')
                if extra and extra.get('영업이익')!=inc.get('영업이익'):raise ValueError('영업이익 대조 불일치')
                if all(num(bal.get(k)) for k in ('자산','자본','부채')) and abs(bal['자산']-bal['자본']-bal['부채'])>max(1,abs(bal['자산'])*1e-8):
                    raise ValueError('잔액 대차 불일치')
                r=dict(period_end=end,basis='CFS',cadence='quarter',available_at=None,
                    source='인포맥스 저장 XLSX · 연결 단독분기',cell_notes={})
                for dest,source,field in [('revenue',inc,'매출액(영업수익)'),('operating_profit',inc,'영업이익'),
                    ('net_income',inc,'당기순이익(포괄손익계산서)'),('assets',bal,'자산'),('equity',bal,'자본'),
                    ('liabilities',bal,'부채'),('interest_expense',extra,'이자비용'),('borrowings',debt,'차입금'),
                    ('parent_net',extra,'당기순이익지배기업주주지분'),('current_assets',bal,'유동자산'),
                    ('current_liabilities',bal,'유동부채'),('nci',more_balance,'기말비지배주주지분'),
                    ('cash',more_balance,'현금및현금성자산')]:
                    r[dest]=source.get(field)*1000 if num(source.get(field)) else None
                evidence=row.get('additional_financial_evidence',{})
                now=row.get('financial_period',snapshot['meta'].get('financial_period',''))[:10]
                if (end==now and evidence.get('unit')=='million KRW'
                    and evidence.get('observed',{}).get('equity')==r.get('equity',0)/1e6
                    and num(evidence.get('total_debt_million_krw'))):
                    r['total_borrowings']=evidence['total_debt_million_krw']*1e6
                    note='유동성 부채·리스 보충을 포함한 기존 검토값. 계정 범위 동일성 미확인인 혼합 출처 추정치입니다.'
                    r['cell_notes'].update(total_borrowings=note,borrowing_dependence=note)
                periods.append(r)
            result[code]=dict(code=code,name=row['name'],market=row['market'],periods=periods,
                notes=['인포맥스 관측값을 우선 표시합니다. 원문과의 대조 범위는 기존 검토 기록을 따릅니다.'])
        from .dart_statements import load_bundle
        return merge_financials(result,load_bundle(folder/'company-statements.json',snapshot))
    except (OSError,ValueError,KeyError,TypeError):
        # Bad supplemental input must not turn into a successful synthetic table.
        return {}


def merge_financials(provider, official):
    """Supplement missing cells, retaining every numeric provider value and its limitations."""
    import copy
    result=copy.deepcopy(official)
    for code,record in provider.items():
        if code not in result:result[code]=copy.deepcopy(record);continue
        target=result[code]
        if (target['name'],target['market'])!=(record['name'],record['market']):continue
        by_period={(r['basis'],r['cadence'],r['period_end']):r for r in target['periods']}
        for raw in record['periods']:
            key=(raw['basis'],raw['cadence'],raw['period_end']);prior=by_period.get(key)
            if prior:
                note=dict(prior.get('cell_notes',{}),**raw.get('cell_notes',{}))
                for field in INPUTS:
                    if num(raw.get(field)):
                        if num(prior.get(field)) and raw[field]!=prior[field]:note[field]='인포맥스 관측값 우선 · 공시값과 금액 차이 보존'
                        prior[field]=raw[field]
                prior['source']='인포맥스 저장 XLSX 우선 / DART 미확보 계정 보충'
                # The provider's publication date remains unknown; do not lend it a filing date.
                prior['filing_available_at']=prior['available_at'];prior['available_at']=raw.get('available_at')
                prior['cell_notes']=note
            else:target['periods'].append(copy.deepcopy(raw))
        target['notes']=list(dict.fromkeys(target.get('notes',[])+record.get('notes',[])+[
            '인포맥스 금액 우선, 없는 계정만 DART로 보충합니다. 공개일 미확인 공급자 금액의 과거 시점 재현은 보장하지 않습니다.']))
    return result
