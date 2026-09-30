import copy
import json
import re
import unittest
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace


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
