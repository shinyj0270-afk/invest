"""Local immutable external HTML reports. No remote fetching or model execution."""
from contextlib import closing
from datetime import datetime
from html import escape
from html.parser import HTMLParser
import base64,binascii,hashlib,json,re,sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo
from .local_config import load_local
from .research_library import url as public_url

LIMIT=3*1024*1024
KST=ZoneInfo('Asia/Seoul')

def company(root,code):
    if not isinstance(code,str) or not re.fullmatch(r'\d{6}',code):raise ValueError('6자리 종목코드를 확인하세요.')
    cfg=load_local(root)
    if cfg['profile'] not in ('work','home'):raise ValueError('PC 프로필을 확인하세요.')
    path=cfg['data_dir']/cfg['profile']/'market-expansion'/'universe.json'
    rows=json.loads(path.read_text(encoding='utf-8'))['companies']
    row=next((r for r in rows if r.get('code')==code),None)
    if not row:raise ValueError('저장된 기업을 선택하세요.')
    return cfg,row

def location(cfg):return cfg['data_dir']/cfg['profile']/'user_input'/'external-reports.sqlite3'

class EmbeddedJSON(HTMLParser):
    """Read only known bounded attachments; never execute HTML."""
    names={'report-input.json','source-ledger.json'}
    prefix='data:application/json;base64,'
    def __init__(self):super().__init__();self.documents={};self.invalid=False
    def handle_starttag(self,tag,attrs):
        a=dict(attrs);name=a.get('download');href=a.get('href') or ''
        if tag!='a' or name not in self.names:return
        if name in self.documents:self.invalid=True;return
        self.documents[name]=None
        if not href.startswith(self.prefix) or len(href)>2*1024*1024:self.invalid=True;return
        try:
            data=json.loads(base64.b64decode(href[len(self.prefix):],validate=True).decode('utf-8'))
            if not isinstance(data,dict):raise ValueError()
            self.documents[name]=data
        except (ValueError,UnicodeError,binascii.Error,RecursionError):self.invalid=True


def embedded(html,code):
    result=dict(review_status='unknown',review_label='검토 상태 미기재',embedded_sources=[],embedded_notice='')
    parser=EmbeddedJSON()
    try:parser.feed(html);parser.close()
    except (ValueError,RecursionError):parser.invalid=True
    if parser.invalid:
        result['embedded_notice']='내장 자료 형식 확인 필요';return result
    docs=parser.documents
    if not docs:return result
    if any(not isinstance(v.get('company'),dict) or v['company'].get('ticker')!=code for v in docs.values()):
        result['embedded_notice']='내장 자료 종목 불일치 · 출처와 상태 표시 보류';return result
    report=docs.get('report-input.json',{});ledger=docs.get('source-ledger.json')
    if ledger and report and ledger.get('as_of')!=report.get('as_of'):
        result['embedded_notice']='내장 자료 기준일 불일치 · 출처와 상태 표시 보류';return result
    labels={'draft':'초안','limited':'조사 한계 있음','verified':'검증본'}
    status=report.get('status')
    if isinstance(status,str) and status in labels:result.update(review_status=status,review_label='작성자 표기: '+labels[status])
    rows=(ledger if ledger is not None else report).get('sources',[])
    if not isinstance(rows,list) or len(rows)>200:
        result['embedded_notice']='내장 출처 형식·개수 확인 필요';return result
    seen=set();skipped=0
    def short(v,limit=300):return v[:limit] if isinstance(v,str) else ''
    for row in rows:
        if not isinstance(row,dict):skipped+=1;continue
        value=row.get('url')
        if value is None:continue
        try:
            if not isinstance(value,str) or len(value)>2000 or any(c.isspace() or ord(c)<32 or ord(c)==127 or c==chr(92) for c in value):raise ValueError()
            value=public_url(value)
        except ValueError:skipped+=1;continue
        if value in seen:continue
        seen.add(value)
        result['embedded_sources'].append(dict(url=value,title=short(row.get('title')) or value,publisher=short(row.get('publisher'),120),published_at=short(row.get('published_at'),50)))
    if skipped:result['embedded_notice']=f'주소·형식 확인이 필요한 출처 {skipped}개는 표시하지 않았습니다.'
    return result


def metadata(row):
    d=dict(row);d['source_urls']=json.loads(d['source_urls']);html=d.pop('html','')
    if hashlib.sha256(html.encode('utf-8')).hexdigest()!=d['sha256']:
        d.update(review_status='unknown',review_label='파일 확인 필요',embedded_sources=[],embedded_notice='원본 해시 불일치')
    else:d.update(embedded(html,d['code']))
    return d


def listing(root,code):
    cfg,row=company(root,code);path=location(cfg)
    if not path.exists():return dict(code=code,name=row['name'],reports=[])
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
        db.row_factory=sqlite3.Row
        records=db.execute('SELECT * FROM reports WHERE code=? AND name=? AND market=? ORDER BY authored_on DESC,created_at DESC LIMIT 50',(code,row['name'],row['market'])).fetchall()
    return dict(code=code,name=row['name'],reports=[metadata(x) for x in records])

def register(root,payload):
    if not isinstance(payload,dict) or set(payload)!={'code','title','authored_on','source_label','source_urls','filename','html'}:raise ValueError('보고서 입력 항목을 확인하세요.')
    cfg,row=company(root,payload['code'])
    def text(key,cap):
        v=payload[key]
        if not isinstance(v,str) or not v.strip() or len(v)>cap:raise ValueError('제목·출처·파일을 확인하세요.')
        return v.strip()
    title=text('title',200);label=text('source_label',200);filename=text('filename',250)
    if not filename.lower().endswith(('.html','.htm')) or '/' in filename or chr(92) in filename:raise ValueError('HTML 파일만 등록할 수 있습니다.')
    day=payload['authored_on']
    try:parsed=datetime.strptime(day,'%Y-%m-%d').date()
    except (ValueError,TypeError):raise ValueError('작성일을 확인하세요.') from None
    if parsed.isoformat()!=day or parsed>datetime.now(KST).date():raise ValueError('작성일은 오늘 이전 날짜로 입력하세요.')
    urls=payload['source_urls']
    if not isinstance(urls,list) or len(urls)>20:raise ValueError('출처 URL은 최대20개입니다.')
    urls=list(dict.fromkeys(public_url(u) for u in urls))
    html=payload['html']
    if not isinstance(html,str) or not html.strip() or len(html.encode('utf-8'))>LIMIT or '\x00' in html:raise ValueError('UTF-8 HTML은 3MB 이하로 등록하세요.')
    sha=hashlib.sha256(html.encode('utf-8')).hexdigest()
    identity=dict(code=payload['code'],name=row['name'],market=row['market'],title=title,authored_on=day,source_label=label,source_urls=urls,sha256=sha)
    report_id=hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    path=location(cfg);path.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(path,timeout=5)) as db:
        db.execute('CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY,code TEXT,name TEXT,market TEXT,title TEXT,authored_on TEXT,source_label TEXT,source_urls TEXT,filename TEXT,html TEXT,sha256 TEXT,created_at TEXT)')
        values=[report_id,payload['code'],row['name'],row['market'],title,day,label,json.dumps(urls,ensure_ascii=False),filename,html,sha,datetime.now(KST).isoformat()]
        inserted=db.execute('INSERT OR IGNORE INTO reports VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',values).rowcount
        db.commit()
    return dict(id=report_id,duplicate=not bool(inserted),**listing(root,payload['code']))

class StaticHTML(HTMLParser):
    allowed=set('article section header footer main nav aside div span p h1 h2 h3 h4 h5 h6 b strong i em small br hr ul ol li dl dt dd table thead tbody tfoot tr th td caption colgroup col blockquote pre code figure figcaption details summary a img style svg g path rect circle ellipse line polyline polygon text tspan defs linearGradient radialGradient stop clipPath'.lower().split())
    blocked={'script','iframe','object','embed','form','button','input','textarea','select','video','audio','canvas','title','noscript'}
    attrs=set('id class style title width height colspan rowspan scope open viewbox xmlns x y x1 x2 y1 y2 cx cy r rx ry d points fill stroke stroke-width opacity transform offset stop-color stop-opacity preserveaspectratio text-anchor font-size clip-path'.split())
    def __init__(self):super().__init__(convert_charrefs=True);self.out=[];self.skip=[];self.in_style=False
    def handle_starttag(self,tag,attrs):
        if self.skip:
            if tag in self.blocked and tag not in ('input','embed'):self.skip.append(tag)
            return
        if tag in self.blocked:
            if tag not in ('input','embed'):self.skip.append(tag)
            return
        if tag not in self.allowed:return
        clean=[]
        for k,v in attrs:
            if k in self.attrs:clean.append((k,v or ''))
            elif tag=='a' and k=='href' and (v or '').startswith('#'):clean.append((k,v))
            elif tag=='img' and k=='src' and re.match(r'^data:image/(?:png|jpeg|gif|webp);base64,',v or '',re.I):clean.append((k,v))
            elif tag=='img' and k=='alt':clean.append((k,v or ''))
        self.out.append('<'+tag+''.join(' '+k+'="'+escape(v,quote=True)+'"' for k,v in clean)+'>');self.in_style=tag=='style'
    def handle_endtag(self,tag):
        if self.skip:
            if tag==self.skip[-1]:self.skip.pop()
            return
        if tag in self.allowed:self.out.append('</'+tag+'>')
        if tag=='style':self.in_style=False
    def handle_data(self,data):
        if not self.skip:self.out.append(data if self.in_style else escape(data))

def read(root,code,report_id):
    cfg,row=company(root,code)
    if not isinstance(report_id,str) or not re.fullmatch('[a-f0-9]{64}',report_id):raise ValueError('보고서를 확인하세요.')
    path=location(cfg)
    if not path.exists():raise ValueError('등록된 보고서가 없습니다.')
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=5)) as db:
        db.row_factory=sqlite3.Row
        record=db.execute('SELECT * FROM reports WHERE id=? AND code=? AND name=? AND market=?',(report_id,code,row['name'],row['market'])).fetchone()
    if not record:raise ValueError('선택 기업의 보고서가 아닙니다.')
    if hashlib.sha256(record['html'].encode('utf-8')).hexdigest()!=record['sha256']:raise ValueError('보고서 파일 검증에 실패했습니다.')
    parser=StaticHTML();parser.feed(record['html']);parser.close()
    csp="default-src 'none'; script-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'"
    document='<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="'+escape(csp,quote=True)+'"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{overflow-wrap:anywhere}img,svg{max-width:100%}</style></head><body>'+''.join(parser.out)+'</body></html>'
    return dict(code=code,report=metadata(record),document=document)
