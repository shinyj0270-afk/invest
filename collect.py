"""Explicit read-only collection to private staging, never automatic promotion."""
import argparse
import json
from datetime import datetime,timezone
from pathlib import Path
from investment.adapters import Reader,AdapterError
from investment.core import digest
from investment.local_config import load_local,require_profile

ROOT=Path(__file__).resolve().parent
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('provider',choices=['kiwoom','dart']); p.add_argument('operation')
    p.add_argument('--params',type=Path,required=True,help='비밀값 없는 요청 파라미터 JSON')
    args=p.parse_args()
    config_path=ROOT/'config/runtime.local.json'
    try:
        if not config_path.exists(): raise AdapterError('config/runtime.local.json 및 PC별 권한 설정 대기')
        config=json.loads(config_path.read_text(encoding='utf-8'))
        local=load_local(ROOT)
        require_profile(local,config['profile'])
        if args.provider not in local['enabled_data_adapters']: raise AdapterError('PC별 공급자 권한 설정 대기')
        reader=Reader(config['profile'],config['permissions'])
        params=json.loads(args.params.read_text(encoding='utf-8'))
        if any(k.lower() in ('token','authorization','appkey','secretkey','crtfc_key','password') for k in params): raise AdapterError('비밀값은 환경변수만 사용')
        result=getattr(reader,args.provider)(args.operation,params)
        record=dict(provider=args.provider,operation=args.operation,profile=config['profile'],fetched_at=datetime.now(timezone.utc).isoformat(),status='staging_not_normalized',records=result)
        folder=local['data_dir']/config['profile']/'live'/'staging'; folder.mkdir(parents=True,exist_ok=True)
        dest=folder/(digest(record)+'.json')
        dest.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        print('조회 응답 비공개 staging 저장 완료. 단위·기간·계정 매핑 검증 후 별도 스냅샷 적재 필요.')
    except (AdapterError,ValueError,KeyError,OSError):
        p.exit(1,'조회 미완료: 인증·권한·요청 설정 또는 공급자 응답 확인 필요. 가상 자료로 전환하지 않았습니다.\n')
