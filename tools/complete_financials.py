"""Explicit, resumable repair and completion of private public-statement caches."""
import json,sys,hashlib,time
import requests
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor,as_completed
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from investment.company_financials import folder,acquire_lock,collect_company,_collect_company
from investment.live_dashboard import saved_data
from investment.market_discovery import load_market_cache,discovery_candidate
from investment.dart_statements import parse_viewer,valid_report
from investment.market_refresh import write_json

def repair_saved(dest):
    repaired={};failures=[]
    lease=acquire_lock(dest/'collection.lock')
    try:
        for p in (dest/'sources').glob('*-*-*.json'):
            html=p.with_suffix('.html')
            if not html.exists():continue
            old=json.loads(p.read_text(encoding='utf-8'));payload=html.read_bytes()
            if hashlib.sha256(payload).hexdigest()!=old.get('sha256'):failures.append(dict(file=p.name,reason='source_hash'));continue
            try:
                keys={k:old[k] for k in ('code','name','market','basis','year','quarter','receipt','url')}
                # A version stamp cannot validate values produced by an older parser.
                # Re-read the original HTML, including attribution and account context.
                new=parse_viewer(payload.decode('utf-8'),**keys)
                if not valid_report(new):raise ValueError('원계정 검증')
                new.update(sha256=old['sha256'],corp_code=old.get('corp_code'),legal_name=old.get('legal_name'))
                repaired[(new['code'],new['basis'],new['year'],new['quarter'])]=new
                if new!=old:write_json(p,new)
            except (ValueError,KeyError,TypeError):failures.append(dict(file=p.name,reason='parser_validation'))
        count=0
        for p in dest.glob('*.json'):
            if not p.stem.isalnum() or len(p.stem)!=6:continue
            bundle=json.loads(p.read_text(encoding='utf-8'));changed=False
            for code,company in bundle.get('companies',{}).items():
                for i,old in enumerate(company.get('reports',[])):
                    new=repaired.get((code,old['basis'],old['year'],old['quarter']))
                    if new and old.get('sha256')==new['sha256'] and new!=old:company['reports'][i]=new;changed=True
            if changed:
                bundle['reparsed_on']=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat();write_json(p,bundle);count+=1
        return dict(repaired_companies=count,validated_sources=len(repaired),revalidation_failures=failures)
    finally:lease.close()

def main(root):
    root=Path(root);dest=folder(root);dest.mkdir(parents=True,exist_ok=True)
    lease=acquire_lock(dest/'monitor.lock')
    today=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat();status=dest/'completion-status.json'
    try:
        write_json(status,dict(status='running',checked_on=today,total=0,completed=0,updated=0,failed=0,partial=0))
        repair=repair_saved(dest);print('REPAIR',repair['repaired_companies'],repair['validated_sources'],'failed',len(repair['revalidation_failures']),flush=True)
        snapshot=saved_data(root)['snapshot'];cache=load_market_cache(root,snapshot);quotes=cache['quotes']['quotes']
        rows=[r for r in cache['universe']['companies'] if discovery_candidate(r,quotes.get(r['code']))]
        rows.sort(key=lambda r:-(quotes.get(r['code'],{}).get('market_cap_eok') or r['metrics'].get('market_cap_eok') or 0))
        year=int(today[:4]);month=int(today[5:7]);q=0 if month<5 else 1 if month<8 else 2 if month<11 else 3
        expected={(year-1,i) for i in range(1,5)}|{(year,i) for i in range(1,q+1)}
        todo=[]
        for r in rows:
            p=dest/(r['code']+'.json')
            reports=json.loads(p.read_text(encoding='utf-8')).get('companies',{}).get(r['code'],{}).get('reports',[]) if p.exists() else []
            existing={(x['year'],x['quarter']) for x in reports if x['basis']=='CFS'}
            if not expected<=existing:todo.append(r)
        state=dict(status='running',checked_on=today,total=len(todo),completed=0,updated=0,failed=0,partial=0,repair=repair,failures=[])
        write_json(status,state);print('TODO',len(todo),'ELIGIBLE',len(rows),flush=True)
        # One exclusive writer lease; two paced, independent company sessions.
        collection_lease=acquire_lock(dest/'collection.lock')
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                jobs={pool.submit(_collect_company,root,r,today):r for r in todo}
                for future in as_completed(jobs):
                    r=jobs[future]
                    try:
                        result=future.result()
                        state['updated']+=result['action']=='update';state['partial']+=bool(result.get('failed_reports'))
                    except Exception as error:
                        reason='public_connection_failed' if isinstance(error,requests.exceptions.RequestException) else 'public_statement_unavailable_or_validation_failed'
                        state['failed']+=1;state['failures'].append(dict(code=r['code'],name=r['name'],reason=reason))
                    state['completed']+=1;write_json(status,state)
                    if state['completed']%25==0:print('PROGRESS',state['completed'],state['total'],'updated',state['updated'],'failed',state['failed'],'partial',state['partial'],flush=True)
        finally:collection_lease.close()
        state['status']='complete';state['completed_at']=time.time();state['revision']=uuid4().hex;write_json(status,state);print('COMPLETE',state['completed'],'updated',state['updated'],'failed',state['failed'],'partial',state['partial'],flush=True)
        return state
    except Exception:
        failed=json.loads(status.read_text(encoding='utf-8')) if status.exists() else {}
        failed.update(status='failed',checked_on=today,completed_at=time.time())
        write_json(status,failed)
        raise
    finally:lease.close()

if __name__=='__main__':main(Path(__file__).resolve().parents[1])
