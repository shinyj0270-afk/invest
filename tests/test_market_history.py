import copy
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from investment.fixture import make_fixture
from investment.market_history import benchmark_calendar, fetch_history, parse_history


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self): return self
    def __exit__(self, *args): pass
    def raise_for_status(self): pass
    def iter_content(self, size): yield self.payload


class MarketHistoryTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 24, 10, tzinfo=ZoneInfo('Asia/Seoul'))
        self.start = '2025-01-01'; self.end = '2026-09-23'
        self.data = [dict(localDate=day.replace('-', ''), closePrice=100+i,
            openPrice=100+i, highPrice=102+i, lowPrice=99+i, accumulatedTradingVolume=1000)
            for i, day in enumerate(make_fixture()['sessions'])]
        self.payload = json.dumps(self.data).encode()
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name)

    def parsed(self, data=None, symbol='005930', kind='item'):
        return parse_history(json.dumps(self.data if data is None else data).encode(), symbol=symbol,
            kind=kind, start=self.start, end=self.end, fetched_at=self.now)

    def fetch(self, client, **kwargs):
        return fetch_history('005930', start=self.start, end=self.end, cache_dir=self.cache,
                             now=self.now, session=client, **kwargs)

    def test_completed_daily_prices_keep_honest_provenance(self):
        original = copy.deepcopy(self.data); result = self.parsed()
        self.assertEqual(len(result['prices']), 280)
        self.assertEqual(result['price_date'], self.end)
        self.assertTrue(all(p['final'] is True for p in result['prices']))
        self.assertTrue(all(p['adjustment_basis'] == 'naver_chart_adjusted' for p in result['prices']))
        self.assertTrue(all(p['turnover'] is None for p in result['prices']))
        self.assertIn('당일 제외', result['source']['final_basis'])
        self.assertIn('미공개', result['source']['adjustment_note'])
        self.assertEqual(self.data, original)

    def test_today_and_future_are_excluded_even_if_provider_sends_them(self):
        data = copy.deepcopy(self.data)
        data.extend([dict(data[-1], localDate='20260924', closePrice=9999),
                     dict(data[-1], localDate='20990101', closePrice=99999)])
        result = self.parsed(data)
        self.assertEqual(len(result['prices']), len(self.data))
        self.assertEqual(result['source']['excluded_outside_completed_window'], 2)
        with self.assertRaisesRegex(ValueError, '당일'):
            fetch_history('005930', start=self.start, end='2026-09-24', cache_dir=self.cache, now=self.now)

    def test_bad_dates_values_or_ohlc_fail_instead_of_filling(self):
        for mutate in ('duplicate', 'nan', 'negative', 'ohlc'):
            with self.subTest(mutate=mutate):
                data = copy.deepcopy(self.data)
                if mutate == 'duplicate': data[1]['localDate'] = data[0]['localDate']
                if mutate == 'nan': data[1]['closePrice'] = float('nan')
                if mutate == 'negative': data[1]['accumulatedTradingVolume'] = -1
                if mutate == 'ohlc': data[1]['highPrice'] = 1
                with self.assertRaises(ValueError): self.parsed(data)

    def test_suspension_observation_does_not_invent_ohlc(self):
        data = copy.deepcopy(self.data)
        data[-1].update(openPrice=0, highPrice=0, lowPrice=0, accumulatedTradingVolume=0)
        bar = self.parsed(data)['prices'][-1]
        self.assertTrue(bar['no_trade'])
        self.assertIsNone(bar['high'])
        self.assertIsNone(bar['low'])
        self.assertEqual(bar['close'], data[-1]['closePrice'])

    def test_small_adjustment_rounding_conflict_keeps_close_and_withholds_ohlc(self):
        data = copy.deepcopy(self.data)
        data[-1].update(closePrice=1000, openPrice=990, highPrice=999, lowPrice=980)
        bar = self.parsed(data)['prices'][-1]
        self.assertEqual(bar['close'], 1000)
        self.assertTrue(bar['ohl_inconsistent'])
        self.assertIsNone(bar['open'])
        self.assertIsNone(bar['high'])

    def test_zero_ohl_with_reported_volume_is_missing_not_invented(self):
        data = copy.deepcopy(self.data)
        data[-1].update(openPrice=0, highPrice=0, lowPrice=0, accumulatedTradingVolume=10)
        bar = self.parsed(data)['prices'][-1]
        self.assertFalse(bar['no_trade'])
        self.assertTrue(bar['ohl_unavailable'])
        self.assertIsNone(bar['low'])

    def test_exact_range_cache_resumes_without_network(self):
        client = Mock(); client.get.return_value = Response(self.payload)
        first = self.fetch(client); second = self.fetch(client)
        self.assertEqual(first, second)
        self.assertEqual(client.get.call_count, 1)
        self.assertEqual(len(list(self.cache.glob('*.json'))), 2)
        self.assertEqual(client.get.call_args.kwargs['params']['endDateTime'], '202609232359')

    def test_hash_corruption_refetches_and_invalid_response_keeps_prior_files(self):
        client = Mock(); client.get.return_value = Response(self.payload)
        self.fetch(client)
        raw = next(p for p in self.cache.glob('*.json') if '.meta.' not in p.name)
        raw.write_bytes(b'corrupt')
        self.fetch(client)
        self.assertEqual(client.get.call_count, 2)
        before = {p.name: p.read_bytes() for p in self.cache.iterdir()}
        client.get.return_value = Response(b'{"error":"unavailable"}')
        with self.assertRaises(ValueError): self.fetch(client, force=True)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.cache.iterdir()})

    def test_consensus_is_labeled_source_sessions_not_official_calendar(self):
        histories = {symbol: self.parsed(symbol=symbol, kind='index') for symbol in ('KOSPI', 'KOSDAQ')}
        result = benchmark_calendar(histories)
        self.assertEqual(result['calendar_basis'], 'naver_index_sessions')
        self.assertEqual(len(result['sessions']), 280)
        self.assertEqual(result['valid_through'], self.end)
        self.assertEqual(histories['KOSPI']['prices'][0]['adjustment_basis'], 'index_level')
        del histories['KOSDAQ']['prices'][-60]
        with self.assertRaisesRegex(ValueError, '불일치'): benchmark_calendar(histories)

    def test_short_index_history_cannot_establish_rank_calendar(self):
        histories = {symbol: self.parsed(data=self.data[-252:], symbol=symbol, kind='index')
                     for symbol in ('KOSPI', 'KOSDAQ')}
        with self.assertRaisesRegex(ValueError, '253'): benchmark_calendar(histories)

    def test_code_path_and_timezone_validation(self):
        self.assertEqual(self.parsed(symbol='0000A0')['symbol'], '0000A0')
        with self.assertRaises(ValueError): self.parsed(symbol='../005930')
        with self.assertRaises(ValueError): self.parsed(symbol='NASDAQ', kind='index')
        with self.assertRaises(ValueError): parse_history(self.payload, symbol='005930', kind='item',
            start=self.start, end=self.end, fetched_at=self.now.replace(tzinfo=None))


if __name__ == '__main__':
    unittest.main()
