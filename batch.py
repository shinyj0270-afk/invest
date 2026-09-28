import argparse
import json
import os
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from investment.core import digest
from investment.store import Store
from investment.fixture import make_fixture
from investment import research,trend
from investment.local_config import load_local,require_profile

ROOT=Path(__file__).resolve().parent

def run(profile,mode,frequency,root=None):
    local=load_local(root or ROOT)
    profile=require_profile(local,profile)
    store=Store(local['data_dir'],profile,mode)
    lock=store.path.parent/'batch.lock'
    try: fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError: raise ValueError('동일 PC/모드 배치 실행 중 또는 남은 잠금 확인 필요') from None
    try:
        os.close(fd); snapshot=store.latest()
        if snapshot is None: raise ValueError('저장 스냅샷 없음 · 먼저 init-fixture 또는 앱의 명시적 저장 실행')
        r=research.analyze(snapshot); t=trend.analyze(snapshot)
        cfg=dict(frequency=frequency,quality_model=research.MODEL,trend_model=trend.MODEL,min_turnover=1e9)
        sid=digest(snapshot); config_hash=digest(cfg)
        run_id=digest(dict(snapshot=sid,config=config_hash))
        events=[]
        for item in r:
            for p in ('turnaround','technology'):
                if item['paths'][p]['signal_status']=='pass':
                    events.append(store.event(dict(code=item['code'],path=p,quarter=item['signals']['quarter'],model=research.MODEL,available_at=item['signals']['available_at'])))
        previous=store.setting('last_'+frequency,{})
        selected=research.balanced_list(r) if frequency=='weekly' else [x for x in t if x['status']=='pass' and x['score'] is not None][:10]
        old={x['code'] for x in previous.get('selected',[])}; new={x['code'] for x in selected}
        result=dict(run_id=run_id,snapshot_id=sid,config_hash=config_hash,mode=mode,profile=profile,
            evaluated_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),as_of=snapshot['meta']['price_date'],
            calendar_basis=snapshot['meta'].get('calendar_basis','observed_dates_unverified'),
            status='complete',frequency=frequency,selected=selected,events=events,research=r,trends=t,
            added=sorted(new-old),removed=sorted(old-new),
            change_reason='설정/모형 변경' if previous and previous.get('config_hash')!=config_hash else '입력/근거/기준일 변경' if previous and previous.get('snapshot_id')!=sid else '최초 실행' if not previous else '변경 없음',
            note='저장된 마지막 유효 관측일 사용. 공식 달력/최종 확정 여부 미검증 시 주간 최종 거래일로 인증하지 않음. 신규 수집 아님.')
        output=store.path.parent/(frequency+'-latest.json'); tmp=output.with_suffix('.tmp')
        tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); tmp.replace(output)
        store.save_setting('last_'+frequency,result)
        with store.connect() as db: db.execute('INSERT OR IGNORE INTO runs VALUES(?,?,?)',(run_id,result['evaluated_at'],json.dumps(result,ensure_ascii=False)))
        return result
    finally: lock.unlink(missing_ok=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('command',choices=['init-fixture','import-file','daily','weekly'])
    parser.add_argument('--file',type=Path)
    parser.add_argument('--scheduled',action='store_true')
    parser.add_argument('--profile',choices=['home','work','unknown'],default=None)
    parser.add_argument('--mode',choices=['fixture','user_input','live'],default='fixture')
    args=parser.parse_args()
    try:
        local=load_local(ROOT)
        args.profile=require_profile(local,args.profile)
        if args.scheduled and not local['scheduled_jobs_enabled']: raise ValueError('Scheduled jobs disabled in local PC config')
        if args.command=='init-fixture':
            if args.mode!='fixture': raise ValueError('fixture 초기화는 가상 모드만 허용')
            sid=Store(local['data_dir'],args.profile,args.mode).save_snapshot(make_fixture()); print('fixture saved '+sid[:16])
        elif args.command=='import-file':
            if not args.file: raise ValueError('--file 필요')
            sid=Store(local['data_dir'],args.profile,args.mode).save_snapshot(json.loads(args.file.read_text(encoding='utf-8')))
            print('validated local snapshot saved '+sid[:16])
        else:
            result=run(args.profile,args.mode,args.command); print(json.dumps({k:result[k] for k in ('status','as_of','frequency','change_reason')},ensure_ascii=False))
    except ValueError as exc: parser.exit(1,str(exc)+'\n')
