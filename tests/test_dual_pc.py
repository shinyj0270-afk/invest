import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from investment.local_config import load_local, require_profile
from investment.store import Store
from investment.fixture import make_fixture
from tools.pc_check import inspect, excluded

ROOT = Path(__file__).resolve().parents[1]


class LocalTests(unittest.TestCase):
    def test_unknown_and_profile_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            config = load_local(folder)
            self.assertEqual(config['profile'], 'unknown')
            with self.assertRaises(ValueError): require_profile(config)
            with self.assertRaises(ValueError): require_profile(dict(profile='work'), 'home')

    def test_custom_path_and_fixture_separation(self):
        import batch
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root/'config').mkdir()
            (root/'config/local.json').write_text(json.dumps(dict(profile='work', data_dir='custom-private')), encoding='utf-8')
            config = load_local(root)
            self.assertEqual(config['data_dir'], root/'custom-private')
            self.assertIsNone(config['manual_snapshot_file'])
            Store(config['data_dir'], 'work', 'fixture').save_snapshot(make_fixture())
            with patch.object(batch, 'ROOT', root):
                self.assertEqual(batch.run('work', 'fixture', 'daily')['status'], 'complete')
                with self.assertRaises(ValueError): batch.run('home', 'fixture', 'daily')
            self.assertFalse((root/'data').exists())
            self.assertIsNone(Store(config['data_dir'], 'work', 'user_input').latest())
            self.assertIsNone(Store(config['data_dir'], 'home', 'fixture').latest())

    def test_copied_root_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'config').mkdir()
            (root/'config/local.json').write_text('{"project_root":"other-checkout"}',encoding='utf-8')
            with self.assertRaises(ValueError): load_local(root)

    def test_exclusions(self):
        for name in ('config/local.json', '.env', 'private_data/raw.xlsx', 'x.sqlite3-wal',
                     'x.db-journal', '.streamlit/secrets.toml', 'validation/current/a.txt'):
            self.assertTrue(excluded(name),name)
        self.assertFalse(excluded('investment/core.py'))

    def test_app_uses_custom_local_path(self):
        from streamlit.testing.v1 import AppTest
        with tempfile.TemporaryDirectory() as folder:
            local=dict(profile='work',data_dir=Path(folder),enabled_data_adapters=[],scheduled_jobs_enabled=False)
            with patch('investment.local_config.load_local',return_value=local):
                app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
                self.assertEqual(len(app.exception),0)
                self.assertTrue(any('실제 저장자료가 없습니다' in x.value for x in app.info))
                next(x for x in app.selectbox if x.label=='데이터 모드').select('가상 테스트').run()
                next(x for x in app.button if x.label=='현재 스냅샷을 이 PC에 저장').click().run()
                self.assertEqual(len(app.exception),0)
                self.assertIsNotNone(Store(folder,'work','fixture').latest())
            self.assertIsNone(Store(folder,'work','user_input').latest())

    def test_manual_file_is_pc_local(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'config').mkdir()
            (root/'config/local.json').write_text('{"profile":"home","manual_snapshot_file":"private_data/manual.json"}',encoding='utf-8')
            config=load_local(root)
            self.assertEqual(config['manual_snapshot_file'],root/'private_data/manual.json')
            self.assertFalse(config['manual_snapshot_file'].exists())

    def test_scheduled_disabled(self):
        import sys
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); (root/'config').mkdir()
            (root/'config/local.json').write_text('{"profile":"work","scheduled_jobs_enabled":false}',encoding='utf-8')
            # Run CLI against copied code only, never the operating data or scheduler.
            (root/'batch.py').write_bytes((ROOT/'batch.py').read_bytes())
            import os
            env=dict(os.environ,PYTHONPATH=str(ROOT),PYTHONIOENCODING='utf-8')
            run=subprocess.run([sys.executable,str(root/'batch.py'),'daily','--scheduled'],env=env,capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(run.returncode,1)
            self.assertIn('Scheduled jobs disabled',run.stderr)
            self.assertFalse((root/'data').exists())


class GitTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.base=Path(self.temp.name)
        self.repo=self.base/'repo'; self.repo.mkdir()
        self.git('init','-b','handoff')
        self.commit('initial.txt','initial')

    def tearDown(self): self.temp.cleanup()

    def git(self,*args,cwd=None):
        run=subprocess.run(['git','-C',str(cwd or self.repo),*args],capture_output=True,text=True,encoding='utf-8')
        if run.returncode: self.fail('Synthetic Git command failed: '+str(args[:1]))
        return run.stdout

    def commit(self,name,value,cwd=None):
        cwd=cwd or self.repo
        (cwd/name).write_text(value,encoding='utf-8')
        self.git('add','--',name,cwd=cwd)
        self.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
                 '-c','commit.gpgsign=false','commit','-m','synthetic fixture',cwd=cwd)

    def setup_remote(self):
        remote=self.base/'origin.git'
        self.git('init','--bare','-b','handoff',str(remote))
        self.git('remote','add','origin',str(remote))
        self.git('push','-u','origin','handoff') # Temporary filesystem only.
        return remote

    def test_no_repository(self):
        self.assertFalse(inspect(self.base)['repository'])

    def test_no_remote_dirty_and_no_mutation(self):
        self.assertEqual(inspect(self.repo)['state'],'no_remote')
        child=self.repo/'nested'; child.mkdir()
        self.assertEqual(inspect(child)['repository_root'].replace('\\','/'),str(self.repo).replace('\\','/'))
        before=self.git('rev-parse','HEAD')
        (self.repo/'initial.txt').write_text('unfinished',encoding='utf-8')
        self.assertEqual(inspect(self.repo)['state'],'dirty')
        self.assertEqual(self.git('rev-parse','HEAD'),before)
        self.assertEqual((self.repo/'initial.txt').read_text(),'unfinished')
        self.assertEqual(inspect(child)['state'],'dirty')

    def test_clean_and_divergent_cached_refs(self):
        remote=self.setup_remote()
        self.assertEqual(inspect(self.repo)['state'],'clean_cached_refs')
        other=self.base/'other'
        self.git('clone',str(remote),str(other))
        self.commit('local.txt','local')
        self.commit('other.txt','other',cwd=other)
        self.git('push','origin','handoff',cwd=other)
        self.git('fetch','origin') # Local fixture remote only.
        result=inspect(self.repo)
        self.assertEqual(result['state'],'diverged')
        self.assertEqual((result['ahead'],result['behind']),(1,1))
        self.assertFalse(result['transfer_performed_by_check'])

    def test_private_tracked_and_ignore(self):
        (self.repo/'.gitignore').write_bytes((ROOT/'.gitignore').read_bytes())
        self.git('add','--','.gitignore')
        (self.repo/'local.sqlite3-wal').write_text('synthetic',encoding='utf-8')
        self.assertTrue(self.git('check-ignore','local.sqlite3-wal').strip())
        self.git('add','-f','--','local.sqlite3-wal')
        self.assertEqual(inspect(self.repo)['tracked_private_paths'],['local.sqlite3-wal'])

    def test_remote_url_never_exposed(self):
        self.git('remote','add','origin','https://fake:NOT_REAL@example.invalid/repo?key=NOT_REAL')
        result=json.dumps(inspect(self.repo))
        self.assertNotIn('NOT_REAL',result)
        self.assertNotIn('example.invalid',result)

    def test_merge_marker_stops(self):
        head=self.git('rev-parse','HEAD').strip()
        (self.repo/'.git/MERGE_HEAD').write_text(head,encoding='utf-8')
        self.assertEqual(inspect(self.repo)['state'],'unfinished_operation')


if __name__=='__main__': unittest.main()
