"""Selected-company public headlines only. Bounded TTL cache; no article analysis."""
from datetime import datetime
from html import unescape
import json,re,threading,time
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
import requests
from .local_config import load_local

KST=ZoneInfo('Asia/Seoul')
TTL=600
_locks={}
_guard=threading.Lock()

def parse(payload,code,kind,now):
    if kind=='news':
        if not isinstance(payload,dict) or not isinstance(payload.get('clusters'),list):raise ValueError('news_schema')
        clusters=payload['clusters']
        if len(clusters)>100:raise ValueError('news_size')
        records=[]
        for cluster in clusters:
            if not isinstance(cluster,dict) or not isinstance(cluster.get('items'),list):raise ValueError('news_cluster')
            if cluster['items']:records.append(cluster['items'][0])
    else:
        if not isinstance(payload,list) or len(payload)>100:raise ValueError('disclosure_schema')
        records=payload
    result={}
    for item in records:
        if not isinstance(item,dict):raise ValueError('item_schema')
        title=item.get('title')
        if not isinstance(title,str) or not title.strip() or len(title)>1000:raise ValueError('title')
        if kind=='news':
            office,article=item.get('officeId'),item.get('articleId')
            if not re.fullmatch(r'\d{3}',str(office)) or not re.fullmatch(r'\d{6,15}',str(article)):raise ValueError('article_identity')
            stamp=datetime.strptime(item['datetime'],'%Y%m%d%H%M').replace(tzinfo=KST)
            if stamp>now:continue
            source=item.get('officeName')
            if not isinstance(source,str) or not source.strip() or len(source)>200:raise ValueError('publisher')
            url=f'https://n.news.naver.com/article/{office}/{article}'
            published=stamp.isoformat();display=stamp.strftime('%Y-%m-%d %H:%M')+' KST'
        else:
            if item.get('itemcode')!=code or not re.fullmatch(r'\d{1,20}',str(item.get('no'))):raise ValueError('disclosure_identity')
            stamp=datetime.fromisoformat(item['datetime'])
            if stamp.date()>now.date():continue
            # This source does not specify a zone for naive timestamps. Preserve that limit.
            published=stamp.isoformat();display=stamp.strftime('%Y-%m-%d %H:%M')+(' · 시간대 미명시' if stamp.tzinfo is None else '')
            source='네이버 공시'+(' · '+item['comment'] if isinstance(item.get('comment'),str) else '')
            url=f'https://stock.naver.com/domestic/stock/{code}/notice/{item["no"]}'
        result[url]=dict(code=code,kind=kind,title=unescape(title.strip()),source=source,url=url,
                         published_on=stamp.date().isoformat(),published_at=published,published_display=display)
    return sorted(result.values(),key=lambda x:x['published_at'],reverse=True)[:20]

def fetch(code,kind,now):
    params=dict(itemCode=code,pageSize=20,**({'page':1} if kind=='news' else {'startIdx':0}))
    endpoint='https://stock.naver.com/api/domestic/detail/'+('news' if kind=='news' else 'notice')
    with requests.get(endpoint,params=params,timeout=(5,12),stream=True,allow_redirects=False) as response:
        response.raise_for_status()
        if response.status_code!=200:raise ValueError('response_status')
        chunks=[];size=0
        for chunk in response.iter_content(65536):
            size+=len(chunk)
            if size>10*1024*1024:raise ValueError('response_size')
            chunks.append(chunk)
    return parse(json.loads(b''.join(chunks)),code,kind,now)

def view(root,code,*,read_only=False,now=None,fetcher=fetch):
    if not isinstance(code,str) or not re.fullmatch(r'\d{6}',code):raise ValueError('code')
    now=now or datetime.now(KST)
    if now.tzinfo is None:raise ValueError('timezone')
    now=now.astimezone(KST)
    cfg=load_local(root);folder=cfg['data_dir']/cfg['profile']/'market-expansion'
    universe=json.loads((folder/'universe.json').read_text(encoding='utf-8'))
    row=next((x for x in universe.get('companies',[]) if x.get('code')==code),None)
    if not row:raise ValueError('unknown_company')
    cache=Path(root)/'.local'/'company-events';path=cache/(code+'.json')
    with _guard:lock=_locks.setdefault(str(path.resolve()),threading.Lock())
    with lock:
        try:
            saved=json.loads(path.read_text(encoding='utf-8'))
            if saved.get('code')!=code or saved.get('name')!=row['name']:saved={}
        except (OSError,ValueError,TypeError):saved={}
        result=dict(code=code,name=row['name'],checked_at=now.isoformat(),groups={})
        for kind in ('news','disclosure'):
            old=saved.get('groups',{}).get(kind,{})
            try:age=(now-datetime.fromisoformat(old['fetched_at'])).total_seconds()
            except (ValueError,KeyError,TypeError):age=None
            try:attempt_age=(now-datetime.fromisoformat(old['checked_at'])).total_seconds()
            except (ValueError,KeyError,TypeError):attempt_age=None
            if age is not None and 0<=age<TTL:
                group=dict(old,status='cached')
            elif read_only:
                group=dict(old,status='stale' if old.get('items') else 'unavailable')
            elif old.get('status') in ('stale','unavailable') and attempt_age is not None and 0<=attempt_age<60:
                group=old
            else:
                try:
                    items=fetcher(code,kind,now)
                    group=dict(status='complete',items=items,fetched_at=now.isoformat(),checked_at=now.isoformat())
                except (requests.RequestException,OSError,ValueError,KeyError,TypeError,OverflowError):
                    group=dict(old,status='stale' if old.get('items') else 'unavailable',checked_at=now.isoformat())
            result['groups'][kind]=group
        if not read_only:
            cache.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.'+uuid4().hex+'.tmp')
            try:temp.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');temp.replace(path)
            finally:temp.unlink(missing_ok=True)
        return result
