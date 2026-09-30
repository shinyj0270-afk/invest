"""Synthetic public payloads; no network or actual market data in tests."""
import json
from pathlib import Path
import tempfile
import unittest

from investment.naver_reference import SCHEMA, fetch_references, load_cached_references, number, parse_reference, sanitize_references


class NaverReferenceTests(unittest.TestCase):
    def setUp(self):
        self.now = '2026-09-30T14:00:00+09:00'
        self.raw = dict(itemcode='900001', itemname='가상기업', type='ST', tradeTime='20260930133000',
            nowPrice='10,000', per='10', eps='1000', pbr='2', bps='5000', estimatedPer='3', estimatedEps='3000', marketStatus='OPEN')

    def test_current_reference_keeps_unknown_basis_and_excludes_forecasts(self):
        r = parse_reference(self.raw, '900001', self.now)
        self.assertEqual((r['per'], r['pbr'], r['price']), (10, 2, 10000))
        self.assertEqual(r['price_date'], '2026-09-30')
        self.assertEqual(r['status'], 'reference_only')
        self.assertFalse(r['final'])
        self.assertIsNone(r['financial_period'])
        self.assertIsNone(r['financial_basis'])
        self.assertEqual(r['raw_source_values']['estimatedPer'], 3)

    def test_loss_equity_zero_and_missing_do_not_look_cheap(self):
        for value in ('-1', '0', None, '-', 'N/A'):
            result = parse_reference(dict(self.raw, eps=value, bps=value), '900001', self.now)
            self.assertIsNone(result['per'])
            self.assertIsNone(result['pbr'])
        result = parse_reference(dict(self.raw, per=None, pbr=None), '900001', self.now)
        self.assertIsNone(result['per'])
        self.assertIsNone(result['pbr'])

    def test_numeric_bounds(self):
        for value in (True, float('nan'), float('inf'), 'Infinity', '1,2', '12배', [], {}, 10**1000):
            self.assertIsNone(number(value))
        self.assertEqual(number('-1,234.5'), -1234.5)

    def test_identity_type_and_future_rejected(self):
        for patch in (dict(itemcode='000000'), dict(type='ETF'), dict(tradeTime='20261001100000'), dict(tradeTime='20260230100000')):
            with self.assertRaises(ValueError):
                parse_reference(dict(self.raw, **patch), '900001', self.now)

    def test_fetch_one_request_and_failure_no_fallback(self):
        raw = self.raw
        class Response:
            status_code = 200
            content = b'{}'
            def json(self): return raw
        class Session:
            def __init__(self): self.urls = []
            def get(self, url, **kwargs): self.urls.append(url); return Response()
        session = Session()
        result = fetch_references(['900001', '900002'], session=session, now=self.now)
        self.assertEqual(len(session.urls), 2)
        self.assertEqual(set(result['companies']), {'900001'})
        self.assertEqual(set(result['errors']), {'900002'})
        with self.assertRaises(ValueError): fetch_references(['../secret'], session=session, now=self.now)

    def test_cache_only_real_identity_and_never_promotes_or_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'data/unknown/references/naver_reference.json'
            target.parent.mkdir(parents=True)
            record = parse_reference(self.raw, '900001', self.now)
            record.update(status='observed', financial_basis='CFS', url='https://evil.example/')
            target.write_text(json.dumps(dict(schema_version=SCHEMA, companies={'900001':record})), encoding='utf-8')
            snapshot = dict(meta=dict(data_mode='user_input', price_date='2026-09-23'), companies=[dict(code='900001',name='가상기업')])
            before = target.read_bytes()
            result = load_cached_references(root, snapshot)['900001']
            self.assertEqual(result['status'], 'reference_only')
            self.assertIsNone(result['financial_basis'])
            self.assertTrue(result['url'].startswith('https://stock.naver.com/'))
            self.assertFalse(result['same_price_date'])
            self.assertEqual(target.read_bytes(), before)
            snapshot['meta']['data_mode'] = 'fixture'
            self.assertEqual(load_cached_references(root, snapshot), {})
            snapshot['meta']['data_mode'] = 'user_input'
            snapshot['companies'][0]['name'] = '다른기업'
            self.assertEqual(load_cached_references(root, snapshot), {})

    def test_export_sanitizer_drops_private_extras_invalid_dates_and_urls(self):
        record = parse_reference(self.raw, '900001', self.now)
        record.update(api_key='synthetic-private', personal_holdings=[1], status='observed', final=True,
                      url='javascript:alert(1)', financial_basis='CFS')
        record['raw_source_values']['api_key'] = 'synthetic-private'
        snapshot = dict(meta=dict(data_mode='user_input', price_date='2026-09-23'),
                        companies=[dict(code='900001', name='가상기업')])
        cleaned = sanitize_references({'900001': record}, snapshot)['900001']
        self.assertNotIn('synthetic-private', json.dumps(cleaned))
        self.assertNotIn('personal_holdings', cleaned)
        self.assertFalse(cleaned['final'])
        self.assertEqual(cleaned['status'], 'reference_only')
        self.assertIsNone(cleaned['financial_basis'])
        record['price_time'] = 'not a date'
        self.assertEqual(sanitize_references({'900001': record}, snapshot), {})


if __name__ == '__main__':
    unittest.main()
