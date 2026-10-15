"""Synthetic checks for the five-month new-listing seasoning rule; no live requests."""
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from investment.listing_seasoning import (add_months, parse_listing_date, apply_seasoning,
    collect_listing_dates, codes_needing_dates, read_listing_dates)
from investment.market_discovery import load_market_cache

SESSIONS = ['2025-01-17', '2025-01-20', '2026-05-20', '2026-10-14']
HISTORY = dict(calendar=dict(sessions=SESSIONS, valid_through='2026-10-14'), histories={
    'OLD000': dict(prices=[dict(date='2025-01-17')]),
    'NEW000': dict(prices=[dict(date='2026-05-20')]),
})


def row(code, **changes):
    return dict(dict(code=code, name='가상'+code, eligibility='candidate', exclusion_reasons=[]), **changes)


class ListingSeasoningTests(unittest.TestCase):
    def test_add_months_clamps_month_end(self):
        self.assertEqual(add_months(date(2026, 5, 20), 5), date(2026, 10, 20))
        self.assertEqual(add_months(date(2025, 9, 30), 5), date(2026, 2, 28))
        self.assertEqual(add_months(date(2026, 10, 31), 4), date(2027, 2, 28))

    def test_parse_official_listing_date(self):
        self.assertEqual(parse_listing_date('설립일 2012/12/28&nbsp;(상장일: 2026/09/30) 대표'), date(2026, 9, 30))
        self.assertIsNone(parse_listing_date('상장일 정보 없음'))
        self.assertIsNone(parse_listing_date('(상장일: 2026/13/40)'))

    def test_rule_uses_official_date_then_long_history_then_waits(self):
        dates = {'NEW000': dict(listed_on='2026-05-20'), 'NEW001': dict(listed_on='2026-05-14')}
        rows = [row('OLD000'), row('NEW000'), row('NEW001'), row('SHORT0'), row('EXCL00', eligibility='excluded')]
        HISTORY['histories']['SHORT0'] = dict(prices=[dict(date='2026-05-20')])
        result = {r['code']: r for r in apply_seasoning(rows, dates, HISTORY, date(2026, 10, 15))}
        self.assertEqual(result['OLD000']['eligibility'], 'candidate')
        self.assertEqual(result['NEW001']['eligibility'], 'candidate')
        young = result['NEW000']
        self.assertEqual((young['eligibility'], young['seasoning']['eligible_on']), ('excluded', '2026-10-20'))
        self.assertIn('신규 상장 5개월 미경과 · 상장 2026-05-20 · 편입 가능 2026-10-20', young['exclusion_reasons'])
        self.assertEqual(result['SHORT0']['seasoning']['status'], 'listing_date_pending')
        self.assertEqual(result['EXCL00']['eligibility'], 'excluded')
        self.assertNotIn('seasoning', result['EXCL00'])
        self.assertEqual(rows[1]['eligibility'], 'candidate')
        self.assertEqual(apply_seasoning([row('NEW000')], dates, HISTORY, date(2026, 10, 20))[0]['eligibility'], 'candidate')

    def test_without_history_window_rule_is_not_applied(self):
        self.assertEqual(apply_seasoning([row('ANY000')], {}, {}, date(2026, 10, 15))[0]['eligibility'], 'candidate')

    def test_only_short_or_missing_history_needs_official_date(self):
        rows = [row('OLD000'), row('NEW000'), row('MISS00'), row('DONE00'), row('EXCL00', eligibility='excluded')]
        self.assertEqual(codes_needing_dates(rows, HISTORY, {'DONE00': {}}), ['NEW000', 'MISS00'])

    def test_collection_keeps_cache_and_records_failures_without_dates(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            calls = []
            def fetch(code):
                calls.append(code)
                if code == 'BAD000': raise ValueError('공개 조회 HTTP 500')
                return dict(listed_on='2026-05-20', source='FnGuide 기업개요', url='u', retrieved_at='2026-10-15T15:00:00+09:00')
            summary = collect_listing_dates(folder, ['NEW000', 'BAD000'], fetch=fetch, pace=0)
            self.assertEqual((summary['collected'], summary['failed']), (1, 1))
            self.assertEqual(set(read_listing_dates(folder)), {'NEW000'})
            collect_listing_dates(folder, ['NEW000'], fetch=fetch, pace=0)
            self.assertEqual(calls, ['NEW000', 'BAD000'])
            (folder/'listing-dates.json').write_text(json.dumps(dict(schema_version='x', companies={})), encoding='utf-8')
            with self.assertRaises(ValueError):
                read_listing_dates(folder)

    def test_market_cache_applies_rule_without_rewriting_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); folder = root/'work'/'market-expansion'; folder.mkdir(parents=True)
            rows = [dict(code='OLD000', name='가상기존', eligibility='candidate', industry='기계', source_security_type='ST'),
                    dict(code='NEW000', name='가상신규', eligibility='candidate', industry='기계', source_security_type='ST')]
            path = folder/'universe.json'
            path.write_text(json.dumps(dict(schema_version='naver-universe-0.1', companies=rows)), encoding='utf-8')
            (folder/'histories.json').write_text(json.dumps(dict(HISTORY, benchmarks={})), encoding='utf-8')
            (folder/'listing-dates.json').write_text(json.dumps(dict(schema_version='listing-dates-1',
                companies={'NEW000': dict(listed_on='2026-05-20', source='s', url='u', retrieved_at='t')})), encoding='utf-8')
            original = path.read_bytes()
            with patch('investment.market_discovery.load_local', return_value=dict(data_dir=root, profile='work')), \
                 patch('investment.market_discovery.today_kst', return_value=date(2026, 10, 15)):
                cache = load_market_cache(root, dict(meta=dict(data_mode='user_input')))
            self.assertEqual([r['eligibility'] for r in cache['universe']['companies']], ['candidate', 'excluded'])
            self.assertEqual(path.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
