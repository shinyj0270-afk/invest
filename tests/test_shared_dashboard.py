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
    def test_home_source_is_truthful_and_legacy_company_source_remains_readable(self):
        manifest, blob = pack(result_html(), source_build='0'*64, source_profile='home')
        self.assertEqual(manifest['source_profile'], 'home')
        self.assertEqual(unpack(manifest, blob), result_html())
        with tempfile.TemporaryDirectory() as tmp:
            path = install(Path(tmp), manifest, blob)
            self.assertIn('집에서 계산한 저장 결과', path.read_text(encoding='utf-8'))
        with self.assertRaises(ValueError):
            unpack(dict(manifest, source_profile='unknown'), blob)

    def test_single_publisher_policy_preserves_actual_pc_identity(self):
        from investment.shared_dashboard import publisher_profile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp);self.home(root)
            self.assertEqual(publisher_profile(root), 'work')
            (root/'config/result_publisher.json').write_text(json.dumps({'version':1,'profile':'home'}))
            self.assertEqual(publisher_profile(root), 'home')
            (root/'config/local.json').write_text(json.dumps({'profile':'work'}))
            with self.assertRaisesRegex(ValueError, 'home 발행 PC'):
                export_company(root)  # Must gate before any saved-data calculation.
            for policy in ({'version':True,'profile':'home'}, {'version':1,'profile':'unknown'}):
                (root/'config/result_publisher.json').write_text(json.dumps(policy))
                with self.assertRaises(ValueError):publisher_profile(root)

    def test_receive_rejects_wrong_publisher_and_preserves_previous_cache(self):
        manifest,blob=self.bundle()
        def command(*args,**kwargs):
            if args[:2]==('release','view'):
                return {'tagName':'results-20261021T000000Z-'+manifest['sha256'][:12],
                        'isDraft':False,'isPrerelease':False}
            folder=Path(args[args.index('--dir')+1])
            (folder/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
            (folder/'dashboard.html.gz').write_bytes(blob)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.home(root)
            install(root,manifest,blob)
            before=(root/'.local/shared-dashboard/current.json').read_bytes()
            (root/'config/result_publisher.json').write_text(json.dumps({'version':1,'profile':'home'}))
            repo=ResultRepository();repo.verify_private=Mock();repo.command=command
            with self.assertRaisesRegex(ValueError,'지정 발행 PC'):
                repo.receive(root)
            self.assertEqual((root/'.local/shared-dashboard/current.json').read_bytes(),before)

    def test_official_https_sources_are_not_mistaken_for_windows_drive_paths(self):
        from investment.shared_dashboard import public_data
        public_data({'source_url':'https://dart.fss.or.kr/report/viewer.do?rcpNo=20260814000001',
                     'source_urls':['https://finance.naver.com/']})
        for value in ('C:/private/input','source D:\\private\\input','file:///C:/private/input'):
            with self.assertRaises(ValueError):public_data({'source_url':value})
    def test_compressed_result_preserves_complete_independent_values_and_rejects_corruption(self):
        from investment.shared_dashboard import encode_result_payload,restore_result_payload
        item={'source':'공식 원문 <script> 보존 '*20,'values':[0,None,-1,True], 'date':'2026-06-30'}
        value={'analysis_snapshot':{'meta':{'price_date':'2026-09-23'}},
               'financial_tables':{'900001':deepcopy(item),'900002':deepcopy(item)},
               'company_details':{'900001':deepcopy(item)},'detail_html':None}
        before=deepcopy(value)
        wire=encode_result_payload(value)
        self.assertEqual(wire['wire_format'],'result-gzip-v1')
        self.assertEqual(value,before)
        self.assertLess(len(json.dumps(wire)),len(json.dumps(value)))
        restored=restore_result_payload(wire)
        self.assertEqual(restored,before)
        restored['company_details']['900001']['values'][0]=99
        self.assertEqual(restored['financial_tables']['900001']['values'][0],0)
        for bad in (dict(wire,wire_bytes=1),dict(wire,wire_bytes=2**40),dict(wire,wire_gzip='invalid'),dict(wire,wire_bytes=True)):
            with self.assertRaises(ValueError):restore_result_payload(bad)

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
            with self.assertRaisesRegex(ValueError,'work 발행 PC'):export_company(root)

    def test_old_remote_result_cannot_roll_back_newer_cached_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);current,blob=self.bundle();install(root,current,blob)
            old=dict(current,generated_at=(datetime.fromisoformat(current['generated_at'])-timedelta(seconds=1)).isoformat())
            with self.assertRaisesRegex(ValueError,'이전 버전'):install(root,old,blob)
            self.assertEqual(cached(root)[0],current)

    def test_later_generated_result_with_older_market_data_does_not_replace_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            current,blob=self.bundle(generated_at=(datetime.now().astimezone()-timedelta(minutes=10)).isoformat())
            install(root,current,blob)
            old,old_blob=pack(result_html().replace('2026-09-23','2026-09-22'),source_build='0'*64)
            with self.assertRaisesRegex(ValueError,'자료 기준일이 이전'):
                install(root,old,old_blob)
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
            from investment.shared_dashboard import encode_result_payload
            before,tail=content.split('const WORKSPACE_DATA=',1)
            value,length=json.JSONDecoder().raw_decode(tail)
            compressed=before+'const WORKSPACE_DATA='+json.dumps(encode_result_payload(value))+tail[length:]
            with self.assertRaises(ValueError):pack(compressed,source_build='0'*64)

    def test_public_or_wrong_repository_blocks_transfer(self):
        run=Mock(return_value=Mock(returncode=0,stdout=json.dumps({'private':False,'full_name':'shinyj0270-afk/invest-results-private'})))
        repo=ResultRepository(run=run)
        with self.assertRaises(ValueError):repo.verify_private()
        with self.assertRaises(ValueError):ResultRepository('shinyj0270-afk/invest')
        self.assertEqual(run.call_count,1)

    def test_unused_compressed_source_text_cannot_hide_local_metadata(self):
        import base64
        value=json.JSONDecoder().raw_decode(result_html().split('const WORKSPACE_DATA=',1)[1])[0]
        value.update(wire_format='result-text-v1',wire_text=['C:/synthetic/private-input'])
        raw=json.dumps(value).encode('utf-8')
        wire=dict(wire_format='result-gzip-v1',wire_bytes=len(raw),wire_gzip=base64.b64encode(gzip.compress(raw)).decode('ascii'))
        content='<script>const INVESTMENT_LIVE=null;const WORKSPACE_DATA='+json.dumps(wire)+';</script>'
        with self.assertRaises(ValueError):pack(content,source_build='0'*64)


if __name__=='__main__':unittest.main()
