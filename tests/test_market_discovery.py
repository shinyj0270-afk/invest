import unittest
from datetime import date, timedelta

from investment.market_discovery import build_discovery, technical,discovery_candidate


def bars(days, *, index=False, start=100):
    return [dict(date=d, close=start+i, open=start+i, high=start+i+1, low=start+i-1,
        volume=1000, turnover=None, final=True, venue='KRX', no_trade=False,
        adjustment_basis='index_level' if index else 'naver_chart_adjusted')
        for i, d in enumerate(days)]


class MarketDiscoveryTests(unittest.TestCase):
    def test_market_cap_boundary_and_fresh_identity(self):
        row=dict(name='기업',market='KOSPI',eligibility='candidate',metrics={})
        for cap,expected in [(849.9,False),(850,False),(850.01,True),(None,False)]:
            row['metrics']['market_cap_eok']=cap
            self.assertEqual(discovery_candidate(row),expected)
        row['metrics']['market_cap_eok']=1000
        self.assertFalse(discovery_candidate(row,dict(name='기업',market='KOSPI',market_cap_eok=850)))
        self.assertTrue(discovery_candidate(row,dict(name='다른 기업',market='KOSPI',market_cap_eok=850)))

    def test_source_sessions_compute_price_trend_without_claiming_liquidity(self):
        days = [(date(2025, 1, 1)+timedelta(days=i)).isoformat() for i in range(253)]
        calendar = dict(sessions=days, valid_through=days[-1])
        item = dict(kind='item', prices=bars(days))
        index = dict(kind='index', prices=bars(days, index=True, start=1000))
        value = technical(item, index, calendar)
        self.assertEqual(value['history_count'], 253)
        self.assertEqual(value['price_trend_status'], 'pass')
        self.assertEqual(value['status'], 'unknown')
        self.assertIn('거래대금', value['reason'])
        self.assertIsNotNone(value['rs126_pct'])
        self.assertIsNotNone(value['price_strength']['weighted_return_pct'])

    def test_candidate_only_and_metric_provenance_are_preserved(self):
        base = dict(meta=dict(data_mode='user_input', price_date='2026-09-23', as_of='2026-09-23'),
                    companies=[])
        research = dict(rows={}, rs_label='가격 추세 순위')
        candidate = dict(code='123456', name='후보기업', market='KOSPI', industry='화학',
            security_type='ordinary_candidate', analysis_profile='nonfinancial_candidate', eligibility='candidate',
            classification_note='후보', source='Npay 증권 공개 시장 목록', observed_on='2026-09-30',
            metric_basis='기간 미명시', derived_metrics={}, metrics=dict(roe_pct=12, operating_margin_pct=8,
                revenue_growth_pct=4, debt_ratio_pct=30, per=9, pbr=1.1, market_cap_eok=1000), trading_status={})
        excluded = dict(candidate, code='654321', name='금융기업', eligibility='excluded')
        cache = dict(universe=dict(schema_version='naver-universe-0.1', companies=[candidate, excluded],
            pagination_complete=True, errors=[], retrieved_on='2026-09-30'), history={})
        result = build_discovery(base, research, cache)
        self.assertEqual([r['code'] for r in result['snapshot']['companies']], ['123456'])
        row = result['snapshot']['companies'][0]
        self.assertFalse(row['legacy_available'])
        self.assertEqual(row['metric_details']['per']['source'], candidate['source'])
        self.assertIsNone(row['metric_details']['per']['period'])
        self.assertEqual(result['coverage']['total'], 2)
        self.assertEqual(result['coverage']['candidates'], 1)
        self.assertEqual(result['coverage']['both_valuation'], 1)
        candidate['metrics']['market_cap_eok']=850
        limited=build_discovery(base,research,cache)
        self.assertFalse(limited['snapshot']['companies'][0]['discovery_allowed'])
        self.assertEqual(limited['coverage']['discovery_candidates'],0)
        candidate['metrics']['market_cap_eok']=1000
        cache['quotes']={'quotes':{'123456':dict(code='123456',name='후보기업',market='KOSPI',price=999,
            retrieved_at='2026-10-02T10:00:00+09:00',final=False)}}
        refreshed=build_discovery(base,research,cache)
        self.assertEqual(refreshed['snapshot']['companies'][0]['latest_quote']['price'],999)
        self.assertEqual(refreshed['snapshot']['companies'][0]['metrics']['per'],9)
        self.assertEqual(refreshed['research']['rows']['123456']['technical'],result['research']['rows']['123456']['technical'])
        cache['quotes']['quotes']['123456']['name']='식별 다른 기업'
        self.assertNotIn('latest_quote',build_discovery(base,research,cache)['snapshot']['companies'][0])

    def test_fixture_and_missing_cache_do_not_gain_public_rows(self):
        self.assertIsNone(build_discovery({'meta': {'data_mode': 'fixture'}}, {}, {}))
        self.assertIsNone(build_discovery({'meta': {'data_mode': 'user_input'}}, {}, None))

    def test_price_rank_population_is_separate_for_each_market(self):
        days = [(date(2025, 1, 1)+timedelta(days=i)).isoformat() for i in range(253)]
        companies = []
        item_histories = {}
        for market, prefix in [('KOSPI', '1'), ('KOSDAQ', '2')]:
            for i in range(5):
                code = prefix+str(i).zfill(5)
                companies.append(dict(code=code, name=code, market=market, industry='화학',
                    security_type='ordinary_candidate', analysis_profile='nonfinancial_candidate', eligibility='candidate',
                    source='공개', observed_on='2026-09-30', metrics={}, derived_metrics={}, trading_status={}))
                item_histories[code] = dict(symbol=code, kind='item', prices=bars(days, start=100+i*100))
        benchmark = lambda symbol: dict(symbol=symbol, kind='index', prices=bars(days, index=True, start=1000),
                                        source={'url': 'https://example.com/'+symbol})
        cache = dict(universe=dict(schema_version='naver-universe-0.1', companies=companies,
            pagination_complete=True, errors=[], retrieved_on='2026-09-30'),
            history=dict(benchmarks={m: benchmark(m) for m in ('KOSPI','KOSDAQ')}, histories=item_histories, errors=[]))
        result = build_discovery(dict(meta={'data_mode':'user_input','price_date':'2026-09-23','as_of':'2026-09-23'},companies=[]),
                                 dict(rows={},rs_label='가격 추세 순위'),cache)
        for facts in result['research']['rows'].values():
            self.assertEqual(facts['technical']['price_strength']['eligible_count'], 5)
            self.assertEqual(facts['technical']['price_strength']['universe_count'], 5)
        self.assertEqual(result['coverage']['rs_ready_by_market'], {'KOSPI':5,'KOSDAQ':5})


if __name__ == '__main__':
    unittest.main()
