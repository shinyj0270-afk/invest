"""Loopback dashboard server backed by the existing freshness policy."""
import json
import re
import secrets
import sqlite3
import hashlib
import gzip
import threading
from collections import OrderedDict
from datetime import datetime, timedelta
import time
from zoneinfo import ZoneInfo
from pathlib import Path
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .auto_refresh import ensure_data
from .core import digest
from .workspace_export import export_workspace, export_holdings_frame
from .dashboard_build import source_fingerprint, build_identity, restart_page, loading_page
from .naver_reference import load_cached_references
from .workspace_events import load_cached_events
from .market_discovery import read_market_cache as load_market_cache, technical
from .market_history import benchmark_calendar
from .financial_table import load_local_financials, build_table, merge_financials
from .company_detail import build_details
from .holdings_sync import load_service, SyncError, LIMIT
from .local_config import load_local
from .core import validate_snapshot
from .holding_market import HoldingMarket
from .market_refresh import DailyMarketRefresh, collect_daily, collect_quotes
from .company_financials import CompanyFinancials, FinancialMonitor, load_cached as load_company_financials
from urllib.parse import urlsplit, parse_qs


def dashboard_input_version(root):
    """Cheap source versions, including SQLite WAL and deletions; never hash large histories."""
    cfg=load_local(root)
    folders=[cfg['data_dir']/cfg['profile'],Path(root)/'config',Path(root)/'.local/research-library'/cfg['profile']]
    files=[]
    for folder in folders:
        if folder.exists():
            for path in sorted(folder.rglob('*')):
                if path.suffix in ('.lock','.log','.tmp'):continue
                try:
                    if path.is_file():
                        stat=path.stat();files.append((str(path),stat.st_mtime_ns,stat.st_size,stat.st_ino))
                except FileNotFoundError:continue
    manual=cfg.get('manual_snapshot_file')
    if manual:
        for path in [manual]+[manual.parent/name for name in ('config-review.json','info.xlsx','income.xlsx','balance.xlsx','income-extra.xlsx','balance-extra.xlsx','debt-extra.xlsx')]:
            if path.exists():
                try:
                    stat=path.stat();files.append((str(path),stat.st_mtime_ns,stat.st_size,stat.st_ino))
                except FileNotFoundError:continue
    return (datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat(),tuple(files))


def public_receipt(receipt):
    """Keep provider paths and credentials out of browser responses."""
    result={key: receipt.get(key) for key in (
        'status', 'success', 'checked_at', 'data_as_of', 'target_date',
        'stale', 'updated_companies', 'price_records', 'failed_companies',
        'fallback', 'error')}
    error=result.get('error')
    if error and (not isinstance(error,str) or re.search(r'https?://|[A-Z]:[\\/]|(?:api[_-]?key|token|password|secret)\s*[=:]',error,re.I)):
        result['error']='자료 조회·검증 대기 · 연결 설정을 확인하고 다시 시도하세요.'
    return result


def daily_status(service):
    state=service.ensure_due() if service and hasattr(service,'ensure_due') else service.poll() if service else dict(status='unavailable')
    state=dict(state)
    attempt=getattr(service,'last_attempt',0)
    if attempt and state.get('status')!='running':
        remaining=max(0,1800-(time.monotonic()-attempt))
        state['next_retry_at']=(datetime.now(ZoneInfo('Asia/Seoul'))+timedelta(seconds=remaining)).isoformat(timespec='seconds')
    return state


def saved_data(root, *, force=False):
    # Opening the sync app does not change the existing market DB.
    if force:return ensure_data(root,force=True)
    cfg=load_local(root);db=cfg['data_dir']/cfg['profile']/'user_input/research.sqlite3'
    snapshot=None
    if db.exists():
        with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True) as conn:
            row=conn.execute("SELECT payload FROM snapshots WHERE status='complete' ORDER BY created DESC LIMIT 1").fetchone()
        if row:snapshot=json.loads(row[0]);validate_snapshot(snapshot)
    return dict(snapshot=snapshot,receipt=dict(status='cached',success=bool(snapshot),checked_at=datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
        data_as_of=snapshot['meta']['price_date'] if snapshot else None,stale=True,error=None))


def configured_data(root, *, force=False):
    """Naver opted-in PCs check freshness on opening; file-only PCs keep saved reads."""
    cfg = load_local(root)
    if (cfg.get('infomax_refresh') or {}).get('provider') == 'naver':
        return ensure_data(root, force=force)
    return saved_data(root, force=force)


def handler_for(root, *, refresh=ensure_data, token=None, holdings=None, quotes=None, daily=None, latest=None, financial=None, financial_monitor=None, read_only=False, report_inbox=None):
    token = token or secrets.token_urlsafe(32)
    from .report_inbox import ReportInbox
    report_inbox = report_inbox or ReportInbox(root,read_only=read_only)
    loaded_build_id = source_fingerprint(root)
    dashboard_cache={}
    section_cache=OrderedDict()
    cache_lock=threading.RLock()
    from .data_recovery import DataRecovery
    recovery=DataRecovery(root,None if read_only else daily,None if read_only else financial)
    restarting=threading.Event()
    request_lock=threading.RLock()
    company_read_lock=threading.Lock()
    company_reads=set()

    class DashboardHandler(BaseHTTPRequestHandler):
        def send_body(self, status, content, content_type):
            body = content.encode('utf-8')
            compressed = 'gzip' in self.headers.get('Accept-Encoding', '') and len(body)>1024
            if compressed:body=gzip.compress(body,compresslevel=1)
            self.send_response(status)
            self.send_header('Content-Type', content_type + '; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            if compressed:self.send_header('Content-Encoding','gzip')
            self.send_header('Vary','Accept-Encoding')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass

        def authorized(self, *, mutation=False):
            origin=f'http://127.0.0.1:{self.server.server_port}'
            return (self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}' and
                    self.headers.get('X-Dashboard-Token')==token and
                    (self.headers.get('Origin')==origin if mutation else self.headers.get('Origin') in (None,origin)))

        def do_GET(self):
            # Selected-company reads must not wait for a full dashboard/iframe export.
            # Keep other routes and all mutations on the existing serialized path.
            if urlsplit(self.path).path=='/company-reports':
                if not self.authorized():self.send_body(403,'{}','application/json');return
                q=parse_qs(urlsplit(self.path).query)
                if set(q) not in ({'code'},{'code','id'}) or any(len(v)!=1 for v in q.values()):self.send_body(400,'{}','application/json');return
                from .company_reports import listing,read
                try:
                    value=read(root,q['code'][0],q['id'][0]) if 'id' in q else listing(root,q['code'][0])
                    self.send_body(200,json.dumps(value,ensure_ascii=False),'application/json')
                except ValueError as exc:self.send_body(400,json.dumps({'error':str(exc)},ensure_ascii=False),'application/json')
                except (OSError,KeyError,TypeError,sqlite3.Error):self.send_body(503,'{"error":"보고서 저장소 연결 대기"}','application/json')
                return
            if urlsplit(self.path).path=='/company-events':
                if not self.authorized():self.send_body(403,'{"error":"요청 거부"}','application/json');return
                q=parse_qs(urlsplit(self.path).query)
                if set(q)!={'code'} or len(q['code'])!=1 or not re.fullmatch(r'\d{6}',q['code'][0]):
                    self.send_body(400,'{"error":"종목코드 확인 필요"}','application/json');return
                from .company_events import view as event_view
                try:self.send_body(200,json.dumps(event_view(root,q['code'][0],read_only=read_only),ensure_ascii=False),'application/json')
                except (OSError,ValueError,KeyError,TypeError):self.send_body(503,'{"error":"뉴스·공시 연결 대기"}','application/json')
                return
            if urlsplit(self.path).path=='/company-view':
                with company_read_lock:
                    if restarting.is_set():
                        self.send_body(503,'{"error":"서버 다시 실행 중"}','application/json');return
                    company_reads.add(self)
                try:self.handle_get()
                finally:
                    with company_read_lock:company_reads.discard(self)
                return
            with request_lock:self.handle_get()

        def handle_get(self):
            current_build_id=source_fingerprint(root)
            if self.path=='/health':
                identity=build_identity(root,loaded_build_id)
                identity.update(source_build_id=current_build_id,restart_required=current_build_id!=loaded_build_id)
                self.send_body(200,json.dumps(identity),'application/json');return
            if self.path=='/restart':
                if self.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}':self.send_body(403,'','text/plain');return
                self.send_body(200,restart_page(token),'text/html');return
            if restarting.is_set():self.send_body(503,'{"error":"서버 다시 실행 중"}','application/json');return
            if current_build_id!=loaded_build_id:
                self.send_body(503,restart_page(token) if self.path in ('/','/dashboard') else '{"error":"서버 다시 실행 필요"}',
                    'text/html' if self.path in ('/','/dashboard') else 'application/json');return
            if self.path=='/report-inbox':
                if not self.authorized():self.send_body(403,'{}','application/json');return
                self.send_body(200,json.dumps(report_inbox.view(),ensure_ascii=False),'application/json');return
            if self.path=='/data-recovery':
                if not self.authorized():self.send_body(403,'{}','application/json');return
                try:self.send_body(200,json.dumps(recovery.view(),ensure_ascii=False),'application/json')
                except (OSError,ValueError,TypeError):self.send_body(503,'{"error":"수집 상태 연결 대기"}','application/json')
                return
            if urlsplit(self.path).path=='/dashboard-section':
                if not self.authorized():self.send_body(403,'{}','application/json');return
                query=parse_qs(urlsplit(self.path).query)
                with cache_lock:
                    requested=query.get('version',[])
                    if set(query)!={'section','version'} or query.get('section')!=['trend-following'] or len(requested)!=1 or requested[0] not in section_cache:
                        self.send_body(409,'{"error":"저장자료가 바뀌었습니다. 입력을 보관하고 새로고침하세요."}','application/json');return
                    section=section_cache[requested[0]]['trend-following']
                self.send_body(200,json.dumps({'trend_following':section},ensure_ascii=False,separators=(',',':')),'application/json');return
            if self.path=='/holdings-frame':
                if not self.authorized():self.send_body(403,'{"error":"요청 거부"}','application/json');return
                result=refresh(root)
                if not result['snapshot']:self.send_body(404,'저장자료 대기','text/plain');return
                live=dict(token=token,holdings_sync=holdings is not None,holdings_market=quotes is not None)
                cache=load_market_cache(root,result['snapshot'])
                self.send_body(200,export_holdings_frame(result['snapshot'],live=live,market_cache=cache),'text/html');return
            if self.path=='/research-library':
                if not self.authorized():self.send_body(403,'{}','application/json');return
                from .research_library_view import view
                try:self.send_body(200,json.dumps(view(root),ensure_ascii=False),'application/json')
                except (ValueError,OSError,sqlite3.Error,KeyError,TypeError):self.send_body(503,'{}','application/json')
                return
            if self.path=='/recommendations':
                if not self.authorized():self.send_body(403,'{"error":"요청 거부"}','application/json');return
                if read_only:self.send_body(200,'{"records":[],"status":"read_only"}','application/json');return
                from .recommendations import RecommendationBook
                try:
                    snapshot=refresh(root)['snapshot'];cache=load_market_cache(root,snapshot) or {}
                    self.send_body(200,json.dumps(RecommendationBook(root).view(cache),ensure_ascii=False),'application/json')
                except (OSError,ValueError,KeyError,TypeError):self.send_body(503,'{"error":"추천 기록 연결 대기"}','application/json')
                return
            if urlsplit(self.path).path=='/company-view':
                if not self.authorized():self.send_body(403,'{"error":"요청 거부"}','application/json');return
                q=parse_qs(urlsplit(self.path).query)
                if set(q)!={'code'} or len(q['code'])!=1 or not re.fullmatch(r'[0-9A-Z]{6}',q['code'][0]):
                    self.send_body(400,'{"error":"종목코드 확인 필요"}','application/json');return
                result=refresh(root);snapshot=result['snapshot'];code=q['code'][0]
                if not snapshot:self.send_body(404,'{"error":"저장자료 대기"}','application/json');return
                cache=load_market_cache(root,snapshot,codes=[code]) or {}
                row=next((r for r in snapshot['companies'] if r['code']==code),None)
                if row is None:row=next((r for r in cache.get('universe',{}).get('companies',[]) if r['code']==code and r.get('eligibility')=='candidate'),None)
                if row is None:self.send_body(404,'{"error":"저장기업 확인 필요"}','application/json');return
                cutoff=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
                bundles=load_company_financials(root,snapshot,[row],as_of=cutoff) if financial else {}
                manual=load_local_financials(root,snapshot).get(code)
                bundles=merge_financials({code:manual} if manual else {},bundles,as_of=cutoff)
                scope=dict(meta=dict(snapshot['meta'],price_date=cutoff),companies=[row])
                table=build_table(row,scope,bundles.get(code),max_columns=48)
                model=build_details(scope,{code:table},cache)[code]
                model['collection_health']=bundles.get(code,{}).get('collection_health',{})
                history=cache.get('history') or {}
                try:calendar=benchmark_calendar(history.get('benchmarks',{}))
                except (ValueError,KeyError,TypeError):calendar={}
                record=history.get('histories',{}).get(code)
                if record and record.get('symbol')!=code:record=None
                detail=technical(record,history.get('benchmarks',{}).get(row['market']),calendar,
                    suspended=row.get('trading_status',{}).get('tradeStopYn')=='Y')
                from .financial_metrics import common_metrics,apply_common
                from .market_insights import reconcile_prices
                # Same contract as the discovery export, retaining original reviewed metadata.
                discovered=next((r for r in cache.get('universe',{}).get('companies',[]) if r['code']==code),row)
                merged=dict(discovered,**row);quote=cache.get('quotes',{}).get('quotes',{}).get(code)
                if quote and (quote.get('name'),quote.get('market'))==(row['name'],row['market']):merged['latest_quote']=quote
                common=common_metrics(merged,table,detail)
                original=next((r for r in snapshot['companies'] if r['code']==code),None)
                if original:
                    from .valuation import enrich_valuation
                    from .workspace_research import build_research
                    checked=enrich_valuation(snapshot);f=build_research(checked)['rows'][code]['fundamental']
                    merged['metrics']=dict(merged.get('metrics',{}),**f['metrics'])
                    merged['metric_details']={k:dict(source='인포맥스 검토 저장자료',period=f.get('period'),basis=f.get('basis'),status='reviewed',price_date=snapshot['meta']['price_date']) for k in f['metrics']}
                temp={'fundamental':{}}
                apply_common(merged,temp,common);model['common_financial']=merged.get('common_financial')
                from .verification import verify_company, compact as compact_verification
                model['verification']=compact_verification(verify_company(dict(merged,financial_completeness=model.get('financial_completeness')),detail,cutoff))
                original=next((r for r in snapshot['companies'] if r['code']==code),row)
                model['price_audit']=reconcile_prices(original,record)
                self.send_body(200,json.dumps(dict(code=code,name=row['name'],market=row['market'],table=table,model=model,series=detail['series'],trend_analysis=detail.get('trend_analysis')),ensure_ascii=False,separators=(',',':')),'application/json');return
            if self.path=='/financial-monitor':
                if not self.authorized():self.send_body(403,'{"error":"요청 거부"}','application/json');return
                state=financial_monitor.ensure_due() if financial_monitor else dict(status='offline')
                self.send_body(200,json.dumps(state,ensure_ascii=False),'application/json');return
            if urlsplit(self.path).path=='/company-financials':
                if not self.authorized():self.send_body(403,'{"error":"요청 거부"}','application/json');return
                q=parse_qs(urlsplit(self.path).query)
                if set(q)!={'code'} or len(q['code'])!=1 or not re.fullmatch(r'[0-9A-Z]{6}',q['code'][0]):
                    self.send_body(400,'{"error":"종목코드 확인 필요"}','application/json');return
                self.send_body(200,json.dumps(financial.poll(q['code'][0]) if financial else dict(status='unavailable'),ensure_ascii=False),'application/json');return
            if self.path == '/quote-refresh':
                if not self.authorized():self.send_body(403,'{"error":"요청 거부"}','application/json');return
                self.send_body(200,json.dumps(latest.poll() if latest else dict(status='unavailable'),ensure_ascii=False),'application/json');return
            if self.path == '/market-refresh':
                if not self.authorized():self.send_body(403,'{"error":"요청 거부"}','application/json');return
                state=daily_status(daily)
                self.send_body(200,json.dumps(state,ensure_ascii=False),'application/json')
                return
            if urlsplit(self.path).path=='/holding-market':
                if not self.authorized():self.send_body(403,'{"error":"요청 거부"}','application/json');return
                query=parse_qs(urlsplit(self.path).query)
                try:
                    if set(query)-{'code','refresh'} or len(query.get('code',[]))!=1 or query.get('refresh') not in (None,['1']):raise ValueError()
                    if quotes is None:self.send_body(503,'{"error":"가격 연결 설정 필요"}','application/json');return
                    result=quotes.lookup(query['code'][0],force=True) if query.get('refresh') else quotes.lookup(query['code'][0])
                    self.send_body(200,json.dumps(result,ensure_ascii=False),'application/json')
                except ValueError:self.send_body(400,'{"error":"종목코드 형식 확인 필요"}','application/json')
                return
            if self.path=='/holdings':
                if not self.authorized():self.send_body(403,'{"error":"요청 거부"}','application/json');return
                if holdings is None:self.send_body(200,'{"status":"offline","message":"동기화 연결 설정 필요"}','application/json');return
                self.send_body(200,json.dumps(holdings.poll(),ensure_ascii=False),'application/json');return
            if re.fullmatch(r'/investment_dashboard_\d{8}\.html', self.path):
                self.send_response(302)
                self.send_header('Location', '/')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                return
            if self.path not in ('/', '/dashboard'):
                self.send_body(404, '찾을 수 없습니다', 'text/plain')
                return
            if self.path == '/':
                self.send_body(200, loading_page(), 'text/html');return
            result = refresh(root)
            if daily and hasattr(daily,'ensure_due'):daily.ensure_due()
            if financial_monitor:financial_monitor.ensure_due()
            financial_state=financial_monitor.poll() if financial_monitor else {}
            monitor_version=json.dumps({key:financial_state.get(key) for key in ('revision','versions')},sort_keys=True)
            version=(digest(result['snapshot']) if result['snapshot'] else None,dashboard_input_version(root),monitor_version)
            with cache_lock:
                cached=dashboard_cache.get('entry')
                if cached and cached[0]==version:
                    self.send_body(200,cached[1],'text/html');return
            receipt = public_receipt(result['receipt'])
            if result['snapshot'] is None:
                message = escape(receipt.get('error') or '실제 저장자료가 없습니다.')
                content = ('<!doctype html><html lang="ko"><meta charset="utf-8">'
                           '<title>INVESTMENT · 자료 대기</title><main style="font:16px sans-serif;'
                           'max-width:680px;margin:12vh auto;padding:24px"><h1>실제 저장자료 대기</h1>'
                           f'<p>{message}</p><p>기존 갱신 앱에서 저장자료 연결을 확인하세요.</p></main></html>')
                self.send_body(200, content, 'text/html')
                return
            cache=load_market_cache(root,result['snapshot'])
            financial_state=financial_monitor.poll() if financial_monitor else {}
            financial_revision=financial_state.get('revision')
            financial_as_of=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
            all_financial_rows={r['code']:r for r in (cache or {}).get('universe',{}).get('companies',[]) if r.get('eligibility')=='candidate'}
            all_financial_rows.update({r['code']:r for r in result['snapshot']['companies']})
            finances=load_company_financials(root,result['snapshot'],list(all_financial_rows.values()),as_of=financial_as_of,cache=cache) if financial else {}
            finances=merge_financials(load_local_financials(root,result['snapshot']),finances,as_of=financial_as_of)
            live = dict(token=token, receipt=receipt, snapshot_id=digest(result['snapshot']),holdings_sync=holdings is not None,holdings_market=quotes is not None, daily_prices=daily is not None, latest_prices=latest is not None, company_financials=financial is not None)
            live['financial_monitor']=financial_monitor is not None
            live['financial_revision']=financial_revision
            live['financial_versions']=financial_state.get('versions',{})
            live['financial_as_of']=financial_as_of
            live['lazy_company_views']=True
            live['lazy_holdings_frame']=True
            live['lazy_trend_following']=True
            live['section_version']=hashlib.sha256(repr(version).encode()).hexdigest()
            live['build_id']=loaded_build_id
            live['protocol_version']=build_identity(root,loaded_build_id)['version']
            sections={}
            content=export_workspace(result['snapshot'], live=live,section_sink=lambda key,value:sections.update({key:value}),
                events=load_cached_events(root, result['snapshot']),
                references=load_cached_references(root, result['snapshot']),
                market_cache=cache, financials=finances,
                    trend_checkpoint_directory=Path(root)/'.local'/'trend-checkpoints' if daily else None)
            with cache_lock:
                section_cache[live['section_version']]=sections
                while len(section_cache)>3:section_cache.popitem(last=False)
                latest_state=financial_monitor.poll() if financial_monitor else {}
                latest_version=json.dumps({key:latest_state.get(key) for key in ('revision','versions')},sort_keys=True)
                if version==(digest(result['snapshot']),dashboard_input_version(root),latest_version):
                    dashboard_cache['entry']=(version,content,live['section_version'])
            self.send_body(200,content,'text/html')

        def empty_refresh_request(self):
            if not self.authorized(mutation=True):
                return False
            length = self.headers.get('Content-Length')
            if length in ('0', None):
                return True
            # Drain only a small, authenticated invalid body so Windows can
            # deliver the rejection response instead of resetting the socket.
            try:
                size = int(length)
                if 0 < size <= 1024:
                    self.connection.settimeout(1)
                    self.rfile.read(size)
            except (ValueError, OSError):
                pass
            return False

        def drain_small_body(self):
            # Read a small rejected body so Windows delivers the response
            # instead of resetting the socket (WinError 10053).
            try:
                size=int(self.headers.get('Content-Length','0'))
                if 0<size<=1024:
                    self.connection.settimeout(1);self.rfile.read(size)
            except (ValueError,OSError):
                pass

        def do_POST(self):
            with request_lock:self.handle_post()

        def handle_post(self):
            if read_only:
                self.drain_small_body();self.send_body(403,'{"error":"읽기 전용 실행"}','application/json');return
            if restarting.is_set():self.drain_small_body();self.send_body(409,'{"error":"서버 다시 실행 중"}','application/json');return
            if self.path=='/restart':
                if not self.authorized(mutation=True):self.drain_small_body();self.send_body(403,'{}','application/json');return
                leases=[]
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=128 or json.loads(self.rfile.read(size))!={'drafts_saved':True}:raise ValueError('작성 내용 보관 확인이 필요합니다.')
                    for service in (daily,latest,financial_monitor):
                        if service and service.poll().get('status') in ('running','syncing'):raise ValueError('수집·동기화 진행 중입니다. 완료 후 다시 시도하세요.')
                    if financial and financial.running():raise ValueError('재무 수집 완료 후 다시 시도하세요.')
                    from .company_financials import acquire_lock
                    cfg=load_local(root);folder=cfg['data_dir']/cfg['profile']
                    for path in folder.rglob('*.lock'):
                        leases.append(acquire_lock(path))
                    with company_read_lock:
                        if company_reads:raise ValueError('기업 자료 조회 중입니다. 완료 후 다시 시도하세요.')
                        report_inbox.pause()
                        restarting.set()
                except (ValueError,TypeError,OSError) as exc:
                    for lease in leases:lease.close()
                    message='다시 실행 조건을 확인하지 못했습니다. 수집·동기화 완료와 입력 보관을 확인하세요.' if isinstance(exc,OSError) else str(exc)
                    self.send_body(409,json.dumps({'error':message},ensure_ascii=False),'application/json');return
                self.send_body(202,json.dumps({'message':'입력 저장소를 유지하며 서버를 다시 실행합니다.'},ensure_ascii=False),'application/json')
                def restart():
                    import subprocess,sys,os
                    self.server.shutdown();self.server.server_close()
                    for lease in leases:lease.close()
                    subprocess.Popen([sys.executable,str(Path(root)/'tools/open_dashboard.py'),'--no-browser','--port',str(self.server.server_port)],cwd=root,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                threading.Thread(target=restart,daemon=False).start();return
            if source_fingerprint(root)!=loaded_build_id:
                self.send_body(503,'{"error":"코드 버전이 달라 서버 다시 실행 필요 · 기존 입력 유지"}','application/json');return
            if self.path=='/report-inbox':
                if not self.empty_refresh_request():self.send_body(403,'{}','application/json');return
                self.send_body(200,json.dumps(report_inbox.scan(),ensure_ascii=False),'application/json');return
            if self.path=='/company-reports':
                if not self.authorized(mutation=True):self.send_body(403,'{}','application/json');return
                from .company_reports import register,LIMIT as REPORT_LIMIT
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=6*REPORT_LIMIT or self.headers.get('Content-Type')!='application/json':raise ValueError('HTML 파일 크기·형식을 확인하세요.')
                    self.connection.settimeout(15)
                    value=register(root,json.loads(self.rfile.read(size)))
                    self.send_body(200,json.dumps(value,ensure_ascii=False),'application/json')
                except (ValueError,UnicodeError) as exc:self.send_body(400,json.dumps({'error':str(exc)},ensure_ascii=False),'application/json')
                except (OSError,KeyError,TypeError,sqlite3.Error):self.send_body(503,'{"error":"보고서 저장 실패 · 기존 자료 유지"}','application/json')
                return
            if self.path=='/data-recovery':
                if not self.authorized(mutation=True):self.send_body(403,'{}','application/json');return
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=1024:raise ValueError()
                    request=json.loads(self.rfile.read(size))
                    if set(request)!={'kind','code'}:raise ValueError()
                    state=recovery.retry(request['kind'],request['code'])
                    self.send_body(202,json.dumps(state,ensure_ascii=False),'application/json')
                except (ValueError,TypeError,KeyError):self.send_body(400,'{"error":"실패 항목을 확인하세요"}','application/json')
                return
            if self.path=='/recommendations':
                if not self.authorized(mutation=True):self.send_body(403,'{"error":"요청 거부"}','application/json');return
                from .recommendations import RecommendationBook,research_context
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=4096:raise ValueError('요청 크기 확인 필요')
                    request=json.loads(self.rfile.read(size));kind=request.get('kind');reason=request.get('reason','')
                    if set(request)-{'kind','reason'} or kind not in ('monthly','exception') or not isinstance(reason,str) or len(reason)>1000:raise ValueError('추천 검토 요청 확인 필요')
                    snapshot=refresh(root)['snapshot'];cache=load_market_cache(root,snapshot) or {}
                    rows={r['code']:r for r in cache.get('universe',{}).get('companies',[]) if r.get('eligibility')=='candidate'};rows.update({r['code']:r for r in snapshot['companies']})
                    today=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
                    finances=load_company_financials(root,snapshot,list(rows.values()),as_of=today,cache=cache)
                    finances=merge_financials(load_local_financials(root,snapshot),finances,as_of=today)
                    book=RecommendationBook(root);book.append(research_context(snapshot,cache,finances,today),kind,reason,today)
                    self.send_body(200,json.dumps(book.view(cache),ensure_ascii=False),'application/json')
                except ValueError:self.send_body(400,'{"error":"최근 종가·추천 종류·월중 조정 이유를 확인하세요"}','application/json')
                except (OSError,KeyError,TypeError):self.send_body(503,'{"error":"추천 작성 연결 대기 · 기존 기록 유지"}','application/json')
                return
            if urlsplit(self.path).path=='/company-financials':
                if not self.empty_refresh_request():self.send_body(403,'{"error":"요청 거부"}','application/json');return
                q=parse_qs(urlsplit(self.path).query)
                try:
                    if set(q)!={'code'} or len(q['code'])!=1:raise ValueError()
                    if financial is None:self.send_body(503,'{"error":"재무자료 연결 필요"}','application/json');return
                    self.send_body(202,json.dumps(financial.start(q['code'][0]),ensure_ascii=False),'application/json')
                except ValueError:self.send_body(400,'{"error":"저장 후보 종목 확인 필요"}','application/json')
                return
            if self.path == '/quote-refresh':
                if not self.empty_refresh_request():
                    self.send_body(403,'{"error":"요청 거부"}','application/json');return
                if latest is None:self.send_body(503,'{"error":"최신 가격 연결 필요"}','application/json');return
                self.send_body(202,json.dumps(latest.start(),ensure_ascii=False),'application/json');return
            if self.path == '/market-refresh':
                if not self.empty_refresh_request():
                    self.send_body(403,'{"error":"요청 거부"}','application/json');return
                if daily is None:self.send_body(503,'{"error":"일별 갱신 연결 필요"}','application/json');return
                self.send_body(202,json.dumps(daily.start(),ensure_ascii=False),'application/json')
                return
            if self.path=='/holdings':
                if not self.authorized(mutation=True):self.send_body(403,'{"error":"요청 거부"}','application/json');return
                if holdings is None:self.send_body(503,'{"error":"동기화 연결 설정 필요"}','application/json');return
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if size<=0 or size>2*LIMIT+2048 or self.headers.get('Content-Type')!='application/json':raise ValueError()
                    payload=json.loads(self.rfile.read(size))
                    if not isinstance(payload,dict):raise ValueError()
                    result=holdings.submit(payload['state'],payload.get('base'))
                    self.send_body(200,json.dumps(result,ensure_ascii=False),'application/json')
                except (ValueError,KeyError,SyncError):self.send_body(400,'{"error":"보유 입력 형식과 크기를 확인하세요."}','application/json')
                return
            expected_origin = f'http://127.0.0.1:{self.server.server_port}'
            if (self.path != '/refresh' or self.headers.get('Origin') != expected_origin or
                    self.headers.get('X-Dashboard-Token') != token or
                    self.headers.get('Content-Length') not in ('0', None)):
                self.send_body(403, '{"error":"요청 거부"}', 'application/json')
                return
            result = refresh(root, force=True)
            receipt = public_receipt(result['receipt'])
            payload = dict(receipt=receipt,
                           snapshot_id=digest(result['snapshot']) if result['snapshot'] else None)
            self.send_body(200, json.dumps(payload, ensure_ascii=False), 'application/json')

        def log_message(self, format, *args):
            # Requests are local; no provider URL or payload is logged.
            pass

    return DashboardHandler


def serve(root, *, port=8767, saved_only=False, read_only=False):
    if read_only:
        with ThreadingHTTPServer(('127.0.0.1', port), handler_for(root,refresh=lambda folder,force=False:saved_data(folder),read_only=True)) as server:
            server.serve_forever()
        return
    holdings=load_service(root)
    quotes=HoldingMarket(root,lambda:saved_data(root)['snapshot'])
    daily=DailyMarketRefresh(root,collector=lambda folder, progress,**kwargs:collect_daily(folder,progress,skip_unchanged=True,**kwargs))
    latest=DailyMarketRefresh(root,collector=collect_quotes,kind='quote')
    financial=CompanyFinancials(root)
    monitor=FinancialMonitor(root,financial,track_completion=True)
    from .report_inbox import ReportInbox
    inbox=ReportInbox(root)
    with ThreadingHTTPServer(('127.0.0.1', port), handler_for(root,holdings=holdings,quotes=quotes,daily=daily,latest=latest,financial=financial,financial_monitor=monitor,report_inbox=inbox,refresh=configured_data if saved_only else ensure_data)) as server:
        print(f'INVESTMENT live dashboard: http://127.0.0.1:{server.server_port}/', flush=True)
        inbox.start()
        try:server.serve_forever()
        finally:inbox.stop()
