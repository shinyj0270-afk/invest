import copy
import json
import re
import unittest
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace
from investment.naver_reference import parse_reference


class WorkspaceExportTests(unittest.TestCase):
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
