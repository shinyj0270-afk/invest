"""Bound the live overview independently of per-company historical series."""
import copy
import json
import time
import unittest
from unittest.mock import patch
from investment.fixture import make_fixture
from investment.financial_table import INPUTS
from investment.workspace_export import export_workspace


def synthetic_market(count=1369):
    snapshot=make_fixture();snapshot['meta']['data_mode']='user_input'
    bars=copy.deepcopy(snapshot['companies'][0]['prices'])
    for bar in bars:bar.update(final=True,venue='KRX',adjustment_basis='naver_chart_adjusted',volume=100000)
    indices={}
    for market in ('KOSPI','KOSDAQ'):
        prices=copy.deepcopy(bars)
        for bar in prices:bar['adjustment_basis']='index_level'
        indices[market]=dict(symbol=market,kind='index',prices=prices)
    rows=[];histories={};financials={}
    for i in range(count):
        code=f'{910000+i:06d}';name=f'가상 대규모 기업 {i}'
        rows.append(dict(code=code,name=name,market='KOSPI',industry=f'가상 업종 {i%20}',
            eligibility='candidate',security_type='ordinary',analysis_profile='general',
            source='합성 검증 · 실제 관측 아님',metrics={'market_cap_eok':1200+i,'price':10000}))
        histories[code]=dict(symbol=code,kind='item',prices=bars)
        periods=[]
        for year in [2023,2024,2025,2026]:
            for month in [3,6,9,12]:
                if (year,month)>(2026,6):continue
                end=f'{year}-{month:02d}-'+('31' if month in (3,12) else '30')
                available=f'{year+1}-03-31' if month==12 else f'{year}-{month+2:02d}-14'
                periods.append(dict(period_end=end,available_at=available,basis='CFS',cadence='quarter',
                    source='가상 DART 검증 자료',source_url='https://dart.fss.or.kr/report/viewer.do?rcpNo=20260814000001',
                    **{field:1e10 for field in INPUTS}))
        financials[code]=dict(code=code,name=name,market='KOSPI',periods=periods,notes=[])
    cache=dict(universe=dict(schema_version='naver-universe-0.1',companies=rows,pagination_complete=True,
        retrieved_on='2026-09-23',errors=[]),history=dict(benchmarks=indices,histories=histories,errors=[]))
    return snapshot,cache,financials


class DashboardPayloadTests(unittest.TestCase):
    def test_large_live_bootstrap_is_bounded_and_details_are_deferred(self):
        snapshot,cache,financials=synthetic_market();before=copy.deepcopy(snapshot)
        live={'token':'synthetic','lazy_company_views':True,'lazy_holdings_frame':True,'financial_as_of':'2026-10-07'}
        started=time.perf_counter();html=export_workspace(snapshot,market_cache=cache,financials=financials,live=live)
        elapsed=time.perf_counter()-started
        payload=json.JSONDecoder().raw_decode(html.split('const WORKSPACE_DATA=',1)[1])[0]
        self.assertLess(len(html.encode()),12*1024*1024)
        self.assertEqual(payload['financial_tables'],{});self.assertEqual(payload['company_details'],{})
        self.assertIsNone(payload['detail_html']);self.assertNotIn('snapshot',payload)
        self.assertEqual(len(payload['discovery']['snapshot']['companies']),1369)
        for row in payload['discovery']['snapshot']['companies']:
            self.assertTrue(row.get('common_financial'))
            self.assertNotIn('prices',row);self.assertNotIn('trend_prices',row)
        self.assertTrue(all(not facts['technical']['series'] for facts in payload['discovery']['research']['rows'].values()))
        self.assertEqual(snapshot,before)
        print(f'SYNTHETIC 1369-company live overview: {len(html.encode()):,} bytes, {elapsed:.3f}s; common screener metrics retained, details/frame deferred')

    def test_static_export_still_embeds_complete_legacy_and_company_views(self):
        html=export_workspace(make_fixture())
        payload=json.JSONDecoder().raw_decode(html.split('const WORKSPACE_DATA=',1)[1])[0]
        self.assertIsInstance(payload['detail_html'],str)
        self.assertEqual(len(payload['financial_tables']),8)
        self.assertEqual(len(payload['company_details']),8)
        self.assertIn('snapshot',payload)
        self.assertNotIn('wire_format',payload)


if __name__=='__main__':unittest.main()
