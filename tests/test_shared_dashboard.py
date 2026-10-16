import gzip
import json
import tempfile
import unittest
from datetime import datetime,timedelta
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock,patch

from investment.shared_dashboard import (pack,unpack,install,cached,open_home,public_snapshot,
                                         ResultRepository,export_company)
from investment.fixture import make_fixture


def result_html():
    # Synthetic contract, explicitly isolated from every actual-mode store.
    payload={'analysis_snapshot':{'meta':{'data_mode':'user_input','price_date':'2026-09-23'}},
             'detail_html':None,'company_details':{'900000':{'name':'synthetic result'}}}
    return '<html><body><script>const INVESTMENT_LIVE=null;const WORKSPACE_DATA='+json.dumps(payload)+';</script></body></html>'


class SharedDashboardTests(unittest.TestCase):
    def bundle(self,**kwargs):
        return pack(result_html(),source_build='0'*64,**kwargs)

    def home(self,root):
        (root/'config').mkdir()
        (root/'config/local.json').write_text(json.dumps(dict(profile='home')),encoding='utf-8')

    def test_hash_and_corruption_are_checked_before_replacing_good_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);manifest,blob=self.bundle();path=install(root,manifest,blob)
            before=(root/'.local/shared-dashboard/current.json').read_bytes()
            self.assertTrue(path.exists())
            self.assertIn('회사에서 계산한 저장 결과',path.read_text(encoding='utf-8'))
            bad=dict(manifest,sha256='f'*64)
            with self.assertRaises(ValueError):install(root,bad,blob)
            self.assertEqual((root/'.local/shared-dashboard/current.json').read_bytes(),before)
            self.assertEqual(cached(root)[0],manifest)

    def test_offline_home_uses_previous_result_without_calculation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.home(root);manifest,blob=self.bundle();install(root,manifest,blob)
            repo=Mock();repo.receive.side_effect=ValueError('offline');browser=Mock()
            with patch('investment.shared_dashboard.export_company',side_effect=AssertionError('home recalculated')):
                path,status=open_home(root,repository=repo,browser=browser)
            self.assertEqual(status,'cached');browser.assert_called_once_with(path.resolve().as_uri())

    def test_first_home_open_without_company_result_does_not_fall_back_to_collection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.home(root);repo=Mock();repo.receive.side_effect=ValueError('offline')
            with self.assertRaisesRegex(ValueError,'첫 결과 발행 대기'):open_home(root,repository=repo)
            with self.assertRaisesRegex(ValueError,'work Primary'):export_company(root)

    def test_old_remote_result_cannot_roll_back_newer_cached_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);current,blob=self.bundle();install(root,current,blob)
            old=dict(current,generated_at=(datetime.fromisoformat(current['generated_at'])-timedelta(seconds=1)).isoformat())
            with self.assertRaisesRegex(ValueError,'이전 버전'):install(root,old,blob)
            self.assertEqual(cached(root)[0],current)

    def test_fixture_or_live_token_cannot_be_accepted_as_company_result(self):
        manifest,blob=self.bundle()
        with self.assertRaises(ValueError):unpack(dict(manifest,data_mode='fixture'),blob)
        with self.assertRaises(ValueError):pack(result_html().replace('INVESTMENT_LIVE=null','INVESTMENT_LIVE={"token":"synthetic"}'),source_build='0'*64)
        with self.assertRaises(ValueError):unpack(dict(manifest,market_as_of='2026-09-22'),blob)

    def test_snapshot_excludes_personal_notes_and_file_metadata(self):
        snapshot=make_fixture();before=deepcopy(snapshot)
        snapshot['meta']['source_files']=['C:/private/source.xlsx']
        snapshot['companies'][0]['user_policy_evidence']={'private_note':'do not share'}
        public=public_snapshot(snapshot)
        self.assertNotIn('source_files',public['meta'])
        self.assertNotIn('user_policy_evidence',public['companies'][0])
        self.assertEqual(public['companies'][0]['evidence'],[])
        self.assertEqual(snapshot['companies'][1],before['companies'][1])

    def test_nested_secrets_and_private_paths_cannot_enter_artifact(self):
        for value in ({'password':'synthetic'}, {'extra':'C:/private/input'}, {'telegram':[]}):
            content=result_html().replace('"detail_html": null','"detail_html": null, "unexpected":'+json.dumps(value))
            with self.assertRaises(ValueError):pack(content,source_build='0'*64)

    def test_public_or_wrong_repository_blocks_transfer(self):
        run=Mock(return_value=Mock(returncode=0,stdout=json.dumps({'private':False,'full_name':'shinyj0270-afk/invest-results-private'})))
        repo=ResultRepository(run=run)
        with self.assertRaises(ValueError):repo.verify_private()
        with self.assertRaises(ValueError):ResultRepository('shinyj0270-afk/invest')
        self.assertEqual(run.call_count,1)


if __name__=='__main__':unittest.main()
