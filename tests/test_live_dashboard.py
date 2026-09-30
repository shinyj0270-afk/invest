"""Loopback route, freshness invocation and fallback behavior without Infomax."""
import json
import re
import threading
import unittest
from http.server import HTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from investment.fixture import make_fixture
from investment.live_dashboard import handler_for, public_receipt


class FakeRefresh:
    def __init__(self):
        self.snapshot = make_fixture()
        self.snapshot['meta']['data_mode'] = 'user_input'
        self.calls = []

    def __call__(self, root, *, force=False):
        self.calls.append(force)
        receipt = dict(status='cached' if not force else 'unchanged', success=True,
                       checked_at='2026-09-30T09:00:00+09:00', data_as_of=self.snapshot['meta']['price_date'] if self.snapshot else None,
                       target_date='2026-09-23', stale=self.snapshot is None,
                       updated_companies=0, price_records=0, failed_companies=0,
                       fallback=False, error=None, private_path='must-not-appear')
        return dict(snapshot=self.snapshot, receipt=receipt)


class LiveDashboardTests(unittest.TestCase):
    def setUp(self):
        self.provider = FakeRefresh()
        self.server = HTTPServer(('127.0.0.1', 0), handler_for('.', refresh=self.provider, token='test-token'))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def test_startup_refresh_and_manual_refresh(self):
        with urlopen(self.base + '/') as response:
            html = response.read().decode('utf-8')
            self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertIn('통합 투자 대시보드', html)
        self.assertEqual(self.provider.calls, [False])
        live = json.loads(re.search(r'const INVESTMENT_LIVE=(.*?);const WORKSPACE_DATA=', html, re.S).group(1))
        self.assertEqual(live['receipt']['status'], 'cached')
        self.assertNotIn('private_path', html)
        request = Request(self.base + '/refresh', data=b'', method='POST', headers={
            'Origin': self.base, 'X-Dashboard-Token': live['token']})
        with urlopen(request) as response:
            result = json.load(response)
        self.assertEqual(result['receipt']['status'], 'unchanged')
        self.assertEqual(self.provider.calls, [False, True])

    def test_refresh_requires_same_origin_and_token(self):
        for headers in ({}, {'Origin': 'https://elsewhere.example', 'X-Dashboard-Token': 'test-token'},
                        {'Origin': self.base, 'X-Dashboard-Token': 'incorrect'}):
            with self.subTest(headers=headers), self.assertRaises(HTTPError) as error:
                urlopen(Request(self.base + '/refresh', data=b'', method='POST', headers=headers))
            self.assertEqual(error.exception.code, 403)
        self.assertEqual(self.provider.calls, [])

    def test_old_preview_path_opens_live_dashboard(self):
        with urlopen(self.base + '/investment_dashboard_20260923.html') as response:
            self.assertIn('통합 투자 대시보드', response.read().decode('utf-8'))
        self.assertEqual(self.provider.calls, [False])

    def test_missing_data_stays_missing(self):
        self.provider.snapshot = None
        with urlopen(self.base + '/') as response:
            html = response.read().decode('utf-8')
        self.assertIn('실제 저장자료 대기', html)
        self.assertNotIn('가상 연구기업', html)

    def test_public_receipt_only_allows_summary_fields(self):
        self.assertEqual(public_receipt({'status': 'failed', 'error': '갱신 실패 · OSError',
                                         'private_path': 'C:/secret'})['error'], '갱신 실패 · OSError')
        self.assertNotIn('private_path', public_receipt({'private_path': 'C:/secret'}))
