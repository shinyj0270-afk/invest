"""PC-local Goose drop folder; no downloads, model execution or OS scheduling."""
from contextlib import closing
from datetime import datetime
import hashlib,json,os,sqlite3,threading,time
from pathlib import Path
from .company_reports import EmbeddedJSON,LIMIT,KST,company,location,register
from .local_config import load_local


class ReportInbox:
    def __init__(self,root,*,read_only=False):
        self.root=Path(root);self.cfg=load_local(root);self.read_only=read_only
        configured=self.cfg.get('goose_report_inbox')
        self.folder=Path(configured).expanduser() if configured else Path.home()/'Downloads'/'Goose Reports'
        if not self.folder.is_absolute():self.folder=self.root/self.folder
        self.state_path=self.cfg['data_dir']/self.cfg['profile']/'user_input'/'report-inbox.json'
        self.lock=threading.RLock();self.stop_event=threading.Event();self.thread=None
        self.files={};self.observed={};self.error='';self.checked_at=None;self.paused=False
        try:
            saved=json.loads(self.state_path.read_text(encoding='utf-8'))
            if saved.get('folder')==str(self.folder) and isinstance(saved.get('files'),dict):self.files={k:v for k,v in saved['files'].items() if isinstance(k,str) and isinstance(v,dict)}
        except (OSError,ValueError,AttributeError):pass

    def view(self):
        with self.lock:
            return dict(folder=str(self.folder),enabled=not self.read_only and not self.paused,checked_at=self.checked_at,error=self.error,
                        files=sorted(self.files.values(),key=lambda x:x.get('checked_at',''),reverse=True)[:30])

    def save(self):
        content=json.dumps(dict(folder=str(self.folder),files=self.files),ensure_ascii=False)
        try:
            if self.state_path.read_text(encoding='utf-8')==content:return
        except FileNotFoundError:pass
        self.state_path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.state_path.with_suffix('.tmp')
        temp.write_text(content,encoding='utf-8')
        os.replace(temp,self.state_path)

    def import_file(self,path,raw):
        html=raw.decode('utf-8');parser=EmbeddedJSON();parser.feed(html);parser.close()
        report=parser.documents.get('report-input.json')
        if parser.invalid or not isinstance(report,dict):raise ValueError('종목 정보가 내장된 Goose HTML이 필요합니다. 수동 등록을 이용하세요.')
        identity=report.get('company')
        if not isinstance(identity,dict):raise ValueError('보고서 기업 정보가 없습니다.')
        code=identity.get('ticker');cfg,row=company(self.root,code)
        normalize=lambda x:''.join(x.split()).casefold() if isinstance(x,str) else ''
        if not normalize(identity.get('name')) or normalize(identity.get('name'))!=normalize(row['name']):raise ValueError('종목코드와 기업명이 일치하지 않습니다.')
        for doc in parser.documents.values():
            if doc.get('company',{}).get('ticker')!=code or doc.get('as_of')!=report.get('as_of'):raise ValueError('내장 자료의 종목·기준일이 일치하지 않습니다.')
        day=report.get('as_of')
        try:parsed=datetime.strptime(day,'%Y-%m-%d').date()
        except (TypeError,ValueError):raise ValueError('보고서 작성 기준일을 확인하세요.') from None
        if parsed.isoformat()!=day or parsed>datetime.now(KST).date():raise ValueError('보고서 작성 기준일을 확인하세요.')
        sha=hashlib.sha256(raw).hexdigest();dbpath=location(cfg)
        if dbpath.exists():
            canonical=lambda text:text.lstrip('\ufeff').replace('\r\n','\n').replace('\r','\n')
            normalized=canonical(html)
            with closing(sqlite3.connect(dbpath.resolve().as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
                for old in db.execute('SELECT id,title,html,sha256 FROM reports WHERE code=? AND name=? AND market=? ORDER BY created_at',(code,row['name'],row['market'])):
                    if old[3]==sha or canonical(old[2])==normalized:
                        return dict(status='duplicate',message='이미 등록된 같은 보고서',code=code,title=old[1],report_id=old[0])
        document=report.get('document');title=document.get('title') if isinstance(document,dict) else None
        if not isinstance(title,str) or not title.strip():title=f"{row['name']} · Goose · {day}"
        result=register(self.root,dict(code=code,title=title[:200],authored_on=day,source_label='Goose',source_urls=[],filename=path.name,html=html))
        return dict(status='duplicate' if result['duplicate'] else 'registered',message='이미 등록됨' if result['duplicate'] else '기업에 자동 등록 완료',code=code,title=title[:200],report_id=result['id'])

    def scan(self):
        if self.read_only:raise ValueError('읽기 전용에서는 폴더를 등록하지 않습니다.')
        with self.lock:
            if self.paused:return self.view()
            self.checked_at=datetime.now(KST).isoformat();self.error=''
            try:
                if self.cfg['profile'] not in ('work','home'):raise ValueError('PC 프로필 확인 필요')
                if self.folder.is_symlink():raise ValueError('바로가기 폴더는 사용할 수 없습니다.')
                self.folder.mkdir(parents=True,exist_ok=True)
                paths=[]
                with os.scandir(self.folder) as entries:
                    for entry in entries:
                        if len(paths)>=500:self.error='폴더당 최대500개를 확인합니다. 처리한 원본은 별도로 보관해 주세요.';break
                        if entry.name.lower().endswith(('.html','.htm')):paths.append(Path(entry.path))
                present={p.name for p in paths};self.files={k:v for k,v in self.files.items() if k in present};self.observed={k:v for k,v in self.observed.items() if k in present}
                count=0
                for path in paths:
                    stat=path.lstat();sig=[stat.st_size,stat.st_mtime_ns]
                    old=self.files.get(path.name,{})
                    if old.get('signature')==sig and old.get('status') in ('registered','duplicate','error'):continue
                    item=dict(filename=path.name,signature=sig,checked_at=self.checked_at,status='waiting',message='저장 완료 확인 중')
                    self.files[path.name]=item
                    if self.observed.get(path.name)!=sig or time.time()-stat.st_mtime<2:
                        self.observed[path.name]=sig;continue
                    if count>=20:continue
                    count+=1
                    try:
                        if path.is_symlink() or getattr(stat,'st_file_attributes',0)&1024 or path.resolve().parent!=self.folder.resolve():raise ValueError('바로가기 파일은 등록하지 않습니다.')
                        if not path.is_file() or not 0<stat.st_size<=LIMIT:raise ValueError('3MB 이하 HTML 파일이 필요합니다.')
                        with path.open('rb') as stream:raw=stream.read(LIMIT+1)
                        after=path.stat()
                        if [after.st_size,after.st_mtime_ns]!=sig or len(raw)!=stat.st_size:continue
                        item.update(self.import_file(path,raw))
                    except (ValueError,UnicodeError,KeyError,TypeError,AttributeError,RecursionError) as exc:item.update(status='error',message=str(exc)[:220])
                    except (OSError,sqlite3.Error):item.update(status='waiting',message='파일·저장소 연결 대기 · 다음 확인 때 재시도')
                self.save()
            except (OSError,ValueError,sqlite3.Error) as exc:self.error=str(exc)[:220]
            return self.view()

    def start(self):
        if self.read_only:return
        from .dashboard_build import source_fingerprint
        build=source_fingerprint(self.root)
        def run():
            while not self.stop_event.is_set():
                if source_fingerprint(self.root)!=build:
                    with self.lock:self.paused=True;self.error='새 코드 반영을 위한 안전 재시작 대기'
                    return
                self.scan()
                if self.stop_event.wait(5):return
        self.thread=threading.Thread(target=run,daemon=True,name='goose-report-inbox');self.thread.start()

    def pause(self):
        with self.lock:self.paused=True;self.stop_event.set()

    def stop(self):
        self.pause()
        if self.thread:self.thread.join(timeout=10)
