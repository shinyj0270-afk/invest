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
from .portfolio_risk import portfolio_risk

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

def minimum_financial_period(today):
    """Conservative freshness floor after regular filings usually accumulate.

    This research policy is not a legal filing deadline: Jan-Mar accepts the
    prior Q3, Apr-May the prior annual, Jun-Aug Q1, Sep-Nov Q2, and Dec Q3.
    Newer published reports remain preferred; build_table still enforces their
    actual availability dates before metrics enter the recommendation context.
    """
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
        if f['period']<required:excluded[r['code']]=f'재무 최신성 기준 {required} 이후 자료 대기';continue
        if not all(num(x) for x in (rs,short,t.get('close'),sma.get('200'))) or rs<70 or short<50 or t['close']<=sma['200'] or t.get('price_trend_status')!='pass':excluded[r['code']]='추세 조건 미충족';continue
        if m['revenue_growth_pct']<10 or m['operating_margin_pct']<=0 or m['roe_pct']<=0 or m['debt_ratio_pct']>200 or not num(f.get('ttm_ocf')) or f['ttm_ocf']<=0:excluded[r['code']]='성장/재무·현금흐름 조건 미충족';continue
        # Explicit research heuristic, not a backtested expected return.
        score=.4*rs+.2*short+.25*min(100,m['revenue_growth_pct'])+.15*min(100,m['roe_pct'])
        candidates.append((score,r,t,f))
    candidates.sort(key=lambda x:(-x[0],x[1]['code']))
    picks=[];industries={}
    for score,r,t,f in candidates:
        if industries.get(r['industry'],0)>=2:continue
        industries[r['industry']]=industries.get(r['industry'],0)+1
        picks.append(dict(code=r['code'],name=r['name'],market=r['market'],industry=r['industry'],weight_pct=16,
            price=t['close'],price_date=as_of,financial_period=f['period'],score=round(score,2),
            reason=f"매출 YoY {f['metrics']['revenue_growth_pct']:.1f}% · ROE {f['metrics']['roe_pct']:.1f}% · RS {t['price_strength']['score']:.1f}/1개월 {t['short_rs']['1m']['score']:.1f} · 기본 가격 추세 충족"+(' · ROE 원문 계정 허용오차 참고값' if f.get('metric_details',{}).get('roe_pct',{}).get('within_tolerance') else ''),
            risk=f"52주 최고종가 대비 {t.get('gap_to_52w_high_pct',0):.1f}% · 성장 둔화·기본 가격 추세 이탈·1개월 RS50 미만·자료 정정 시 재검토. 손절 주문 아님",
            business_review=business_review(r['code'],r['name'],created_on),
            sources=sorted(set(x['source'] for x in f['metric_details'].values())),source_urls=f.get('source_urls',[])))
        if len(picks)==5:break
    old={r['code']:r for r in (previous or {}).get('targets',[])};new={r['code']:r for r in picks}
    changes=[dict(code=code,name=(new.get(code) or old[code])['name'],action='편입' if code not in old else '제외' if code not in new else '유지',
        before_pct=old.get(code,{}).get('weight_pct',0),after_pct=new.get(code,{}).get('weight_pct',0),
        reason=(reason.strip()+' · ' if kind=='exception' else '')+new.get(code,{}).get('reason',excluded.get(code,'새 월간 기준 미충족 또는 산업 집중도 조정'))) for code in sorted(set(old)|set(new))]
    risk_summary=portfolio_risk(picks,100-16*len(picks),context.get('_risk_cache'),as_of)
    return dict(id=uuid4().hex,month=created_on[:7],created_on=created_on,price_date=as_of,kind=kind,
        reason=reason.strip() or '월간 성장형 기준 재검토',targets=picks,cash_pct=100-16*len(picks),changes=changes,
        coverage=dict(eligible=sum(r.get('discovery_allowed',False) for r in context['snapshot']['companies']),qualified=len(candidates),selected=len(picks),excluded=len(excluded)),
        assumptions='연구용 초안: 최대5종목·종목16%·같은 산업 최대32%·현금 최소20%. 성장/추세 중심 자체 규칙이며 개인 손실 허용도 확정값·매매 주문이 아닙니다. 자료 부족 슬롯은 현금으로 남깁니다.',
        method='RS12개월40% + RS1개월20% + 상한100 매출성장률25% + 상한100 ROE15%; 최신 연결·연속4분기·양수 TTM 영업현금흐름과 성장/추세 필터 적용. 기대수익률·검증된 최적화 점수 아님',
        review_status='자료 기준 추천 초안',
        portfolio_risk=risk_summary,
        review_needed=bool(not picks or risk_summary['status']=='pending' or any(not p.get('business_review') or p['business_review'].get('stale') for p in picks)),
        exclusion_reasons={reason:sum(v==reason for v in excluded.values()) for reason in set(excluded.values())},
        input_digest=digest(dict(as_of=as_of,targets=picks)))

def performance(record,cache):
    histories=(cache or {}).get('history',{}).get('histories',{});cutoff=(cache or {}).get('history',{}).get('calendar',{}).get('valid_through')
    benchmarks=(cache or {}).get('history',{}).get('benchmarks',{})
    dates=[p['date'] for p in benchmarks.get('KOSPI',{}).get('prices',[]) if p['date']>record['created_on'] and p['date']<=str(cutoff)]
    if not dates:return dict(status='pending',reason='작성 후 첫 완료 거래일 종가부터 모델 성과 측정',as_of=cutoff)
    entry=min(dates);total=0;parts=[]
    for target in record['targets']:
        ps={p['date']:p['close'] for p in histories.get(target['code'],{}).get('prices',[]) if p.get('final') is True}
        if not all(num(ps.get(d)) and ps[d]>0 for d in (entry,cutoff)):return dict(status='missing',reason='진입일 또는 평가일 종가 미확보; 누락 종목을 0수익으로 대체하지 않음',as_of=cutoff)
        value=(ps[cutoff]/ps[entry]-1)*100;total+=value*target['weight_pct']/100
        parts.append(dict(code=target['code'],name=target['name'],return_pct=value,contribution_pct=value*target['weight_pct']/100))
    benchmark_returns={}
    for market,record_bm in benchmarks.items():
        bps={p['date']:p['close'] for p in record_bm.get('prices',[])}
        if all(num(bps.get(d)) and bps[d]>0 for d in (entry,cutoff)):benchmark_returns[market]=(bps[cutoff]/bps[entry]-1)*100
    return dict(status='ready',entry_date=entry,as_of=cutoff,return_pct=total,parts=parts,benchmark_returns=benchmark_returns,
        definition='각 추천 버전 고정 비중의 가상 가격 성과. 작성 후 첫 거래일 종가 진입, 현금수익0·배당·수수료·세금 제외. 실제 보유 수익·버전 간 누적 실현성과 아님')

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
            supplemental_reviews={t['code']:business_review(t['code'],t['name'],today) for t in r['targets']}) for r in data['records']])
    def append(self,context,kind='monthly',reason='',today=None):
        day=today or datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
        with _LOCK:
            data=self.read()
            prior=data['records'][-1] if data['records'] else None
            if kind=='monthly' and any(r['month']==day[:7] and r['kind']=='monthly' for r in data['records']):return data
            record=propose(context,created_on=day,kind=kind,reason=reason,previous=prior)
            data['records'].append(record);self.path.parent.mkdir(parents=True,exist_ok=True);write_json(self.path,data);return data
