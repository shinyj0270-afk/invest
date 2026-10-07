"""Native currency statements and completeness, separate from KRW price valuation."""
from datetime import date,timedelta
from .core import num,ratio
from .fiscal_contract import same_fiscal_identity,contiguous_quarters,shift_month

REQUIRED=('revenue','operating_profit','net_income','assets','liabilities','equity','ocf')


def fx_status(groups):
    if any(g.get('currency')=='USD' for g in groups):
        return dict(status='pending',required_provenance=['source_url','observed_on','currency_pair','flow_average_method','balance_closing_method','rates'],reason='검증된 환산 자료 미연결; 원통화 보존')
    return dict(status='not_required',required_provenance=[],reason='KRW 재무와 KRW 시총은 통화 환산 불필요')


def dependency_notes(reports):
    notes={};evidence={}
    for report in reports:
        for field,note in report.get('reconciliation_notes',{}).items():
            message=f"{report['period_end']} 원문 명시 계정 참고 사용 · 귀속 합계 잔차 {note.get('difference_krw'):+,.0f} KRW (1억원 미만) · 분기·TTM·비율 오차 범위 보장 아님"
            notes.setdefault(field,[]).append(message)
            evidence.setdefault(field,[]).append(dict(note,period_end=report['period_end'],currency=report.get('currency','KRW'),receipt=report['receipt'],sha256=report.get('sha256')))
        for field,note in report.get('account_reconciliation',{}).items():
            notes.setdefault(field,[]).append(f"{report['period_end']} 원문 중복 계정의 총계·귀속·현금 독립 검산")
            evidence.setdefault(field,[]).append(dict(note,period_end=report['period_end'],currency=report.get('currency','KRW'),receipt=report['receipt'],sha256=report.get('sha256')))
    return dict(cell_notes={k:' · '.join(dict.fromkeys(v)) for k,v in notes.items()},reconciliation_dependencies=evidence)


def fiscal_quarter_records(reports,cutoff):
    from .dart_statements import FLOW,CASH_FLOW
    reports=sorted(reports,key=lambda r:(r['basis'],r['period_end']))
    keys=lambda r:(r['code'],r['basis'],r['currency'],r['fiscal_year'],r['calendar_segment'],r['quarter'])
    lookup={keys(r):r for r in reports};output=[]
    if len(lookup)!=len(reports):raise ValueError('같은 회계기간 원문 중복')
    for r in reports:
        if r['available_at']>cutoff or r['period_end']>cutoff:continue
        q=r['quarter'];previous=lookup.get(keys(r)[:-1]+(q-1,)) if q>1 else None
        comparable=previous is not None and same_fiscal_identity(r,previous)
        start=r['period_start'] if q==1 else (date.fromisoformat(previous['period_end'])+timedelta(days=1)).isoformat() if comparable else shift_month(date.fromisoformat(r['period_start']),3*(q-1)).isoformat()
        base=dict(code=r['code'],period_end=r['period_end'],available_at=r['available_at'],basis=r['basis'],
            currency=r['currency'],calendar_segment=r['calendar_segment'],fiscal_year=r['fiscal_year'],fiscal_quarter=q,
            year_end_month=r['year_end_month'],source=r['source'],source_url=r['url'],receipt=r['receipt'],sha256=r['sha256'],
            period_contract=r['period_contract'],current_column_evidence=r['current_column_evidence'])
        current=dict(r['values']);values=dict(current)
        for k in FLOW|CASH_FLOW:
            values[k]=current.get(k) if q==1 else current[k]-previous['values'][k] if comparable and num(current.get(k)) and num(previous['values'].get(k)) else None
        values['eps']=current.get('eps') if q==1 else None
        values['cash_start']=current.get('cash_start') if q==1 else previous['values'].get('cash_end') if comparable else None
        available=max(r['available_at'],previous['available_at']) if comparable else r['available_at']
        dependencies=[dict(receipt=x['receipt'],url=x['url'],sha256=x['sha256'],available_at=x['available_at']) for x in ([previous,r] if comparable else [r])]
        if available<=cutoff:
            output.append(dict(base,period_start=start,available_at=available,cadence='quarter',derivation='source_quarter' if q==1 else 'adjacent_fiscal_ytd_difference' if comparable else 'pending_adjacent_ytd',dependencies=dependencies,**dependency_notes([previous,r] if comparable else [r]),**values))
        # Full-year data remains available on its own receipt even if Q3 is missing/future.
        if q==4:
            output.append(dict(base,period_start=r['period_start'],cadence='annual',dependencies=[dependencies[-1]],**dependency_notes([r]),**current))
        elif q>1:output.append(dict(base,period_start=r['period_start'],cadence='cumulative',dependencies=[dependencies[-1]],**dependency_notes([r]),**current))
    return output


def contiguous(columns):
    if any(c.get('calendar_segment') for c in columns):return contiguous_quarters(columns)
    from .financial_metrics import contiguous as legacy_contiguous
    return legacy_contiguous(columns)


def prior_quarter(latest,quarters):
    if latest.get('calendar_segment'):
        return next((c for c in quarters if c.get('fiscal_year')==latest['fiscal_year']-1 and c.get('fiscal_quarter')==latest['fiscal_quarter'] and all(c.get(k)==latest.get(k) for k in ('basis','currency','calendar_segment','year_end_month'))),None)
    end=date.fromisoformat(latest['period_end'])
    try:prior=end.replace(year=end.year-1).isoformat()
    except ValueError:prior=end.replace(year=end.year-1,day=28).isoformat()
    return next((c for c in quarters if c['period_end']==prior),None)


def financial_completeness(periods,cutoff,errors=()):
    from .financial_table import valid_day
    available=[p for p in periods if valid_day(p.get('period_end')) and p['period_end']<=cutoff and (p.get('available_at') is None or valid_day(p['available_at']) and p['available_at']<=cutoff)]
    basis='CFS' if any(p.get('basis')=='CFS' for p in available) else 'OFS'
    available=[p for p in available if p.get('basis')==basis]
    if not available:return dict(status='pending',basis=basis,latest_stored=dict(status='pending',reason='검증된 원문 재무 미확보'),ttm=dict(status='pending'),required_accounts=dict(status='pending'),roe=dict(status='pending'),causes=['source_unavailable'],next_action='공식 제출목록·현재 재무 열·기간·통화를 확인하세요',source_urls=[])
    latest=max(available,key=lambda p:(p['period_end'],p['cadence']=='annual',p['cadence']=='cumulative'))
    qs=sorted((p for p in available if p.get('cadence')=='quarter'),key=lambda p:p['period_end'])
    qlatest=qs[-1] if qs else latest;four=qs[-4:];continuous=contiguous(four)
    missing=[k for k in REQUIRED if not num(qlatest.get(k))]
    profit='parent_net' if basis=='CFS' else 'net_income';book='parent_equity' if basis=='CFS' else 'equity'
    prior=prior_quarter(qlatest,qs);roe_missing=[]
    if not continuous:roe_missing.append('four_contiguous_quarters')
    if not all(num(c.get(profit)) for c in four):roe_missing.append(profit)
    if not num(qlatest.get(book)) or prior is None or not num(prior.get(book)):roe_missing.append('same_fiscal_quarter_average_'+book)
    if prior and num(qlatest.get(book)) and num(prior.get(book)) and (qlatest[book]+prior[book])/2<=0:roe_missing.append('positive_average_equity')
    ttm_missing=[k for k in ('revenue','operating_profit',profit,'ocf') if not all(num(c.get(k)) for c in four)]
    ttm_ready=continuous and not ttm_missing;causes=[]
    if not continuous:causes.append('noncontiguous_fiscal_quarters')
    if missing:causes.append('required_accounts_missing')
    if roe_missing:causes.append('roe_dependencies_missing')
    if errors:causes.append('collection_partial')
    urls=sorted({p['source_url'] for p in available if p.get('source_url')})
    return dict(status='ready' if not causes else 'partial',basis=basis,currency=latest.get('currency','KRW'),
        latest_stored=dict(status='ready',period_end=latest['period_end'],period_start=latest.get('period_start'),available_at=latest.get('available_at'),cadence=latest['cadence'],receipt=latest.get('receipt'),source_url=latest.get('source_url'),sha256=latest.get('sha256')),
        ttm=dict(status='ready' if ttm_ready else 'pending',contiguous=continuous,periods=[c['period_end'] for c in four],missing_accounts=ttm_missing,reason=None if ttm_ready else '같은 통화·회계달력의 연속4분기와 필수 흐름 계정 대기'),
        required_accounts=dict(status='ready' if not missing else 'pending',missing=missing,period_end=qlatest['period_end']),
        roe=dict(status='ready' if not roe_missing else 'pending',missing_dependencies=roe_missing,reason=None if not roe_missing else 'TTM 귀속 손익 및 전년 같은 회계분기 자본 대기'),
        causes=causes,next_action='누락 인접 누적보고서·귀속계정·전년 같은 회계분기 원문을 확인하세요' if causes else '다음 공식 공시·정정 확인',source_urls=urls)


def native_metrics(quarters,basis):
    latest=quarters[-1];prior=prior_quarter(latest,quarters);four=quarters[-4:];complete=contiguous_quarters(four)
    profit='parent_net' if basis=='CFS' else 'net_income';book='parent_equity' if basis=='CFS' else 'equity'
    ttm={k:sum(c[k] for c in four) if complete and all(num(c.get(k)) for c in four) else None for k in ('revenue','operating_profit',profit,'ocf')}
    avg=(latest[book]+prior[book])/2 if prior and num(latest.get(book)) and num(prior.get(book)) else None
    metrics=dict(operating_margin_pct=ratio(latest.get('operating_profit'),latest.get('revenue'),100),
        revenue_growth_pct=ratio(latest['revenue']-prior['revenue'],prior['revenue'],100) if prior and num(latest.get('revenue')) and num(prior.get('revenue')) else None,
        debt_ratio_pct=ratio(latest.get('liabilities'),latest.get('equity'),100),roe_pct=ratio(ttm[profit],avg,100),per=None,pbr=None)
    result=dict(basis=basis,period=latest['period_end'],currency=latest['currency'],fiscal_year=latest['fiscal_year'],fiscal_quarter=latest['fiscal_quarter'],year_end_month=latest['year_end_month'],calendar_segment=latest['calendar_segment'],metrics=metrics,ttm_complete=complete,ttm_ocf=ttm['ocf'],
        metric_details={k:dict(value=v,status='calculated' if v is not None else 'pending',source=latest['source'],basis=basis,period=latest['period_end'],currency=latest['currency'],
            observed_on=max([c['available_at'] for c in four]+([prior['available_at']] if prior else [])),reason=('검증된 환산 출처·날짜·손익 평균/기말 환율 방법 대기; KRW 시총과 원통화 금액을 나누지 않음' if latest['currency']=='USD' else '같은 날짜 가격·시총 및 TTM 귀속 손익·자본의 공통 가치평가 연결 대기; KRW 통화 환산 불필요') if k in ('per','pbr') else '동일 통화·회계기간 계정의 비율' if v is not None else '같은 회계분기·TTM 또는 귀속 계정 대기') for k,v in metrics.items()},
        amounts={k:latest[k]/1e8 if num(latest.get(k)) else None for k in REQUIRED} if latest['currency']=='KRW' else {},
        native_amounts={k:latest.get(k) for k in REQUIRED},amount_unit='억원' if latest['currency']=='KRW' else '백만 USD',amount_divisor=1e8 if latest['currency']=='KRW' else 1e6,
        source_urls=sorted({c['source_url'] for c in four+([prior] if prior else [])}))
    used={'operating_margin_pct':[(latest,'revenue'),(latest,'operating_profit')],
        'revenue_growth_pct':[(c,'revenue') for c in [latest]+([prior] if prior else [])],
        'roe_pct':[(c,profit) for c in four]+[(c,book) for c in [latest]+([prior] if prior else [])],
        'debt_ratio_pct':[(latest,'liabilities'),(latest,'equity')]}
    for metric,cells in used.items():
        notes=sorted({c.get('cell_notes',{}).get(field) for c,field in cells if c.get('cell_notes',{}).get(field)})
        detail=result['metric_details'][metric]
        detail['observed_on']=max(c['available_at'] for c,_ in cells)
        detail['dependencies']=[dict(field=field,period=c['period_end'],available_at=c['available_at'],currency=c['currency'],receipt=c['receipt'],source_url=c['source_url']) for c,field in cells]
        if notes and detail['value'] is not None:
            detail.update(status='reference_with_tolerance',within_tolerance=True,reconciliation_notes=notes)
            detail['reason']+=' · '+' · '.join(notes)
    return result


def build_native_payload(reports,cutoff):
    explicit=[r for r in reports if r.get('period_contract')]
    if not explicit:return None
    periods=fiscal_quarter_records(explicit,cutoff);groups=[];keys=sorted({(p['basis'],p['currency'],p['calendar_segment'],p['cadence']) for p in periods})
    for basis,currency,segment,cadence in keys:
        columns=sorted((p for p in periods if (p['basis'],p['currency'],p['calendar_segment'],p['cadence'])==(basis,currency,segment,cadence)),key=lambda p:p['period_end'])
        groups.append(dict(basis=basis,currency=currency,calendar_segment=segment,cadence=cadence,amount_unit='백만 USD' if currency=='USD' else '억원',amount_divisor=1e6 if currency=='USD' else 1e8,columns=columns))
    qs=[p for p in periods if p['cadence']=='quarter'];basis='CFS' if any(p['basis']=='CFS' for p in qs) else 'OFS'
    qs=sorted((p for p in qs if p['basis']==basis),key=lambda p:p['period_end']);latest=qs[-1] if qs else None
    # Never sum different currencies/segments even when dates happen to align.
    if latest:qs=[p for p in qs if p['currency']==latest['currency'] and p['calendar_segment']==latest['calendar_segment']]
    return dict(status='ready' if periods else 'pending',as_of=cutoff,groups=groups,common_financial=native_metrics(qs,basis) if qs else None,
        completeness=financial_completeness(periods,cutoff),fx=fx_status(groups),
        notes=['원통화 금액과 같은 통화 비율. USD 재무의 원화 시총 기반 PER/PBR에는 검증된 환산이 필요하며 KRW 재무는 통화 환산 불필요입니다.','단독분기 누적차감은 동일 기업·기준·통화·회계연도·달력구간의 인접 보고서만 사용합니다. EPS는 차감하지 않습니다.'])


def native_payload_at(payload,cutoff):
    """Rebuild metrics at the caller's price cutoff; precomputed later metrics leak."""
    if not payload:return None
    from copy import deepcopy
    value=deepcopy(payload);periods=[];groups=[]
    for g in value.get('groups',[]):
        columns=[p for p in g.get('columns',[]) if p.get('period_end','9999')<=cutoff and p.get('available_at','9999')<=cutoff and all(d.get('available_at','9999')<=cutoff for d in p.get('dependencies',[]))]
        if columns:groups.append(dict(g,columns=columns));periods.extend(columns)
    value.update(groups=groups,as_of=cutoff,status='ready' if periods else 'pending',completeness=financial_completeness(periods,cutoff),fx=fx_status(groups))
    qs=[p for p in periods if p['cadence']=='quarter'];basis='CFS' if any(p['basis']=='CFS' for p in qs) else 'OFS'
    qs=sorted((p for p in qs if p['basis']==basis),key=lambda p:p['period_end'])
    if qs:qs=[p for p in qs if (p['currency'],p['calendar_segment'])==(qs[-1]['currency'],qs[-1]['calendar_segment'])]
    value['common_financial']=native_metrics(qs,basis) if qs else None
    return value
