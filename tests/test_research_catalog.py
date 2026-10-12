"""Synthetic catalog tests; never evidence of actual Telegram access."""
import copy
import tempfile
import unittest
from pathlib import Path
from investment.research_library import Library
from investment.research_catalog import annotate, search, source_unique, annotation
from investment.telegram_research import channels, batch
from tests.test_research_library import source, card, thesis, registry, collection, permission

def metadata(stage='derived'):
    return dict(stage=stage,topic='capacity-cycle',sector='반도체',tags=['설비투자'],persons=['minervini'],
                instruments=[dict(code='005930',market='KOSPI',kind='stock')],event_id='event-1',
                summary='Synthetic hypothesis, not a source quote',source_note='Synthetic input',reason='Initial',
                reviewed_by=None,reviewed_on=None,human_reviewed=False)

class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.lib=Library(self.tmp.name,'home','fixture')
        source_unique(self.lib,'s1',source());self.lib.master('m1',card());self.lib.thesis('t1',thesis())

    def test_three_core_channels_and_message_retry(self):
        value=registry();value['core'].append(dict(id='c3',name='Synthetic core 3',enabled=True,permission=permission()))
        channels(self.lib,value)
        first=batch(self.lib,'c3',collection());retry=batch(self.lib,'c3',collection())
        self.assertEqual(first['inserted'],2);self.assertEqual((retry['inserted'],retry['duplicates']),(0,2))

    def test_url_duplicate_and_conflict_no_write(self):
        self.assertTrue(source_unique(self.lib,'s-alias',source())['duplicate'])
        self.assertEqual(source_unique(self.lib,'s-alias',source())['id'],'s1')
        conflict=source();conflict['title']='Different metadata'
        with self.assertRaises(ValueError):source_unique(self.lib,'s2',conflict)
        self.assertEqual(len(search(self.lib,stage='raw')),1)

    def test_queries_and_same_event_distinct_sources(self):
        annotate(self.lib,'master','m1',metadata())
        for kwargs in ({'person':'minervini'},{'topic':'capacity-cycle'},{'sector':'반도체'},{'company':'005930'},{'event_id':'event-1'}):
            self.assertEqual(search(self.lib,**kwargs)[0]['id'],'m1')
        s2=source();s2['url']='https://example.invalid/second';source_unique(self.lib,'s2',s2)
        for sid in ('s1','s2'):
            meta=metadata('raw');meta['summary']=None;annotate(self.lib,'source',sid,meta)
        self.assertEqual(len(search(self.lib,event_id='event-1')),3)
        for sector in ('전력기기','조선','화학'):self.assertEqual(search(self.lib,sector=sector),[])

    def test_raw_and_curated_review_gates(self):
        with self.assertRaises(ValueError):annotate(self.lib,'source','s1',metadata('raw'))
        with self.assertRaises(ValueError):annotate(self.lib,'master','m1',metadata('curated'))
        meta=metadata('curated');meta.update(human_reviewed=True,reviewed_by='Synthetic reviewer',reviewed_on='2026-01-03')
        annotate(self.lib,'master','m1',meta)
        self.assertEqual(len(search(self.lib,stage='curated')),1)
        self.assertEqual(self.lib.get('source','s1'),source())

    def test_correction_stale_write_delete_and_restore(self):
        original=copy.deepcopy(self.lib.get('source','s1'))
        annotate(self.lib,'source','s1',metadata())
        meta=metadata();meta['summary']='Corrected interpretation'
        annotate(self.lib,'source','s1',meta,1)
        with self.assertRaises(ValueError):annotate(self.lib,'source','s1',metadata(),1)
        meta.update(stage='deleted',reason='Synthetic mistaken input')
        annotate(self.lib,'source','s1',meta,2)
        self.assertEqual(search(self.lib,query='Synthetic research'),[])
        self.assertEqual(search(self.lib,stage='deleted')[0]['catalog_revision'],3)
        with self.assertRaises(ValueError):self.lib.draft('t1')
        self.assertEqual(self.lib.history('source','s1')[0]['value'],original)
        meta.update(stage='derived',reason='Explicit recovery')
        annotate(self.lib,'source','s1',meta,3)
        self.assertEqual(self.lib.get('source','s1'),original)
        self.assertEqual(annotation(self.lib,'source','s1')['revision'],4)

    def test_excluded_not_curated_or_normal_results(self):
        annotate(self.lib,'master','m1',metadata('excluded'))
        self.assertNotIn('m1',[x['id'] for x in search(self.lib)])
        self.assertEqual(search(self.lib,stage='excluded')[0]['id'],'m1')
        annotate(self.lib,'source','s1',metadata('excluded'))
        self.assertEqual(search(self.lib,stage='excluded')[0]['id'],'s1')

    def test_readonly_view_hides_deleted_dependencies_without_creating_db(self):
        from unittest.mock import patch
        from investment.research_library_view import view
        root=Path(self.tmp.name)
        real=Library(root/'.local/research-library','home')
        real.source('s1',source());real.master('m1',card());real.thesis('t1',thesis())
        annotate(real,'source','s1',metadata('deleted'))
        with patch('investment.research_library_view.load_local'), patch('investment.research_library_view.require_profile',return_value='home'):
            result=view(root)
        self.assertEqual((result['sources'],result['cards'],result['theses']),([],[],[]))

    def test_cli_duplicate_identity_and_search_catalog_revision(self):
        import io,json,contextlib
        from unittest.mock import patch
        from tools import research_library as cli
        root=Path(self.tmp.name)/'cli';(root/'.local').mkdir(parents=True)
        (root/'.local/source.json').write_text(json.dumps(source()),encoding='utf-8')
        def run(args):
            with patch.object(cli,'ROOT',root),patch.object(cli,'load_local',return_value={'profile':'home'}),patch('sys.argv',['research_library.py']+args),contextlib.redirect_stdout(io.StringIO()) as output:
                cli.main()
            return json.loads(output.getvalue())
        self.assertFalse(run(['source','--id','s1','--input','.local/source.json'])['duplicate'])
        self.assertEqual(run(['source','--id','alias','--input','.local/source.json'])['id'],'s1')
        (root/'.local/meta.json').write_text(json.dumps(metadata()),encoding='utf-8')
        self.assertEqual(run(['annotate','--kind','source','--id','s1','--input','.local/meta.json'])['revision'],1)
        result=run(['search','--company','005930'])
        self.assertEqual((result[0]['id'],result[0]['catalog_revision']),('s1',1))

    def test_deleted_telegram_metadata_rechecks_permission(self):
        channels(self.lib,registry())
        tg=source(origin='telegram');tg['url']='https://t.me/synthetic_test/9'
        source_unique(self.lib,'tg',tg);annotate(self.lib,'source','tg',metadata('deleted'))
        self.assertEqual(search(self.lib,stage='deleted')[0]['id'],'tg')
        value=registry();value['core'][0]['enabled']=False;channels(self.lib,value,1)
        self.assertEqual(search(self.lib,stage='deleted'),[])

    def test_revoked_telegram_never_reused(self):
        channels(self.lib,registry());tg=source(origin='telegram');tg['url']='https://t.me/synthetic_test/1';source_unique(self.lib,'tg',tg)
        meta=metadata('raw');meta['summary']=None;annotate(self.lib,'source','tg',meta)
        value=registry();value['core'][0]['enabled']=False;channels(self.lib,value,1)
        self.assertNotIn('tg',[x['id'] for x in search(self.lib)])
        with self.assertRaises(ValueError):annotate(self.lib,'source','tg',metadata(),1)

if __name__=='__main__':unittest.main()
