import io
import json
import unittest
import zipfile
from investment.pit_acquire import Budget, BudgetExceeded
from investment.pit_live import OpenDart, QuotaStop, corp_candidates, key_from_env, plan_first_call

KEY = 'k' * 40


class FakeResponse:
    def __init__(self, content=b'{}', status=200, headers=None):
        self.content, self.status_code, self.headers = content, status, headers or {}
    def __enter__(self):return self
    def __exit__(self, *a):return False
    def raise_for_status(self):
        if self.status_code >= 400:raise RuntimeError(f'HTTP {self.status_code} for https://opendart.fss.or.kr/api/x?crtfc_key={KEY}')
    def iter_content(self, size):
        for i in range(0, len(self.content), size):yield self.content[i:i + size]


class FakeSession:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []
    def get(self, url, params=None, timeout=None, stream=False, headers=None):
        self.calls.append(dict(url=url, params=dict(params or {}), timeout=timeout))
        r = self.responses.pop(0)
        if isinstance(r, Exception):raise r
        return r


def client(*responses, max_requests=10, **kw):
    budget = Budget(max_requests=max_requests, min_interval=0.0, clock=lambda: 0.0, sleep=lambda s: None)
    session = FakeSession(*responses)
    return OpenDart(KEY, session=session, budget=budget, **kw), session, budget


def corp_zip(rows):
    body = '<?xml version="1.0" encoding="UTF-8"?><result>' + ''.join(
        f'<list><corp_code>{c}</corp_code><corp_name>{n}</corp_name><stock_code>{s}</stock_code><modify_date>20240101</modify_date></list>' for c, n, s in rows) + '</result>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as z:z.writestr('CORPCODE.xml', body)
    return buffer.getvalue()


class ClientTests(unittest.TestCase):
    def test_every_request_is_charged_to_the_budget_and_carries_the_key_as_a_parameter_only(self):
        api, session, budget = client(FakeResponse(json.dumps(dict(status='000', page_no=1, total_count=0, total_page=1, list=[])).encode()))
        api.list_page('00126380', '20230101', '20261103', 1)
        self.assertEqual(budget.count, 1);call = session.calls[0]
        self.assertEqual((call['url'], call['params']['corp_code'], call['params']['crtfc_key'], call['params']['last_reprt_at'], call['params']['pblntf_ty']),
            ('https://opendart.fss.or.kr/api/list.json', '00126380', KEY, 'N', 'A'))
        self.assertNotIn(KEY, call['url'])

    def test_the_key_never_appears_in_error_messages_or_the_repr(self):
        api, _, _ = client(RuntimeError('boom ' + KEY), FakeResponse(b'x', status=500))
        for _ in range(2):
            with self.assertRaises(ValueError) as raised:api.corp_code_zip()
            self.assertNotIn(KEY, str(raised.exception))
        self.assertNotIn(KEY, repr(api));self.assertNotIn(KEY, str(api))

    def test_a_quota_status_or_http_429_stops_everything(self):
        api, _, _ = client(FakeResponse(json.dumps(dict(status='020', message='limit')).encode()))
        with self.assertRaises(QuotaStop):api.list_page('00126380', '20230101', '20261103', 1)
        api, _, _ = client(FakeResponse(b'', status=429))
        with self.assertRaises(QuotaStop):api.corp_code_zip()

    def test_other_error_statuses_are_value_errors_and_no_data_is_not_an_error(self):
        api, _, _ = client(FakeResponse(json.dumps(dict(status='010', message='unregistered key')).encode()))
        with self.assertRaises(ValueError):api.list_page('00126380', '20230101', '20261103', 1)
        api, _, _ = client(FakeResponse(json.dumps(dict(status='013', message='no data')).encode()))
        self.assertEqual(api.list_page('00126380', '20230101', '20261103', 1)['status'], '013')

    def test_oversized_responses_are_refused_and_the_budget_still_counted(self):
        api, _, budget = client(FakeResponse(b'PK' + b'x' * 100), max_bytes=10)          # looks like a zip, so only the size cap can refuse it
        with self.assertRaises(ValueError):api.corp_code_zip()
        self.assertEqual(budget.count, 1)

    def test_the_budget_stops_the_run_before_the_network_is_touched(self):
        api, session, _ = client(FakeResponse(b'{}'), max_requests=0)
        with self.assertRaises(BudgetExceeded):api.corp_code_zip()
        self.assertEqual(session.calls, [])

    def test_a_document_download_that_is_really_a_json_error_is_not_returned_as_a_zip(self):
        api, _, _ = client(FakeResponse(json.dumps(dict(status='014', message='file missing')).encode()))
        with self.assertRaises(ValueError):api.document_zip('20260310000001')
        data = corp_zip([('1', 'a', '000001')]);api, session, _ = client(FakeResponse(data))
        self.assertEqual(api.document_zip('20260310000001'), data);self.assertEqual(session.calls[0]['params']['rcept_no'], '20260310000001')

    def test_malformed_arguments_are_rejected_before_any_request(self):
        api, session, budget = client(FakeResponse(b'{}'))
        for call in (lambda: api.list_page('123', '20230101', '20261103', 1), lambda: api.list_page('00126380', '2023-01-01', '20261103', 1),
                     lambda: api.list_page('00126380', '20230101', '20261103', 0), lambda: api.document_zip('123')):
            with self.assertRaises(ValueError):call()
        self.assertEqual((session.calls, budget.count), ([], 0))


class CorpCodeTests(unittest.TestCase):
    def test_candidates_are_found_by_stock_code_and_by_name_without_guessing(self):
        data = corp_zip([('00126380', '삼성전자', '005930'), ('00555555', '효성중공업', '298040'), ('00777777', '도레이케미칼', ''), ('00888888', '도레이케미칼', '')])
        self.assertEqual([c['corp_code'] for c in corp_candidates(data, stock_code='298040')], ['00555555'])
        self.assertEqual(len(corp_candidates(data, name='도레이케미칼')), 2)                 # ambiguous: the caller must not pick one silently
        self.assertEqual(corp_candidates(data, name='없는회사'), []);self.assertEqual(corp_candidates(data, name='도레이'), [])    # exact names only, never substrings
        with self.assertRaises(ValueError):corp_candidates(b'not a zip', stock_code='298040')


class KeyTests(unittest.TestCase):
    def test_the_key_comes_only_from_the_environment_and_is_validated_without_being_echoed(self):
        self.assertEqual(key_from_env({'OPENDART_API_KEY': KEY}), KEY)
        for env in ({}, {'OPENDART_API_KEY': ''}, {'OPENDART_API_KEY': 'short'}, {'OPENDART_API_KEY': ' ' * 40}):
            with self.assertRaises(ValueError) as raised:key_from_env(env)
            self.assertNotIn('short', str(raised.exception))


class PlanTests(unittest.TestCase):
    def test_the_first_call_plan_is_small_explicit_and_lists_every_request(self):
        plan = plan_first_call(today='2026-11-04')
        self.assertLessEqual(plan['max_requests'], 30);self.assertGreaterEqual(plan['min_interval_seconds'], 1)
        hosts = {r['host'] for r in plan['requests']};self.assertEqual(hosts, {'opendart.fss.or.kr', 'api.stock.naver.com'})
        self.assertEqual(sum(1 for r in plan['requests'] if r['kind'] == 'document'), 1)
        self.assertTrue(all('crtfc_key' not in json.dumps(r) for r in plan['requests']))
        self.assertIn('.local/pit-pilot', plan['storage']);self.assertEqual(plan['viewer_scraping'], False)
        self.assertLessEqual(len(plan['requests']), plan['max_requests'])


if __name__ == '__main__':unittest.main()
