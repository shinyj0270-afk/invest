"""Loopback dashboard server backed by the existing freshness policy."""
import json
import re
import secrets
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer

from .auto_refresh import ensure_data
from .core import digest
from .workspace_export import export_workspace
from .naver_reference import load_cached_references
from .workspace_events import load_cached_events
from .market_discovery import load_market_cache
from .financial_table import load_local_financials


def public_receipt(receipt):
    """Keep provider paths and credentials out of browser responses."""
    return {key: receipt.get(key) for key in (
        'status', 'success', 'checked_at', 'data_as_of', 'target_date',
        'stale', 'updated_companies', 'price_records', 'failed_companies',
        'fallback', 'error')}


def handler_for(root, *, refresh=ensure_data, token=None):
    token = token or secrets.token_urlsafe(32)

    class DashboardHandler(BaseHTTPRequestHandler):
        def send_body(self, status, content, content_type):
            body = content.encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type + '; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
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
            receipt = public_receipt(result['receipt'])
            if result['snapshot'] is None:
                message = escape(receipt.get('error') or '실제 저장자료가 없습니다.')
                content = ('<!doctype html><html lang="ko"><meta charset="utf-8">'
                           '<title>INVESTMENT · 자료 대기</title><main style="font:16px sans-serif;'
                           'max-width:680px;margin:12vh auto;padding:24px"><h1>실제 저장자료 대기</h1>'
                           f'<p>{message}</p><p>기존 갱신 앱에서 저장자료 연결을 확인하세요.</p></main></html>')
                self.send_body(200, content, 'text/html')
                return
            live = dict(token=token, receipt=receipt, snapshot_id=digest(result['snapshot']))
            self.send_body(200, export_workspace(result['snapshot'], live=live,
                events=load_cached_events(root, result['snapshot']),
                references=load_cached_references(root, result['snapshot']),
                market_cache=load_market_cache(root, result['snapshot']), financials=load_local_financials(root, result['snapshot'])), 'text/html')

        def do_POST(self):
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


def serve(root, *, port=8767):
    with HTTPServer(('127.0.0.1', port), handler_for(root)) as server:
        print(f'INVESTMENT live dashboard: http://127.0.0.1:{server.server_port}/', flush=True)
        server.serve_forever()
