"""Private GitHub holdings sync. CLI credentials stay on each PC; writes use blob SHA."""
import base64
import json
import os
import re
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

LIMIT=900*1024

class SyncError(Exception):
    pass

def contract(root, **payload):
    try:
        run=subprocess.run(['node',str(Path(root)/'tools/holdings_sync_check.js')],input=json.dumps(payload,ensure_ascii=False,allow_nan=False),
            capture_output=True,text=True,encoding='utf-8',timeout=12)
        if run.returncode:raise SyncError('보유 입력 형식 또는 병합 결과를 확인하세요.')
        return json.loads(run.stdout)
    except (OSError,subprocess.TimeoutExpired,ValueError) as error:
        raise SyncError('보유 저장 검사에 실패했습니다. 입력 파일로 먼저 보관하세요.') from error

class GitHubStorage:
    def __init__(self,repository,*,run=None):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*/[A-Za-z0-9][A-Za-z0-9_.-]*',repository):raise SyncError('동기화 저장소 설정을 확인하세요.')
        self.repository=repository;self.runner=run or subprocess.run
        self.gh=shutil.which('gh') or 'gh'

    def api(self,path,body=None,missing=False):
        args=[self.gh,'api',path,'-H','Accept: application/vnd.github+json','-H','X-GitHub-Api-Version: 2022-11-28']
        if body is not None:args+=['--method','PUT','--input','-']
        try:
            r=self.runner(args,input=json.dumps(body,ensure_ascii=False) if body is not None else None,capture_output=True,text=True,encoding='utf-8',timeout=12)
        except (OSError,subprocess.TimeoutExpired) as e:raise SyncError('GitHub 연결 대기 · 이 PC의 로그인과 네트워크를 확인하세요.') from e
        if r.returncode:
            if 'HTTP 409' in r.stderr or 'HTTP 422' in r.stderr:raise SyncError('REMOTE_CHANGED')
            if missing and 'HTTP 404' in r.stderr:return None
            raise SyncError('GitHub 연결 대기 · 이 PC의 로그인과 저장소 권한을 확인하세요.')
        try:return json.loads(r.stdout)
        except ValueError as e:raise SyncError('GitHub 응답 형식을 확인하세요.') from e

    def verify_private(self):
        meta=self.api('repos/'+self.repository)
        if meta.get('private') is not True or meta.get('full_name','').lower()!=self.repository.lower() or not meta.get('permissions',{}).get('push'):
            raise SyncError('비공개 저장소와 쓰기 권한 확인 필요 · 보유내역을 전송하지 않았습니다.')

    def read(self):
        self.verify_private()
        record=self.api('repos/'+self.repository+'/contents/holdings.json',missing=True)
        if record is None:return None,None
        if record.get('type')!='file' or record.get('encoding')!='base64' or record.get('size',LIMIT+1)>LIMIT or not re.fullmatch('[a-f0-9]{40}',record.get('sha','')):
            raise SyncError('보유 저장 파일 형식 또는 크기를 확인하세요.')
        try:
            raw=base64.b64decode(record['content']);envelope=json.loads(raw)
            if len(raw)>LIMIT or envelope.get('kind')!='investment-holdings-sync' or envelope.get('version')!=1:raise ValueError()
            return envelope['state'],record['sha']
        except (ValueError,KeyError) as e:raise SyncError('보유 저장 파일을 읽지 못했습니다. 기존 입력을 유지합니다.') from e

    def write(self,state,sha):
        self.verify_private()
        raw=json.dumps(dict(kind='investment-holdings-sync',version=1,updated_at=datetime.now(timezone.utc).isoformat(),state=state),ensure_ascii=False,allow_nan=False).encode()
        if len(raw)>LIMIT:raise SyncError('동기화 입력은 900KB 이하여야 합니다. 입력 파일로 보관하세요.')
        payload=dict(message='Update private holdings input',content=base64.b64encode(raw).decode())
        if sha:payload['sha']=sha
        result=self.api('repos/'+self.repository+'/contents/holdings.json',payload)
        return result['content']['sha']

class HoldingsService:
    def __init__(self,root,backend,cache):
        self.root=Path(root);self.backend=backend;self.cache=Path(cache);self.lock=threading.RLock()
        self.record=None
        if self.cache.exists():
            try:
                self.record=json.loads(self.cache.read_text(encoding='utf-8'))
                for key in ['state','base']:
                    if self.record.get(key) is not None:contract(self.root,operation='validate',state=self.record[key])
            except (ValueError,SyncError) as e:raise SyncError('이 PC의 보유 저장 파일을 확인하세요. 파일을 덮어쓰지 않았습니다.') from e

    def save(self,record):
        self.cache.parent.mkdir(parents=True,exist_ok=True)
        temp=self.cache.with_suffix('.tmp')
        try:
            with temp.open('w',encoding='utf-8') as f:
                json.dump(record,f,ensure_ascii=False,allow_nan=False);f.flush();os.fsync(f.fileno())
            os.replace(temp,self.cache)
        except OSError as e:raise SyncError('이 PC의 보유 저장에 실패했습니다. 입력 파일로 먼저 보관하세요.') from e
        self.record=record

    def poll(self):
        with self.lock:
            if self.record and self.record.get('pending'):
                return self.submit(self.record['state'],self.record.get('base'))
            try:
                state,sha=self.backend.read()
                if state is not None:contract(self.root,operation='validate',state=state)
                elif (self.record or {}).get('state') is not None:raise SyncError('원격 보유 파일 확인 필요 · 이 PC의 입력을 유지합니다.')
                self.save(dict(state=state,base=state,pending=False,revision=sha))
                return dict(status='synced',state=state,revision=sha)
            except SyncError as e:
                return dict(status='offline',state=(self.record or {}).get('state'),message=str(e),local_saved=(self.record or {}).get('state') is not None)

    def submit(self,state,base):
        contract(self.root,operation='validate',state=state)
        if base is not None:contract(self.root,operation='validate',state=base)
        with self.lock:
            self.save(dict(state=state,base=base,pending=True))
            try:
                for _ in range(3):
                    remote,sha=self.backend.read()
                    if remote is not None:contract(self.root,operation='validate',state=remote)
                    result=contract(self.root,operation='merge',base=base,local=state,remote=remote)
                    if result['conflicts']:
                        return dict(status='conflict',state=state,remote=remote,base=base,conflicts=result['conflicts'],local_saved=True)
                    merged=result['state']
                    if remote==merged:
                        self.save(dict(state=merged,base=merged,pending=False,revision=sha))
                        return dict(status='synced',state=merged,revision=sha)
                    try:revision=self.backend.write(merged,sha)
                    except SyncError as e:
                        if str(e)=='REMOTE_CHANGED':continue
                        raise
                    self.save(dict(state=merged,base=merged,pending=False,revision=revision))
                    return dict(status='synced',state=merged,revision=revision)
                raise SyncError('다른 PC의 변경을 확인 중입니다. 잠시 후 다시 동기화합니다.')
            except SyncError as e:return dict(status='offline',state=state,message=str(e),local_saved=True)

def load_service(root):
    path=Path(root)/'config/holdings-sync.json'
    if not path.exists():return None
    cfg=json.loads(path.read_text(encoding='utf-8'))
    if cfg.get('enabled') is not True:return None
    return HoldingsService(root,GitHubStorage(cfg['repository']),Path(root)/'.local/holdings-sync/cache.json')
