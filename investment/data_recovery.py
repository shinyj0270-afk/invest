"""Saved failure inventory and explicit, single-company recovery."""
import re
from pathlib import Path
from .local_config import load_local
from .market_discovery import read_market_cache,discovery_candidate
from .financial_health import read_record,collection_health


class DataRecovery:
    def __init__(self,root,daily,financial):
        self.root=Path(root);self.daily=daily;self.financial=financial

    def view(self):
        cfg=load_local(self.root);base=cfg['data_dir']/cfg['profile']
        cache=read_market_cache(self.root,{'meta':{'data_mode':'user_input'}}) or {}
        rows={r['code']:r for r in cache.get('universe',{}).get('companies',[])}
        names={code:r.get('name',code) for code,r in rows.items()}
        quotes=cache.get('quotes',{}).get('quotes',{})
        market=base/'market-expansion';side=market/'daily-failures.json';history=market/'histories.json'
        errors=cache.get('history',{}).get('errors',[])
        if side.is_file() and history.exists():
            stamp=history.stat();diagnostics=read_record(side)
            if diagnostics.get('history_version')==[stamp.st_mtime_ns,stamp.st_size]:errors=diagnostics.get('errors',errors)
        failures=[]
        for kind,items in [('price',errors),('financial', [dict(read_record(p),code=p.name[:-12]) for p in (base/'company-financials').glob('*.status.json')])]:
            for item in items:
                code=item.get('code','')
                if not re.fullmatch(r'[0-9A-Z]{6}',code) or code not in names:continue
                if kind=='financial' and item.get('status') not in ('failed','partial'):continue
                eligible=rows[code].get('eligibility')=='candidate'
                if kind=='financial':
                    eligible=discovery_candidate(rows[code],quotes.get(code))
                    dest=base/'company-financials'
                    saved=read_record(dest/(code+'.json'))
                    available=saved.get('companies',{}).get(code,{}).get('reports',[])
                    native=read_record(dest/'native-derived'/(code+'.json'))
                    health=collection_health(dest,code,dict(periods=available or native.get('periods',[])))
                    if health['status'] not in ('failed','partial'):continue
                    if health['status']!=item['status']:
                        item=dict(item,status=health['status'],stage='statements',reason='최근 저장 자료 기준 일부 보고서 조회·검증 대기',checked_at=health['last_checked'])
                failures.append(dict(kind=kind,code=code,name=names[code],status=item.get('status','failed'),eligible=bool(eligible),can_retry=bool(eligible and (self.daily if kind=='price' else self.financial)),
                    stage=item.get('stage','unknown'),reason=item.get('reason','이전 수집에는 상세 원인이 저장되지 않았습니다. 대상 재시도 후 확인할 수 있습니다.'),
                    checked_at=item.get('checked_at'),retry_at=item.get('retry_at')))
        failures.sort(key=lambda item:(item['status']=='partial',item['kind'],item['code']))
        return dict(scope='저장된 수집 기록 전체 · 최근 자동 점검 대상·건수와 다를 수 있습니다.',failures=failures,price_job=self.daily.poll() if self.daily else {},
                    financial_jobs={f['code']:self.financial.poll(f['code']) for f in failures if f['kind']=='financial'} if self.financial else {})

    def retry(self,kind,code):
        if not isinstance(code,str) or not re.fullmatch(r'[0-9A-Z]{6}',code) or kind not in ('price','financial'):
            raise ValueError('잘못된 복구 대상')
        if not any(f['kind']==kind and f['code']==code and f['can_retry'] for f in self.view()['failures']):
            raise ValueError('현재 실패 목록에 없는 대상')
        if kind=='price' and self.daily:return self.daily.start(codes=[code])
        if kind=='financial' and self.financial:return self.financial.start(code,retry=True)
        raise ValueError('읽기 전용 환경에서는 재시도할 수 없습니다.')
