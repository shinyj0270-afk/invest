"""Loopback dashboard server backed by the existing freshness policy."""
import json
import re
import secrets
import sqlite3
import hashlib
import gzip
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .auto_refresh import ensure_data
from .core import digest
from .workspace_export import export_workspace
from .naver_reference import load_cached_references
from .workspace_events import load_cached_events
from .market_discovery import load_market_cache, technical
from .market_history import benchmark_calendar
from .financial_table import load_local_financials, build_table
from .company_detail import build_details
from .holdings_sync import load_service, SyncError, LIMIT
from .local_config import load_local
from .core import validate_snapshot
from .holding_market import HoldingMarket
from .market_refresh import DailyMarketRefresh, collect_daily, collect_quotes
from .company_financials import CompanyFinancials, FinancialMonitor, load_cached as load_company_financials
from urllib.parse import urlsplit, parse_qs


def public_receipt(receipt):
    """Keep provider paths and credentials out of browser responses."""
    return {key: receipt.get(key) for key in (
        'status', 'success', 'checked_at', 'data_as_of', 'target_date',
        'stale', 'updated_companies', 'price_records', 'failed_companies',
        'fallback', 'error')}


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


def handler_for(root, *, refresh=ensure_data, token=None, holdings=None, quotes=None, daily=None, latest=None, financial=None, financial_monitor=None):
    token = token or secrets.token_urlsafe(32)

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
            if self.path=='/recommendations':
                if not self.authorized():self.send_body(403,'{"error":"요청 거부"}','application/json');return
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
                cache=load_market_cache(root,snapshot) or {}
                row=next((r for r in snapshot['companies'] if r['code']==code),None)
                if row is None:row=next((r for r in cache.get('universe',{}).get('companies',[]) if r['code']==code and r.get('eligibility')=='candidate'),None)
                if row is None:self.send_body(404,'{"error":"저장기업 확인 필요"}','application/json');return
                cutoff=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
                bundles=load_company_financials(root,snapshot,[row],as_of=cutoff) if financial else {}
                manual=load_local_financials(root,snapshot).get(code)
                if manual:
                    keys={(p['basis'],p['cadence'],p['period_end']) for p in manual['periods']}
                    manual['periods'].extend(p for p in bundles.get(code,{}).get('periods',[]) if (p['basis'],p['cadence'],p['period_end']) not in keys)
                    manual['notes'].extend(bundles.get(code,{}).get('notes',[]))
                    manual['collection_health']=bundles.get(code,{}).get('collection_health',{})
                    bundles[code]=manual
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
                    merged['metric_details']={k:dict(source='인포맥스 우선 저장자료',period=f.get('period'),basis=f.get('basis'),status='reviewed',price_date=snapshot['meta']['price_date']) for k in f['metrics']}
                temp={'fundamental':{}}
                apply_common(merged,temp,common);model['common_financial']=merged.get('common_financial')
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
                state=daily.ensure_due() if daily and hasattr(daily,'ensure_due') else daily.poll() if daily else dict(status='unavailable')
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
            if self.path=='/health':
                root_id=hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()
                self.send_body(200,json.dumps(dict(app='investment-holdings-sync',version=1,root_id=root_id)),'application/json');return
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
            result = refresh(root)
            if daily and hasattr(daily,'ensure_due'):daily.ensure_due()
            if financial_monitor:financial_monitor.ensure_due()
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
            for code,manual in load_local_financials(root,result['snapshot']).items():
                public=finances.get(code)
                if public:
                    manual_keys={(p['basis'],p['cadence'],p['period_end']) for p in manual['periods']}
                    manual['periods'].extend(p for p in public['periods'] if (p['basis'],p['cadence'],p['period_end']) not in manual_keys)
                    manual['notes'].extend(public.get('notes',[]))
                    manual['collection_health']=public.get('collection_health',{})
                finances[code]=manual
            live = dict(token=token, receipt=receipt, snapshot_id=digest(result['snapshot']),holdings_sync=holdings is not None,holdings_market=quotes is not None, daily_prices=daily is not None, latest_prices=latest is not None, company_financials=financial is not None)
            live['financial_monitor']=financial_monitor is not None
            live['financial_revision']=financial_revision
            live['financial_versions']=financial_state.get('versions',{})
            live['financial_as_of']=financial_as_of
            live['lazy_company_views']=True
            self.send_body(200, export_workspace(result['snapshot'], live=live,
                events=load_cached_events(root, result['snapshot']),
                references=load_cached_references(root, result['snapshot']),
                market_cache=cache, financials=finances), 'text/html')

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

        def do_POST(self):
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
                    for code,manual in load_local_financials(root,snapshot).items():
                        keys={(p['basis'],p['cadence'],p['period_end']) for p in manual['periods']}
                        manual['periods'].extend(p for p in finances.get(code,{}).get('periods',[]) if (p['basis'],p['cadence'],p['period_end']) not in keys);finances[code]=manual
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


def serve(root, *, port=8767, saved_only=False):
    holdings=load_service(root)
    quotes=HoldingMarket(root,lambda:saved_data(root)['snapshot'])
    daily=DailyMarketRefresh(root,collector=lambda folder, progress:collect_daily(folder,progress,skip_unchanged=True))
    latest=DailyMarketRefresh(root,collector=collect_quotes,kind='quote')
    financial=CompanyFinancials(root)
    monitor=FinancialMonitor(root,financial,track_completion=True)
    with ThreadingHTTPServer(('127.0.0.1', port), handler_for(root,holdings=holdings,quotes=quotes,daily=daily,latest=latest,financial=financial,financial_monitor=monitor,refresh=saved_data if saved_only else ensure_data)) as server:
        print(f'INVESTMENT live dashboard: http://127.0.0.1:{server.server_port}/', flush=True)
        server.serve_forever()
