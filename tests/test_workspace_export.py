import copy
import json
import re
import unittest
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace, market_summary
from investment.naver_reference import parse_reference


class WorkspaceExportTests(unittest.TestCase):
    def test_live_lazy_charts_keep_screener_metrics_and_offline_series(self):
        from unittest.mock import patch
        snapshot=make_fixture();code=snapshot['companies'][0]['code']
        discovered=dict(snapshot=snapshot,research={'rows':{code:{'technical':{'series':[{'date':'2026-09-23','close':100}],'price_strength':{'score':88}}}}})
        def payload(live):
            with patch('investment.workspace_export.build_discovery',return_value=copy.deepcopy(discovered)):
                html=export_workspace(snapshot,live=live)
            return json.JSONDecoder().raw_decode(html.split('const WORKSPACE_DATA=',1)[1])[0]
        self.assertEqual(len(payload(None)['discovery']['research']['rows'][code]['technical']['series']),1)
        technical=payload({'lazy_company_views':True})['discovery']['research']['rows'][code]['technical']
        self.assertEqual(technical['series'],[])
        self.assertTrue(technical['series_pending'])
        self.assertEqual(technical['price_strength']['score'],88)

    def test_market_summary_requires_completed_matching_date_and_keeps_source(self):
        snap=make_fixture();date=snap['meta']['price_date']
        snap['benchmarks']['KOSDAQ']=copy.deepcopy(snap['benchmarks']['KOSPI'])
        for market,bars in snap['benchmarks'].items():
            for b in bars:b['final']=True
        before=copy.deepcopy(snap)
        summary=market_summary(snap,None,date)
        self.assertEqual(len(summary),2)
        for r in summary:
            a,b=snap['benchmarks'][r['market']][-2:]
            self.assertAlmostEqual(r['change_pct'],(b['close']/a['close']-1)*100)
            self.assertEqual(r['date'],date)
        self.assertEqual(snap,before)
        snap['benchmarks']['KOSPI'][-1]['final']=False
        self.assertEqual([r['market'] for r in market_summary(snap,None,date)],['KOSDAQ'])
        self.assertEqual(market_summary(snap,None,'2099-01-01'),[])

    def test_market_summary_reads_validated_public_cache_and_rejects_bad_calendar(self):
        snap=make_fixture();bars=copy.deepcopy(snap['benchmarks']['KOSPI'])
        for b in bars:b.update(final=True,venue='KRX',adjustment_basis='index_level')
        cache={'history':{'benchmarks':{m:dict(symbol=m,kind='index',prices=copy.deepcopy(bars),source={'url':'https://example.com/'+m}) for m in ('KOSPI','KOSDAQ')}}}
        results=market_summary(snap,cache,snap['meta']['price_date'])
        self.assertEqual(len(results),2)
        self.assertEqual(results[1]['source']['url'],'https://example.com/KOSDAQ')
        cache['history']['benchmarks']['KOSDAQ']['prices'].pop()
        self.assertEqual(market_summary(snap,cache,snap['meta']['price_date']),[])

    def test_self_contained_fixture_preserves_source_and_mode(self):
        snapshot=make_fixture(); before=copy.deepcopy(snapshot)
        html=export_workspace(snapshot)
        payload=json.loads(re.search(r'const WORKSPACE_DATA=(.*?);</script>',html,re.S).group(1))
        self.assertEqual(payload['snapshot'],before)
        self.assertEqual(snapshot,before)
        self.assertIn('const INVESTMENT_LIVE=null;',html)
        self.assertNotIn('src="http',html)
        self.assertNotIn('INVESTMENT_INITIAL_HOLDINGS=',html)
        self.assertNotIn('Object.assign(window,{"INVESTMENT_HOLDINGS_INPUT"',payload['detail_html'])

    def test_script_delimiters_and_template_tokens_are_data(self):
        snapshot=make_fixture()
        name='</script><script>window.PWNED=1</script> /*WORKSPACE_JS*/'
        snapshot['companies'][0]['name']=name
        html=export_workspace(snapshot)
        self.assertNotIn(name,html)
        payload=json.loads(re.search(r'const WORKSPACE_DATA=(.*?);</script>',html,re.S).group(1))
        self.assertEqual(payload['snapshot']['companies'][0]['name'],name)

    def test_real_mode_links_empty_holdings_with_observed_price(self):
        snapshot=make_fixture();snapshot['meta']['data_mode']='user_input'
        for bar in snapshot['companies'][0]['prices']:
            bar.update(final=True,venue='KRX',adjustment_basis='unadjusted')
        html=export_workspace(snapshot)
        payload=json.loads(re.search(r'const WORKSPACE_DATA=(.*?);</script>',html,re.S).group(1))
        values=json.loads(re.search(r'Object.assign\(window,(.*?)\);</script>',payload['detail_html'],re.S).group(1))
        self.assertEqual(values['INVESTMENT_HOLDINGS_INPUT']['holdings'],[])
        self.assertTrue(values['INVESTMENT_HOLDINGS_INPUT']['research'][0]['price_krw']>0)

    def test_rejects_credentials(self):
        snapshot=make_fixture();snapshot['meta']['api_key']='not-a-real-key'
        with self.assertRaises(ValueError): export_workspace(snapshot)

    def test_future_metrics_are_missing_in_all_analysis_views(self):
        snapshot=make_fixture();snapshot['meta']['financial_period']='2099Q1'
        before=copy.deepcopy(snapshot)
        html=export_workspace(snapshot)
        payload=json.loads(re.search(r'const WORKSPACE_DATA=(.*?);</script>',html,re.S).group(1))
        self.assertEqual(payload['snapshot'],before)
        self.assertEqual(snapshot,before)
        self.assertIsNone(payload['analysis_snapshot']['companies'][0]['metrics']['roe_pct'])
        values=json.loads(re.search(r'Object.assign\(window,(.*?)\);</script>',payload['detail_html'],re.S).group(1))
        self.assertIsNone(values['INVESTMENT_INITIAL_SNAPSHOT']['companies'][0]['metrics']['roe_pct'])
        self.assertEqual(payload['research']['rs_choice'],'price_primary_excess_secondary')

    def test_live_financial_date_advances_without_relabelling_old_prices(self):
        snapshot=make_fixture();row=snapshot['companies'][0]
        supplemental={row['code']:dict(code=row['code'],name=row['name'],market=row['market'],periods=[
            dict(period_end='2026-09-30',available_at='2026-11-15',basis='CFS',cadence='quarter',
                 revenue=100e8,operating_profit=15e8,net_income=10e8,source='DART')])}
        def payload(live):
            html=export_workspace(snapshot,financials=supplemental,live=live)
            return json.loads(re.search(r'const WORKSPACE_DATA=(.*?);</script>',html,re.S).group(1))
        old=payload(None);new=payload({'financial_as_of':'2026-11-16'})
        def ends(data):return [c['period_end'] for g in data['financial_tables'][row['code']]['groups'] for c in g['columns']]
        self.assertNotIn('2026-09-30',ends(old))
        self.assertIn('2026-09-30',ends(new))
        self.assertEqual(new['analysis_snapshot']['meta']['price_date'],snapshot['meta']['price_date'])

    def test_naver_reference_date_never_overwrites_primary_snapshot(self):
        snapshot=make_fixture();snapshot['meta']['data_mode']='user_input'
        row=snapshot['companies'][0];before=copy.deepcopy(snapshot)
        ref=parse_reference(dict(itemcode=row['code'],itemname=row['name'],type='ST',
            tradeTime='20260930130000',nowPrice=12000,per=12,pbr=2,eps=1000,bps=6000),
            row['code'],'2026-09-30T13:01:00+09:00')
        ref.update(private_note='PRIVATE SENTINEL',url='https://evil.example/',status='verified')
        html=export_workspace(snapshot,references={row['code']:ref})
        payload=json.loads(re.search(r'const WORKSPACE_DATA=(.*?);</script>',html,re.S).group(1))
        self.assertEqual(payload['snapshot'],before)
        self.assertEqual(snapshot,before)
        self.assertIsNone(payload['analysis_snapshot']['companies'][0]['metrics']['per'])
        result=payload['references'][row['code']]
        self.assertEqual(result['per'],12)
        self.assertFalse(result['same_price_date'])
        self.assertFalse(result['final'])
        self.assertEqual(result['status'],'reference_only')
        self.assertNotIn('PRIVATE SENTINEL',html)
        self.assertNotIn('https://evil.example/',html)
