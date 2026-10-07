"""Bounded on-demand public DART statements, separate from personal inputs."""
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock, Thread
from zoneinfo import ZoneInfo
import json,re,time
from uuid import uuid4
from html import unescape
import requests
from .local_config import load_local
from .market_discovery import read_market_cache as load_market_cache,discovery_candidate
from .market_refresh import write_json
from .dart_statements import Tables, load_bundle, PARSER_VERSION
from .financial_update_policy import decide_update
_COLLECTION_LOCK=Lock()


def acquire_lock(path):
    """OS releases this lock after a crash; the marker file may remain."""
    stream=path.open('a+b')
    try:
        if stream.seek(0,2)==0:stream.write(b'0');stream.flush()
        stream.seek(0)
        import os
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        return stream
    except OSError:
        stream.close();raise ValueError('다른 실행의 재무 수집 확인 필요') from None

def folder(root):
    cfg=load_local(root)
    return cfg['data_dir']/cfg['profile']/'company-financials'

def resolve_company(session,code,name):
    response=session.post('https://dart.fss.or.kr/corp/searchCorp.ax',data={'textCrpNm':code},timeout=(5,20))
    response.raise_for_status()
    if len(response.content)>1024*1024:raise ValueError('기업 검색 크기 초과')
    text=response.content.decode('utf-8')
    parser=Tables();parser.feed(text)
    if not any(code in row for table in parser.tables for row in table):
        # New alphanumeric tickers may not be indexed by code in public search.
        # A name search is usable ONLY when its returned row still proves that exact ticker.
        response=session.post('https://dart.fss.or.kr/corp/searchCorp.ax',data={'textCrpNm':name},timeout=(5,20))
        response.raise_for_status()
        if len(response.content)>1024*1024:raise ValueError('기업 검색 크기 초과')
        text=response.content.decode('utf-8');parser=Tables();parser.feed(text)
        if not any(code in row for table in parser.tables for row in table):raise ValueError('DART 종목 식별 불일치')
    codes=re.findall(r"name=['\"]hiddenCikCD\d+['\"]\s+value=['\"](\d{8})",text)
    names=re.findall(r"name=['\"]hiddenCikNM\d+['\"]\s+value=['\"]([^'\"]+)",text)
    if len(codes)!=1 or len(names)!=1:raise ValueError('DART 기업 식별 미확인')
    return codes[0],unescape(names[0])

def collect_company(root,row,cutoff,progress=lambda _:None, *, force=False, extra_targets=()):
    with _COLLECTION_LOCK:
        dest=folder(root);dest.mkdir(parents=True,exist_ok=True)
        lease=acquire_lock(dest/'collection.lock')
        stamp=dest/(row['code']+'.status.json')
        now=lambda:datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds')
        try:
            decision=_collect_company(root,row,cutoff,progress,force=force,extra_targets=extra_targets)
            write_json(stamp,dict(status='partial' if decision.get('failed_reports') else 'ready',checked_at=now()))
            return decision
        except Exception:
            write_json(stamp,dict(status='failed',checked_at=now()))
            raise
        finally:lease.close()


def _collect_company(root,row,cutoff,progress=lambda _:None, *, force=False, extra_targets=()):
    inventory=folder(root)/'fiscal-inventory'/(row['code']+'.json')
    if inventory.is_file():return _collect_inventory(root,row,cutoff,inventory,progress,force=force)
    from tools.company_statements import collect
    cache=folder(root)/'sources';cache.mkdir(parents=True,exist_ok=True)
    year=int(cutoff[:4]);month=int(cutoff[5:7])
    # Filing availability is verified from receipts by load_bundle, not assumed.
    latest_quarter=0 if month<5 else 1 if month<8 else 2 if month<11 else 3
    targets=[(year-1,q) for q in range(1,5) if q<4 or month>=4]+[(year,q) for q in range(1,latest_quarter+1)]
    targets=sorted(set(targets)|set(extra_targets))
    records=[];errors=[]
    with requests.Session() as session:
        session.headers['User-Agent']='INVESTMENT public financial review'
        identity=resolve_company(session,row['code'],row['name'])
        for y,q in targets:
            cached=(cache/f"{row['code']}-CFS-{y}q{q}.html").is_file() and (cache/f"{row['code']}-CFS-{y}q{q}.json").is_file() and not force
            try:
                record=collect(session,row['code'],'CFS',y,q,cache,'public',identity=identity,market=row['market'],force=force,display_name=row['name'])
                if record['available_at']<=cutoff:records.append(record)
            except (ValueError,KeyError,AttributeError,OSError):errors.append(dict(year=y,quarter=q))
            progress(dict(completed=len(records)+len(errors),total=len(targets)))
            if not cached:time.sleep(.2)
        cfs_errors=list(errors)
        if not records:
            errors=[]
            for y,q in targets:
                cached=(cache/f"{row['code']}-OFS-{y}q{q}.html").is_file() and (cache/f"{row['code']}-OFS-{y}q{q}.json").is_file() and not force
                try:
                    record=collect(session,row['code'],'OFS',y,q,cache,'public',identity=identity,market=row['market'],force=force,display_name=row['name'])
                    if record['available_at']<=cutoff:records.append(record)
                except (ValueError,KeyError,AttributeError,OSError):errors.append(dict(year=y,quarter=q,basis='OFS'))
                progress(dict(completed=len(records)+len(errors),total=len(targets)))
                if not cached:time.sleep(.2)
    bundle=dict(schema='dart-public-statements-1',unit='KRW',companies={row['code']:dict(reports=records)},errors=errors,
                cfs_unverified=bool(records and not any(r['basis']=='CFS' for r in records)),cfs_attempt_errors=cfs_errors,
                retrieved_on=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat())
    path=folder(root)/(row['code']+'.json')
    # Do not replace a previous complete cache with a partial attempt.
    if errors:
        write_json(path.with_suffix('.incomplete.json'),bundle)
    else:path.with_suffix('.incomplete.json').unlink(missing_ok=True)
    if not records:
        raise ValueError('DART 재무자료 일부 조회·검증 대기')
    previous=json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None
    if previous:
        prior=previous['companies'].get(row['code'],{}).get('reports',[])
        observed={(r['basis'],r['year'],r['quarter']):r for r in records}
        for record in prior:observed.setdefault((record['basis'],record['year'],record['quarter']),record)
        bundle['companies'][row['code']]['reports']=list(observed.values())
    decision=decide_update(previous,bundle)
    if previous and any(r.get('parser_version',0)<PARSER_VERSION for r in previous['companies'].get(row['code'],{}).get('reports',[])):
        old={(r['basis'],r['year'],r['quarter']):r for r in previous['companies'][row['code']]['reports']}
        reparsed=[r for r in records if r.get('parser_version')==PARSER_VERSION and old.get((r['basis'],r['year'],r['quarter']),{}).get('parser_version',0)<PARSER_VERSION and r.get('sha256') and old.get((r['basis'],r['year'],r['quarter']),{}).get('sha256')==r['sha256']]
        if reparsed and decision['action'] in ('review','defer','unchanged') and decision.get('reason')!='financial_contract_changed':
            # Parser repairs are distinct from new provider corrections (<7% remains deferred).
            corrected=dict(old)
            corrected.update({(r['basis'],r['year'],r['quarter']):r for r in reparsed})
            bundle['companies'][row['code']]['reports']=list(corrected.values())
            decision=dict(action='update',reason='same_source_parser_revalidation',changes=[])
    decision['failed_reports']=len(errors)
    write_json(path.with_suffix('.observed.json'),dict(bundle,update_decision=decision))
    if decision['action'] in ('update','unchanged'):write_json(path,bundle)
    return decision


def _collect_inventory(root,row,cutoff,inventory,progress=lambda _:None, *, force=False):
    from tools.company_statements import collect_receipt
    from .fiscal_contract import validate_contract
    data=json.loads(Path(inventory).read_text(encoding='utf-8'))
    if data.get('schema')!='dart-fiscal-inventory-1' or (data.get('code'),data.get('name'),data.get('market'))!=(row['code'],row['name'],row['market']):raise ValueError('검증 원문 목록 기업 식별 불일치')
    entries=data.get('reports',[])
    if not isinstance(entries,list) or not entries:raise ValueError('검증 원문 목록 미확보')
    checked=[];identities=set()
    for entry in entries:
        c=validate_contract(entry['period_contract'],year=entry['year'],quarter=entry['quarter'])
        key=(entry['basis'],c['fiscal_year'],c['fiscal_quarter'],c['currency'],c['calendar_segment'])
        if key in identities:raise ValueError('검증 원문 목록 기간 중복')
        identities.add(key)
        if c['source']['available_at']<=cutoff and c['period_end']<=cutoff:checked.append(entry)
    cache=folder(root)/'sources';records=[];errors=[]
    with requests.Session() as session:
        session.headers['User-Agent']='INVESTMENT public fiscal statement review'
        for entry in checked:
            try:records.append(collect_receipt(session,entry,cache,code=row['code'],name=row['name'],market=row['market'],force=force))
            except (ValueError,KeyError,AttributeError,OSError):errors.append(dict(basis=entry['basis'],year=entry['year'],quarter=entry['quarter'],reason='verified_receipt_validation_pending'))
            progress(dict(completed=len(records)+len(errors),total=len(checked)))
    bundle=dict(schema='dart-native-statements-1',unit='native',companies={row['code']:dict(reports=records)},errors=errors,
        collection_route='verified_receipt_inventory',retrieved_on=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat(),
        cfs_unverified=bool(records and not any(r['basis']=='CFS' for r in records)))
    path=folder(root)/(row['code']+'.json')
    if errors:write_json(path.with_suffix('.incomplete.json'),bundle)
    if not records:raise ValueError('원문 목록 조회·검증 대기; 이전 유효 자료 보존')
    previous=json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None
    if previous:
        prior=previous.get('companies',{}).get(row['code'],{}).get('reports',[])
        observed={(r['basis'],r['year'],r['quarter']):r for r in records}
        for r in prior:observed.setdefault((r['basis'],r['year'],r['quarter']),r)
        bundle['companies'][row['code']]['reports']=list(observed.values())
    decision=decide_update(previous,bundle);decision['failed_reports']=len(errors)
    write_json(path.with_suffix('.observed.json'),dict(bundle,update_decision=decision))
    if decision['action'] in ('update','unchanged'):write_json(path,bundle)
    if not errors:path.with_suffix('.incomplete.json').unlink(missing_ok=True)
    return decision

def load_cached(root,snapshot,rows, *, as_of=None, cache=None):
    result={}
    identities={r.get('code'):r for r in rows}
    cache=cache if cache is not None else load_market_cache(root,snapshot)
    cutoff=as_of or (cache or {}).get('history',{}).get('calendar',{}).get('valid_through') or snapshot['meta']['price_date']
    for path in folder(root).glob('*.json'):
        code=path.stem;row=identities.get(code)
        if row and re.fullmatch(r'[0-9A-Z]{6}',code):
            scope=dict(meta=dict(snapshot['meta'],price_date=cutoff),companies=[row])
            result.update(load_bundle(path,scope))
    # Derived, revalidated native bundles live separately from the applied cache.
    # Reading this sidecar never rewrites an original public viewer or provider row.
    for path in (folder(root)/'native-derived').glob('*.json'):
        row=identities.get(path.stem)
        if not row or not re.fullmatch(r'[0-9A-Z]{6}',path.stem):continue
        scope=dict(meta=dict(snapshot['meta'],price_date=cutoff),companies=[row])
        derived=load_bundle(path,scope).get(path.stem)
        if not derived:continue
        if path.stem not in result:result[path.stem]=derived
        else:
            existing=result[path.stem];keys={(p['basis'],p['cadence'],p['period_end']) for p in existing['periods']}
            existing['periods'].extend(p for p in derived['periods'] if (p['basis'],p['cadence'],p['period_end']) not in keys)
            existing['native_financial']=derived.get('native_financial');existing['financial_completeness']=derived.get('financial_completeness')
    from .financial_health import collection_health
    dest=folder(root)
    for code,row in identities.items():
        if not re.fullmatch(r'[0-9A-Z]{6}',str(code)):continue
        health=collection_health(dest,code,result.get(code))
        if code in result:result[code]['collection_health']=health
        else:result[code]=dict(code=code,name=row['name'],market=row['market'],periods=[],notes=[],collection_health=health)
    return result

class CompanyFinancials:
    def __init__(self,root,collector=collect_company):
        self.root=Path(root);self.collector=collector;self.lock=Lock();self.jobs={}

    def poll(self,code):
        with self.lock:return dict(self.jobs.get(code,dict(status='idle',code=code)))

    def running(self):
        with self.lock:return any(j.get('status')=='running' for j in self.jobs.values())

    def start(self,code):
        if not re.fullmatch(r'[0-9A-Z]{6}',code):raise ValueError('종목코드 오류')
        cache=load_market_cache(self.root,{'meta':{'data_mode':'user_input'}})
        quotes=(cache or {}).get('quotes',{}).get('quotes',{})
        row=next((r for r in (cache or {}).get('universe',{}).get('companies',[]) if r.get('code')==code and discovery_candidate(r,quotes.get(code))),None)
        if row is None:raise ValueError('저장 후보에 없는 종목')
        now=datetime.now(ZoneInfo('Asia/Seoul'))
        cutoff=(cache or {}).get('history',{}).get('calendar',{}).get('valid_through') or now.date().isoformat()
        with self.lock:
            prior=self.jobs.get(code,{})
            if prior.get('status')=='running':return dict(prior)
            if prior.get('status')=='complete' and prior.get('checked_on')==now.date().isoformat():return dict(prior)
            stored=folder(self.root)/(code+'.json')
            derived=folder(self.root)/'native-derived'/(code+'.json')
            if stored.is_file() or derived.is_file():return dict(status='cached',code=code,cache_revision=str((stored if stored.is_file() else derived).stat().st_mtime_ns))
            if prior.get('status')=='failed' and time.monotonic()-prior.get('attempt',0)<3600:return dict(prior)
            if any(j.get('status')=='running' for j in self.jobs.values()):return dict(status='busy',code=code,message='다른 기업의 재무자료 조회 중')
            self.jobs[code]=dict(status='running',code=code,completed=0,total=0,attempt=time.monotonic())
            Thread(target=self.run,args=(row,cutoff),daemon=True).start()
            return dict(self.jobs[code])

    def run(self,row,cutoff):
        code=row['code']
        def update(info):
            with self.lock:self.jobs[code].update(info)
        try:
            decision=self.collector(self.root,row,datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat(),update)
            update(dict(status='complete',failed_reports=decision.get('failed_reports',0),checked_on=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat(),message='검증된 DART 연결 재무자료 저장 완료'))
        except Exception:
            update(dict(status='failed',message='공개 재무자료 조회·검증 대기 · 기존 자료 유지'))


def fetch_filings(day, *, session=None):
    """Read all public daily pages. Fail closed if counts/dates are incomplete."""
    session=session or requests.Session();result=[];total=None;pages=1
    for page in range(1,101):
        response=session.post('https://dart.fss.or.kr/dsac001/search.ax',data=dict(
            selectDate=day.replace('-',''),currentPage=str(page),maxResults='100',mdayCnt='0',sort='',series=''),timeout=(5,30))
        response.raise_for_status()
        if len(response.content)>2*1024*1024:raise ValueError('공시 목록 크기 초과')
        text=response.content.decode('utf-8')
        count=re.search(r'id="totalCnt"\s+value="(\d+)"',text)
        pagination=re.search(r'pageInfo[^>]*>\[(\d+)/(\d+)\]',text)
        if count and int(count[1])==0 and page==1 and '검색된 자료가 없습니다' in text and 'rcpNo=' not in text:return []
        if not count or not pagination:raise ValueError('공시 페이지 확인 실패')
        if total is not None and total!=int(count[1]):raise ValueError('조회 중 공시 목록 변경 · 재시도')
        total=int(count[1]);pages=int(pagination[2])
        if int(pagination[1])!=page or pages>100:raise ValueError('공시 페이지 누락')
        parsed=[]
        for block in re.findall(r'<tr\b[^>]*>(.*?)</tr>',text,re.S|re.I):
            company=re.search(r'openCorpInfoNew\(\'(\d{8})\'.*?>(.*?)</a>',block,re.S)
            report=re.search(r'<a\b[^>]*href="/dsaf001/main.do\?rcpNo=(\d{14})"[^>]*>(.*?)</a>',block,re.S)
            if not report:continue
            # Attachment additions can point to the original receipt/date.
            if not company or report[1][:8]>day.replace('-',''):raise ValueError('공시 날짜·기업 확인 실패')
            clean=lambda s:unescape(re.sub('<[^>]+>','',s)).strip()
            parsed.append(dict(corp=company[1],name=clean(company[2]),receipt=report[1],title=clean(report[2])))
        result.extend(parsed)
        if page>=pages:break
        time.sleep(.2)
    if len(result)!=total:raise ValueError('공시 건수 불일치')
    return result


class FinancialMonitor:
    """Daily filing scan plus paced initial coverage; no OS registration."""
    def __init__(self,root,service,*,filings=fetch_filings,collector=collect_company,track_completion=False):
        self.root=Path(root);self.service=service;self.filings=filings;self.collector=collector
        self.track_completion=track_completion
        self.lock=Lock();self.state=dict(status='idle');self.last_attempt=0

    def poll(self):
        bulk=self.completion_state()
        if bulk:return bulk
        with self.lock:return dict(self.state)

    def completion_state(self):
        if not self.track_completion:return None
        try:
            path=folder(self.root)/'completion-status.json'
            if not path.exists():return None
            data=json.loads(path.read_text(encoding='utf-8'))
            if data.get('checked_on')!=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat():return None
            if data.get('status')=='complete' and time.time()-data.get('completed_at',0)>3600:return None
            result={k:data.get(k) for k in ('status','checked_on','total','completed','updated','failed','partial','revision')}
            result['failure_label']='조회·검증 대기'
            return result
        except (OSError,ValueError):return None

    def update(self,**info):
        with self.lock:self.state.update(info)

    def ensure_due(self):
        today=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
        bulk=self.completion_state()
        if bulk:return bulk
        with self.lock:
            if self.state.get('status')=='running' or self.last_attempt and time.monotonic()-self.last_attempt<3600:return dict(self.state)
            stamp=folder(self.root)/'monitor-status.json'
            if stamp.is_file():
                try:
                    saved=json.loads(stamp.read_text(encoding='utf-8'))
                    if saved.get('checked_on')==today and not saved.get('failed'):
                        self.state.update(saved);return dict(self.state)
                except (OSError,ValueError):pass
            self.last_attempt=time.monotonic();self.state.update(status='running',completed=0,total=0)
            Thread(target=self.run,daemon=True).start();return dict(self.state)

    def run(self):
        lease=None
        try:
            dest=folder(self.root);dest.mkdir(parents=True,exist_ok=True)
            lease=acquire_lock(dest/'monitor.lock')
            today=datetime.now(ZoneInfo('Asia/Seoul')).date()
            stamp=dest/'monitor-status.json'
            saved=json.loads(stamp.read_text(encoding='utf-8')) if stamp.is_file() else {}
            start=datetime.fromisoformat(saved.get('checked_on',today.isoformat())).date()
            # Daily pages cover gaps when the app was closed, including corrections.
            cache=load_market_cache(self.root,{'meta':{'data_mode':'user_input'}})
            quotes=(cache or {}).get('quotes',{}).get('quotes',{})
            rows=[r for r in (cache or {}).get('universe',{}).get('companies',[]) if discovery_candidate(r,quotes.get(r['code']))]
            if not rows:raise ValueError('기업 목록 연결 대기')
            names={r['name']:r for r in rows};changed={}
            # Public corporate names can differ from trading names (e.g. 현대차).
            corp_rows={}
            for path in (dest/'sources').glob('*-CFS-*.json'):
                try:
                    evidence=json.loads(path.read_text(encoding='utf-8'))
                    if evidence.get('corp_code'):
                        candidate=next((r for r in rows if r['code']==evidence.get('code')),None)
                        if candidate:corp_rows[evidence['corp_code']]=candidate
                except (OSError,ValueError):pass
            while start<=today:
                for report in self.filings(start.isoformat()):
                    if not any(t in report['title'] for t in ('분기보고서','반기보고서','사업보고서')):continue
                    row=corp_rows.get(report.get('corp')) or names.get(report['name'])
                    if row:
                        targets=changed.setdefault(row['code'],set())
                        period=re.search(r'\((20\d{2})\.(03|06|09|12)\)',report['title'])
                        if period:targets.add((int(period[1]),int(period[2])//3))
                start+=timedelta(days=1)
            # Missing data is bootstrapped once; existing data only for changed filings.
            todo=[r for r in rows if r['code'] in changed or not (dest/(r['code']+'.json')).is_file() or (dest/(r['code']+'.incomplete.json')).is_file()]
            todo.sort(key=lambda row:row['code'] not in changed)
            self.update(total=len(todo),completed=0,updated=0,deferred=0,failed=0,partial=0)
            for index,row in enumerate(todo):
                # On-demand viewing has priority over the background pass.
                while self.service.running():time.sleep(1)
                try:
                    decision=self.collector(self.root,row,today.isoformat(),force=row['code'] in changed,
                                            extra_targets=changed.get(row['code'],()))
                    if decision.get('failed_reports'):self.update(partial=self.poll()['partial']+1)
                    field='updated' if decision['action']=='update' else 'deferred'
                except Exception:field='failed'
                self.update(**{field:self.poll().get(field,0)+1},completed=index+1)
                if field=='updated':
                    revision=uuid4().hex
                    versions=dict(self.poll().get('versions',{}));versions[row['code']]=revision
                    self.update(revision=revision,versions=versions)
                time.sleep(.3)
            result=dict(self.poll(),status='complete',checked_on=today.isoformat(),
                        message='분기 재무·일간 공시 확인 완료 · 7% 이상 수정 반영')
            write_json(stamp,result);self.update(**result)
        except Exception:
            self.update(status='failed',message='재무 공시 조회·검증 대기 · 기존 자료 유지')
        finally:
            if lease is not None:lease.close()
