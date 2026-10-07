"""Private, immutable research recommendations, separate from holdings and orders."""
from datetime import date,datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4
from zoneinfo import ZoneInfo
import json
from .core import num,digest
from .local_config import load_local
from .financial_metrics import common_metrics,apply_common
from .financial_table import build_table
from .valuation import enrich_valuation
from .workspace_research import build_research
from .market_discovery import build_discovery
from .market_insights import enrich_market
from .market_refresh import write_json
from .portfolio_risk import portfolio_risk,compare_portfolios,common_window
from .recommendation_allocation import choose_and_allocate,RECOMMENDATION_POLICY

_LOCK=Lock()


def business_review(code,name,as_of):
    """Dated analyst interpretation, separate from numerical screening and forecasts."""
    try:
        data=json.loads((Path(__file__).resolve().parents[1]/'config/business_theses.json').read_text(encoding='utf-8'))
        r=data['companies'].get(code)
        if not r or r['name']!=name or data['reviewed_on']>as_of:return None
        return dict(r,reviewed_on=data['reviewed_on'],stale=(date.fromisoformat(as_of)-date.fromisoformat(data['reviewed_on'])).days>31,
                    method='공식 사업 자료 요약 + 작성자 해석. 성장 가설·반대 요인은 전망이며 확정 실적이 아닙니다.')
    except (OSError,ValueError,KeyError,TypeError):return None

def minimum_financial_period(today,year_end_month=12):
    """Conservative freshness floor after regular filings usually accumulate.

    This research policy is not a legal filing deadline: Jan-Mar accepts the
    prior Q3, Apr-May the prior annual, Jun-Aug Q1, Sep-Nov Q2, and Dec Q3.
    Newer published reports remain preferred; build_table still enforces their
    actual availability dates before metrics enter the recommendation context.
    """
    if year_end_month!=12:
        from .fiscal_contract import fiscal_bounds,shift_month
        candidates=[]
        for fy in (today.year-1,today.year,today.year+1):
            for q in (1,2,3,4):
                _,end=fiscal_bounds(fy,year_end_month,q)
                # Same conservative research delay as December policy: annual
                # four-month boundary; interim three-month boundary. Actual
                # source availability remains a separate mandatory check.
                boundary=shift_month(end.replace(day=1),4 if q==4 else 3)
                if boundary<=today:candidates.append(end.isoformat())
        return max(candidates)
    if today.month<=3:return f'{today.year-1}-09-30'
    if today.month<=5:return f'{today.year-1}-12-31'
    if today.month<=8:return f'{today.year}-03-31'
    if today.month<=11:return f'{today.year}-06-30'
    return f'{today.year}-09-30'


def research_context(snapshot,cache,financials,as_of):
    analysis=enrich_valuation(snapshot);d=build_discovery(analysis,build_research(analysis),cache,include_series=False)
    if not d:return None
    scope=dict(analysis,meta=dict(analysis['meta'],price_date=as_of))
    for r in d['snapshot']['companies']:
        if financials.get(r['code']):
            table=build_table(r,scope,financials[r['code']],max_columns=48)
            apply_common(r,d['research']['rows'][r['code']],common_metrics(r,table,d['research']['rows'][r['code']]['technical']))
    d['market_insights']=enrich_market(d,cache)
    d['_risk_cache']=cache  # In-memory only; never serialized into a recommendation.
    return d

def propose(context, *, created_on, kind='monthly', reason='', previous=None):
    if kind not in ('monthly','exception'):raise ValueError('검토 종류 확인 필요')
    if kind=='exception' and not reason.strip():raise ValueError('월중 조정 이유를 입력하세요')
    if not context:raise ValueError('실제 기업 자료 연결 대기')
    if not any(r.get('discovery_allowed') and r.get('common_financial') for r in context['snapshot']['companies']):raise ValueError('공통 재무자료 확보 후 추천안을 작성하세요')
    as_of=context['snapshot']['meta']['price_date'];today=date.fromisoformat(created_on)
    if as_of>created_on or (today-date.fromisoformat(as_of)).days>7:raise ValueError('최근 완료 종가 확인 후 추천안을 작성하세요')
    candidates=[];excluded={};required=minimum_financial_period(today)
    for r in context['snapshot']['companies']:
        if not r.get('discovery_allowed'):continue
        t=context['research']['rows'][r['code']]['technical'];f=r.get('common_financial');m=(f or {}).get('metrics',{})
        rs=t.get('price_strength',{}).get('score');short=t.get('short_rs',{}).get('1m',{}).get('score');sma=t.get('sma',{})
        if not r.get('discovery_allowed') or not f or f['basis']!='CFS' or not f['ttm_complete'] or not all(num(m.get(k)) for k in ('revenue_growth_pct','operating_margin_pct','roe_pct','debt_ratio_pct')):excluded[r['code']]='재무/비교기간 미확보';continue
        floor=minimum_financial_period(today,f.get('year_end_month',12))
        if f['period']<floor:excluded[r['code']]=f'재무 최신성 기준 {floor} 이후 자료 대기';continue
        if not all(num(x) for x in (rs,short,t.get('close'),sma.get('200'))) or rs<70 or short<50 or t['close']<=sma['200'] or t.get('price_trend_status')!='pass':excluded[r['code']]='추세 조건 미충족';continue
        if m['revenue_growth_pct']<10 or m['operating_margin_pct']<=0 or m['roe_pct']<=0 or m['debt_ratio_pct']>200 or not num(f.get('ttm_ocf')) or f['ttm_ocf']<=0:excluded[r['code']]='성장/재무·현금흐름 조건 미충족';continue
        # Explicit research heuristic, not a backtested expected return.
        score=.4*rs+.2*short+.25*min(100,m['revenue_growth_pct'])+.15*min(100,m['roe_pct'])
        candidates.append((score,r,t,f))
    candidates.sort(key=lambda x:(-x[0],x[1]['code']))
    shortlist=[]
    for score,r,t,f in candidates[:15]:
        shortlist.append(dict(code=r['code'],name=r['name'],market=r['market'],industry=r['industry'],weight_pct=0,
            price=t['close'],price_date=as_of,financial_period=f['period'],score=round(score,2),
            reason=f"매출 YoY {f['metrics']['revenue_growth_pct']:.1f}% · ROE {f['metrics']['roe_pct']:.1f}% · RS {t['price_strength']['score']:.1f}/1개월 {t['short_rs']['1m']['score']:.1f} · 기본 가격 추세 충족"+(' · ROE 원문 계정 허용오차 참고값' if f.get('metric_details',{}).get('roe_pct',{}).get('within_tolerance') else ''),
            risk=f"52주 최고종가 대비 {t.get('gap_to_52w_high_pct',0):.1f}% · 성장 둔화·기본 가격 추세 이탈·1개월 RS50 미만·자료 정정 시 재검토. 손절 주문 아님",
            business_review=business_review(r['code'],r['name'],created_on),
            sources=sorted(set(x['source'] for x in f['metric_details'].values())),source_urls=f.get('source_urls',[])))
    allocation=choose_and_allocate(shortlist,context.get('_risk_cache'),as_of)
    picks=allocation['targets'];cash_pct=allocation['cash_pct']
    old={r['code']:r for r in (previous or {}).get('targets',[])};new={r['code']:r for r in picks}
    changes=[dict(code=code,name=(new.get(code) or old[code])['name'],action='편입' if code not in old else '제외' if code not in new else '유지',
        before_pct=old.get(code,{}).get('weight_pct',0),after_pct=new.get(code,{}).get('weight_pct',0),
        reason=(reason.strip()+' · ' if kind=='exception' else '')+new.get(code,{}).get('reason',excluded.get(code,'새 월간 기준 미충족 또는 산업 집중도 조정'))) for code in sorted(set(old)|set(new))]
    risk_summary=portfolio_risk(picks,cash_pct,context.get('_risk_cache'),as_of)
    proposal=dict(targets=picks,cash_pct=cash_pct,created_on=created_on)
    risk_review=compare_portfolios(proposal,previous,context.get('_risk_cache'),as_of,RECOMMENDATION_POLICY)
    alternatives=[];selected={p['code'] for p in picks}
    alternative_targets=[]
    for candidate in shortlist:
        if candidate['code'] in selected or not picks:continue
        replacement=min(picks,key=lambda p:(p['score'],p['code']))
        alternative=dict(candidate,weight_pct=replacement['weight_pct'])
        alternative_targets.append((candidate,replacement,dict(targets=[alternative if p['code']==replacement['code'] else dict(p) for p in picks],cash_pct=cash_pct,created_on=created_on)))
        if len(alternative_targets)==3:break
    try:
        dates=common_window(picks+[(c) for c,_,_ in alternative_targets]+(previous or {}).get('targets',[]),context.get('_risk_cache'),as_of)
        risk_review=compare_portfolios(proposal,previous,context.get('_risk_cache'),as_of,RECOMMENDATION_POLICY,observation_dates=dates)
    except (ValueError,TypeError,KeyError):dates=None
    for candidate,replacement,composition in alternative_targets:
        review=compare_portfolios(composition,proposal,context.get('_risk_cache'),as_of,RECOMMENDATION_POLICY,observation_dates=dates)
        if dates is None:
            review.update(status='pending',deltas={},reason='전체 대안의 공통 관측기간 미확보; 대안 간 순위 비교 보류')
        alternatives.append(dict(code=candidate['code'],name=candidate['name'],replaces=replacement['code'],score=candidate['score'],review=review,
            advisory='동일 재무·추세 조건 통과 후보의 한 종목 교체 참고안. 자동 교체·매매 주문 아님'))
    allocation.pop('observation_dates',None);allocation.pop('targets',None)
    return dict(id=uuid4().hex,month=created_on[:7],created_on=created_on,price_date=as_of,kind=kind,
        reason=reason.strip() or '월간 성장형 기준 재검토',targets=picks,cash_pct=cash_pct,changes=changes,
        coverage=dict(eligible=sum(r.get('discovery_allowed',False) for r in context['snapshot']['companies']),qualified=len(candidates),selected=len(picks),excluded=len(excluded)),
        assumptions='사용자 확인 구성 한도: 최대5종목·종목당 최대40%·현금 최소5%. 성장/추세와 과거 상관·역변동성의 연구용 초안이며 개인 변동성·낙폭 한도나 매매 주문이 아닙니다. 종목 수 부족시 남는 비중은 현금입니다.',
        method='RS12개월40% + RS1개월20% + 상한100 매출성장률25% + 상한100 ROE15%; 최신 연결·연속4분기·양수 TTM 영업현금흐름과 성장/추세 필터 적용. 기대수익률·검증된 최적화 점수 아님',
        review_status='자료 기준 추천 초안',
        portfolio_risk=risk_summary,
        risk_review=risk_review,alternatives=alternatives,allocation=allocation,policy=dict(RECOMMENDATION_POLICY),
        review_needed=bool(not picks or risk_summary['status']=='pending' or allocation['status']=='pending' or risk_review['flags'] or any(not p.get('business_review') or p['business_review'].get('stale') for p in picks)),
        exclusion_reasons={reason:sum(v==reason for v in excluded.values()) for reason in set(excluded.values())},
        input_digest=digest(dict(as_of=as_of,targets=picks)))

def performance(record,cache):
    from .portfolio_risk import day,numeric,verified_price_inputs
    history=(cache or {}).get('history',{});cutoff=history.get('calendar',{}).get('valid_through')
    try:
        targets=record['targets'];weights=[t['weight_pct'] for t in targets];cash=record['cash_pct']
        if not day(record['created_on']) or len({t['code'] for t in targets})!=len(targets) or not all(numeric(w) and 0<w<=100 for w in weights) or not numeric(cash) or not 0<=cash<=100 or abs(sum(weights)+cash-100)>1e-6:
            raise ValueError('추천 작성일·종목·비중 확인 필요')
        calendar,series,_=verified_price_inputs(targets,cache,cutoff)
        dates=[d for d in calendar['sessions'] if record['created_on']<d<=cutoff]
        if not dates:return dict(status='pending',reason='작성 후 첫 완료 거래일 종가부터 모델 성과 측정',as_of=cutoff)
        entry=dates[0];total=0;parts=[]
        for target,rows in zip(targets,series):
            rows=[p for p in rows if p['date']>=entry]
            if [p['date'] for p in rows]!=dates:
                return dict(status='missing',reason=target['code']+' 진입일·평가일 또는 중간 거래일 종가 미확보; 누락 종목을 0수익으로 대체하지 않음',as_of=cutoff)
            value=(rows[-1]['close']/rows[0]['close']-1)*100;contribution=value*target['weight_pct']/100
            if not numeric(value) or not numeric(contribution):raise ValueError('가격 수익률 계산 범위 확인 필요')
            total+=contribution;parts.append(dict(code=target['code'],name=target['name'],return_pct=value,contribution_pct=contribution))
        if not numeric(total):raise ValueError('가격 수익률 계산 범위 확인 필요')
        benchmark_returns={}
        for market in ('KOSPI','KOSDAQ'):
            bps={p['date']:p['close'] for p in history['benchmarks'][market]['prices']}
            value=(bps[cutoff]/bps[entry]-1)*100
            if not numeric(value):raise ValueError('가격지수 수익률 계산 범위 확인 필요')
            benchmark_returns[market]=value
        return dict(status='ready',entry_date=entry,as_of=cutoff,return_pct=total,parts=parts,benchmark_returns=benchmark_returns,
            definition='각 추천 버전 고정 비중의 가상 가격 성과. 작성 후 첫 거래일 종가 진입, 현금수익0·배당·수수료·세금 제외. 실제 보유 수익·버전 간 누적 실현성과 아님')
    except (ValueError,TypeError,KeyError,OverflowError) as exc:
        return dict(status='pending',reason=str(exc),as_of=cutoff)

def current_risk_views(record, previous, cache, cutoff, today):
    """Re-evaluate saved compositions without changing their original qualification."""
    universe=(cache or {}).get('universe',{}).get('companies',[])
    replacements={t['code']:t for t in record.get('targets',[])}
    alternatives=[];compositions=[]
    for saved in record.get('alternatives',[])[:3]:
        matches=[r for r in universe if r.get('code')==saved.get('code') and r.get('name')==saved.get('name')]
        old=replacements.get(saved.get('replaces'))
        item=dict(saved,reviewed_on=today,advisory='작성 당시 통과한 대안 · 최신 가격 위험 재점검. 현재 재무·추세 자격을 재검증한 추천이 아닙니다.')
        if len(matches)!=1 or not old or matches[0].get('market') not in ('KOSPI','KOSDAQ'):
            item['review']=dict(status='pending',policy_status='pending',deltas={},reason='대안의 현재 기업 식별·시장·교체 대상 확인 대기')
            alternatives.append(item);continue
        row=matches[0]
        target=dict(code=row['code'],name=row['name'],market=row['market'],industry=row.get('industry') or '산업 미확인',weight_pct=old['weight_pct'])
        if target['code'] in replacements:
            item['review']=dict(status='pending',policy_status='pending',deltas={},reason='기존 편입 종목과 대안 중복 확인 필요')
            alternatives.append(item);continue
        composition=dict(targets=[target if t['code']==old['code'] else dict(t) for t in record['targets']],cash_pct=record['cash_pct'])
        item['identity_source']='저장 기업 목록의 종목코드·명칭 일치'
        alternatives.append(item);compositions.append((item,composition))
    dates=None
    try:
        dates=common_window(record.get('targets',[])+(previous or {}).get('targets',[])+[t for _,c in compositions for t in c['targets']],cache,cutoff)
    except (ValueError,TypeError,KeyError):pass
    review=compare_portfolios(record,previous,cache,cutoff,RECOMMENDATION_POLICY,observation_dates=dates,policy_as_of=today)
    if compositions and dates is None:
        review.update(status='pending',deltas={},reason='전체 대안과 이전·현재 구성의 공통 관측기간 미확보; 비교 차이·순위 보류')
    for item,composition in compositions:
        item['review']=compare_portfolios(composition,record,cache,cutoff,RECOMMENDATION_POLICY,observation_dates=dates,policy_as_of=today)
        if dates is None:item['review'].update(status='pending',deltas={},reason='전체 대안의 공통 관측기간 미확보; 비교 차이·순위 보류')
    return dict(current_risk_review=review,current_risk_alternatives=alternatives)


class RecommendationBook:
    def __init__(self,root):
        cfg=load_local(root);self.path=cfg['data_dir']/cfg['profile']/'recommendations'/'book.json'
    def read(self):
        if not self.path.exists():return dict(version=1,records=[])
        if self.path.stat().st_size>2_000_000:raise ValueError('추천 기록 크기 확인 필요')
        data=json.loads(self.path.read_text(encoding='utf-8'))
        if data.get('version')!=1 or not isinstance(data.get('records'),list):raise ValueError('추천 기록 형식 확인 필요')
        seen=set()
        for r in data['records']:
            if not isinstance(r,dict) or not r.get('id') or r['id'] in seen or r.get('kind') not in ('monthly','exception'):raise ValueError('추천 버전 확인 필요')
            seen.add(r['id']);date.fromisoformat(r['created_on'])
            targets=r.get('targets',[])
            weights=[t.get('weight_pct') for t in targets]+[r.get('cash_pct')]
            if not all(num(w) and 0<=w<=100 for w in weights) or abs(sum(weights)-100)>1e-6:raise ValueError('추천 비중 확인 필요')
            if len({t.get('code') for t in targets})!=len(targets):raise ValueError('추천 종목 중복 확인 필요')
        return data
    def view(self,cache):
        data=self.read();today=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
        # Supplement old records at a separately labelled review date; never rewrite their decision.
        cutoff=(cache or {}).get('history',{}).get('calendar',{}).get('valid_through')
        return dict(version=1,records=[dict(r,performance=performance(r,cache),
            current_portfolio_risk=portfolio_risk(r['targets'],r['cash_pct'],cache,cutoff),
            **current_risk_views(r,data['records'][i-1] if i else None,cache,cutoff,today),
            supplemental_reviews={t['code']:business_review(t['code'],t['name'],today) for t in r['targets']}) for i,r in enumerate(data['records'])])
    def append(self,context,kind='monthly',reason='',today=None):
        day=today or datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
        with _LOCK:
            data=self.read()
            prior=data['records'][-1] if data['records'] else None
            if kind=='monthly' and any(r['month']==day[:7] and r['kind']=='monthly' for r in data['records']):return data
            record=propose(context,created_on=day,kind=kind,reason=reason,previous=prior)
            data['records'].append(record);self.path.parent.mkdir(parents=True,exist_ok=True);write_json(self.path,data);return data
