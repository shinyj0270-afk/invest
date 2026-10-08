import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import date, timedelta

from investment.market_discovery import build_discovery, technical,discovery_candidate,load_market_cache,MarketCacheReader,MIN_DISCOVERY_CAP_EOK
from concurrent.futures import ThreadPoolExecutor


def bars(days, *, index=False, start=100):
    return [dict(date=d, close=start+i, open=start+i, high=start+i+1, low=start+i-1,
        volume=1000, turnover=None, final=True, venue='KRX', no_trade=False,
        adjustment_basis='index_level' if index else 'naver_chart_adjusted')
        for i, d in enumerate(days)]


class MarketDiscoveryTests(unittest.TestCase):
    def test_runtime_reader_reuses_stable_sources_and_refreshes_replacements(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'work/market-expansion';folder.mkdir(parents=True)
            (folder/'universe.json').write_text(json.dumps(dict(schema_version='naver-universe-0.1',companies=[])),encoding='utf-8')
            history=folder/'histories.json'
            history.write_text(json.dumps(dict(histories={'A':{'prices':[{'close':100}]},'B':{'prices':[{'close':200}]}})),encoding='utf-8')
            reader=MarketCacheReader();snap=dict(meta=dict(data_mode='user_input'))
            with patch('investment.market_discovery.load_local',return_value=dict(data_dir=root,profile='work')),patch('investment.market_discovery.load_market_cache',wraps=load_market_cache) as loader:
                with ThreadPoolExecutor(max_workers=6) as pool:
                    values=list(pool.map(lambda _:reader.get(root,snap,codes=['A']),range(6)))
                self.assertEqual(loader.call_count,1)
                self.assertEqual(set(values[0]['history']['histories']),{'A'})
                values[0]['history']['histories']['A']['prices'][0]['close']=999
                self.assertEqual(reader.get(root,snap,codes=['A'])['history']['histories']['A']['prices'][0]['close'],100)
                replacement=folder/'new.json';replacement.write_text(json.dumps(dict(histories={'A':{'prices':[{'close':333}]}})),encoding='utf-8');replacement.replace(history)
                self.assertEqual(reader.get(root,snap,codes=['A'])['history']['histories']['A']['prices'][0]['close'],333)
                self.assertEqual(loader.call_count,2)
                history.write_text('invalid',encoding='utf-8');self.assertIsNone(reader.get(root,snap))
                self.assertIsNone(reader.get(root,dict(meta=dict(data_mode='fixture'))))

    def test_runtime_reader_rejects_structurally_invalid_json_without_old_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'work/market-expansion';folder.mkdir(parents=True)
            universe=folder/'universe.json';history=folder/'histories.json';quote=folder/'latest-quotes.json'
            valid={'schema_version':'naver-universe-0.1','companies':[]};snap={'meta':{'data_mode':'user_input'}}
            with patch('investment.market_discovery.load_local',return_value=dict(data_dir=root,profile='work')):
                reader=MarketCacheReader();universe.write_text(json.dumps(valid));history.write_text('{}')
                self.assertIsNotNone(reader.get(root,snap))
                for malformed in [[1],None,3,{'histories':[]},{'benchmarks':None},{'histories':{'A':[]}}]:
                    history.write_text(json.dumps(malformed));self.assertIsNone(reader.get(root,snap))
                history.write_text('{}')
                for malformed in [[],None,3,dict(valid,companies=[[]])]:
                    universe.write_text(json.dumps(malformed));self.assertIsNone(reader.get(root,snap))
                universe.write_text(json.dumps(valid));quote.write_text('[1]');self.assertIsNone(reader.get(root,snap))

    def test_old_cache_exclusions_are_reapplied_without_rewriting_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'work'/'market-expansion';folder.mkdir(parents=True)
            rows=[dict(code='90000K',name='가상4우(전환)',eligibility='candidate',industry='기계',source_security_type='ST'),
                  dict(code='900000',name='가상보통',eligibility='candidate',industry='기계',source_security_type='ST')]
            path=folder/'universe.json';path.write_text(json.dumps(dict(schema_version='naver-universe-0.1',companies=rows)),encoding='utf-8')
            original=path.read_bytes()
            with patch('investment.market_discovery.load_local',return_value=dict(data_dir=root,profile='work')):
                cache=load_market_cache(root,dict(meta=dict(data_mode='user_input')))
            self.assertEqual([r['eligibility'] for r in cache['universe']['companies']],['excluded','candidate'])
            self.assertEqual(path.read_bytes(),original)

    def test_market_cap_boundary_and_fresh_identity(self):
        row=dict(name='기업',market='KOSPI',eligibility='candidate',metrics={})
        self.assertEqual(MIN_DISCOVERY_CAP_EOK,1500)
        for cap,expected in [(1499.9,False),(1500,False),(1500.01,True),(None,False)]:
            row['metrics']['market_cap_eok']=cap
            self.assertEqual(discovery_candidate(row),expected)
        row['metrics']['market_cap_eok']=2000
        self.assertFalse(discovery_candidate(row,dict(name='기업',market='KOSPI',market_cap_eok=1500)))
        self.assertTrue(discovery_candidate(row,dict(name='다른 기업',market='KOSPI',market_cap_eok=1500)))

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
                revenue_growth_pct=4, debt_ratio_pct=30, per=9, pbr=1.1, market_cap_eok=2000), trading_status={})
        excluded = dict(candidate, code='654321', name='금융기업', eligibility='excluded')
        cache = dict(universe=dict(schema_version='naver-universe-0.1', companies=[candidate, excluded],
            pagination_complete=True, errors=[], retrieved_on='2026-09-30'), history={})
        result = build_discovery(base, research, cache)
        self.assertEqual([r['code'] for r in result['snapshot']['companies']], ['123456'])
        self.assertTrue(result['snapshot']['companies'][0]['discovery_allowed'])
        self.assertIn('1,500억원 초과', result['snapshot']['meta']['discovery_note'])
        row = result['snapshot']['companies'][0]
        self.assertFalse(row['legacy_available'])
        self.assertEqual(row['metric_details']['per']['source'], candidate['source'])
        self.assertIsNone(row['metric_details']['per']['period'])
        self.assertEqual(result['coverage']['total'], 2)
        self.assertEqual(result['coverage']['candidates'], 1)
        self.assertEqual(result['coverage']['both_valuation'], 1)
        candidate['metrics']['market_cap_eok']=1500
        limited=build_discovery(base,research,cache)
        self.assertFalse(limited['snapshot']['companies'][0]['discovery_allowed'])
        self.assertEqual(limited['coverage']['discovery_candidates'],0)
        candidate['metrics']['market_cap_eok']=2000
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
