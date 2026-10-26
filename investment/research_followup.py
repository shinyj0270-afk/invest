"""Immutable local research cohorts and read-only forward price observations.

No retrospective membership, DB mutations, retrieval, jobs or investment signals.
"""
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from .core import digest
from .portfolio_risk import checked, day, numeric
from .market_history import benchmark_calendar

HORIZONS = (63, 126, 252)
NOTE = ('고정 후보군 동일 초기비중 가격 관찰 · 고정일 다음 완료 거래일 종가 기준 · '
        '63/126/252거래일 후 평가(약 3/6/12개월) · 배당·세금·체결비용 제외 · '
        '가설 인과/전략 수익률/ROIC·CAP 검증과 구분; 탈락 기업을 사후 제거하지 않음.')


def plan_path(root, profile, thesis_id, revision):
    if profile not in ('work', 'home') or not isinstance(thesis_id,str) or not thesis_id.strip() or len(thesis_id)>100 or type(revision) is not int or revision < 1:
        raise ValueError('연구 가설 식별정보 확인 필요')
    return Path(root)/'.local/research-followup'/profile/(digest([thesis_id,revision])+'.json')


def freeze(root, profile, record, candidates, selection_rule, *, frozen_at=None):
    """Explicit write operation only. Repeating identical inputs reuses the plan."""
    path = plan_path(root, profile, record['id'], record['revision'])
    if not isinstance(selection_rule,str) or not selection_rule.strip() or len(selection_rule)>2000:
        raise ValueError('후보 선정 규칙 필요')
    if not isinstance(candidates,list) or not 1<=len(candidates)<=500:
        raise ValueError('연구 후보 1~500개 명시 필요')
    cohort=[]
    for item in candidates:
        if set(item)!={'code','market','name','industry'} or not re.fullmatch(r'\d{6}',item['code']) or item['market'] not in ('KOSPI','KOSDAQ') or any(not isinstance(item[k],str) or not item[k].strip() for k in ('name','industry')):
            raise ValueError('후보 기업·시장·산업 식별 확인 필요')
        cohort.append(dict(item))
    if len({x['code'] for x in cohort})!=len(cohort):raise ValueError('중복 후보 기업')
    cohort.sort(key=lambda x:x['code'])
    identity=dict(thesis_id=record['id'],revision=record['revision'],thesis_digest=digest(record['value']),
        candidates=cohort,selection_rule=selection_rule)
    if path.exists():
        saved=read_plan(path)
        if any(saved[k]!=v for k,v in identity.items()):raise ValueError('기존 관찰계획 충돌; 보존하고 새 가설 revision 검토')
        return dict(created=False,plan=saved)
    at=frozen_at or datetime.now(timezone.utc).isoformat()
    frozen_on=datetime.fromisoformat(at).astimezone(timezone(timedelta(hours=9))).date().isoformat()
    recorded_on=datetime.fromisoformat(record['recorded_at']).astimezone(timezone(timedelta(hours=9))).date().isoformat()
    if not day(frozen_on) or frozen_on<max(record['value']['as_of'],recorded_on):raise ValueError('가설 기록 이전으로 소급 계획 불가')
    value=dict(schema=1,profile=profile,**identity,frozen_at=at,frozen_on=frozen_on,
        horizons=list(HORIZONS),entry_rule='first_completed_session_after_freeze',weight_rule='equal_initial_buy_hold',definition=NOTE)
    value['digest']=digest(value)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)
    return dict(created=True,plan=value)


def read_plan(path):
    value=json.loads(path.read_text(encoding='utf-8'))
    if (value.get('digest')!=digest({k:v for k,v in value.items() if k!='digest'})
        or value.get('horizons')!=list(HORIZONS) or value.get('schema')!=1
        or value.get('entry_rule')!='first_completed_session_after_freeze'
        or value.get('weight_rule')!='equal_initial_buy_hold'):
        raise ValueError('연구 관찰계획 무결성·계약 확인 필요')
    return value


def evaluate(plan, cache, cutoff):
    result=dict(status='pending',definition=NOTE,frozen_on=plan['frozen_on'],
        candidates=len(plan['candidates']),selection_rule=plan['selection_rule'],horizons=[])
    try:
        if not day(cutoff):raise ValueError('평가일 확인 필요')
        history=(cache or {}).get('history',{})
        # Remove future observations before deriving the source-session calendar.
        indexes={m:dict(r,prices=[p for p in r['prices'] if p['date']<=cutoff]) for m,r in history.get('benchmarks',{}).items()}
        calendar=benchmark_calendar(indexes)
        if calendar['sessions'][0]>plan['frozen_on']:
            raise ValueError('후보 고정일 전후 지수 이력 필요; 시작일을 사후 이동하지 않음')
        dates=[d for d in calendar['sessions'] if plan['frozen_on']<d<=cutoff]
        result.update(as_of=calendar['valid_through'],entry_date=dates[0] if dates else None,elapsed_returns=max(0,len(dates)-1))
        if not dates:
            result['reason']='후보 고정일 다음 완료 종가 대기'
        for size in HORIZONS:
            row=dict(days=size,label={63:'3개월',126:'6개월',252:'12개월'}[size],status='waiting',
                remaining_sessions=max(0,size-max(0,len(dates)-1)))
            result['horizons'].append(row)
            if len(dates)<=size:continue
            selected=dates[:size+1]; paths=[];benchmarks=[]
            try:
                bases=set()
                for candidate in plan['candidates']:
                    code=candidate['code'];record=history.get('histories',{}).get(code,{})
                    if record.get('symbol')!=code or record.get('kind')!='item':raise ValueError(code+' 가격 식별·상장폐지 이력 대기')
                    prices=checked(record.get('prices'),selected[-1])
                    prices=[p for p in prices if p['date']>=selected[0]]
                    if [p['date'] for p in prices]!=selected:raise ValueError(code+' 관측 누락·평가 종가 대기; 후보 제거하지 않음')
                    bases.update(p['adjustment_basis'] for p in prices)
                    if 'index_level' in bases or len(bases)!=1:raise ValueError('후보 간 수정가격 기준 불일치')
                    paths.append([p['close']/prices[0]['close'] for p in prices])
                    bm={p['date']:p['close'] for p in indexes[candidate['market']]['prices']}
                    benchmarks.append(bm[selected[-1]]/bm[selected[0]]-1)
                wealth=[sum(v[i] for v in paths)/len(paths) for i in range(len(selected))]
                peak=1.;drawdown=0.
                for v in wealth:
                    if not numeric(v):raise ValueError('관찰 수익률 계산 범위 초과')
                    peak=max(peak,v);drawdown=min(drawdown,v/peak-1)
                ret=(wealth[-1]-1)*100;bm=sum(benchmarks)/len(benchmarks)*100
                row.update(status='ready',entry_date=selected[0],evaluation_date=selected[-1],
                    return_pct=ret,benchmark_return_pct=bm,excess_return_pp=ret-bm,max_drawdown_pct=drawdown*100,
                    observations=size,benchmark='고정 후보의 KOSPI/KOSDAQ 초기비중 혼합 가격지수')
            except (ValueError,KeyError,TypeError,OverflowError,ZeroDivisionError) as exc:
                row.update(status='pending',reason=str(exc))
        if any(h['status']=='ready' for h in result['horizons']):result['status']='observing'
        elif dates:result.update(status='waiting',reason='관측기간 미도래 또는 가격 자료 대기')
    except (ValueError,KeyError,TypeError) as exc:result['reason']=str(exc)
    return result


def project(root, profile, record, cache=None):
    try:
        path=plan_path(root,profile,record['id'],record['revision'])
        if not path.exists():return dict(status='unplanned',reason='후보군·규칙 고정 전; 과거 성과를 소급 생성하지 않음')
        plan=read_plan(path)
        if plan['profile']!=profile or plan['thesis_id']!=record['id'] or plan['revision']!=record['revision'] or plan['thesis_digest']!=digest(record['value']):raise ValueError('가설 revision/관찰계획 불일치')
        if cache is None:
            from .market_discovery import load_market_cache
            cache=load_market_cache(root,{'meta':{'data_mode':'user_input'}})
        cutoff=(cache or {}).get('history',{}).get('calendar',{}).get('valid_through')
        if not cutoff:
            cutoff=datetime.now(timezone(timedelta(hours=9))).date().isoformat()
        return evaluate(plan,cache,cutoff)
    except (ValueError,OSError,KeyError,TypeError) as exc:return dict(status='pending',reason=str(exc))
