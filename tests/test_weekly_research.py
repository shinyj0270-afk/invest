"""Synthetic weekly transaction, conflict, provenance and link checks."""
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from investment.research_library import Library
from investment.weekly_research import import_week, read_bundle
from investment.research_catalog import annotate
from tests.test_research_library import source, card, thesis, evidence


class WeeklyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.lib = Library(self.temp.name, 'work', 'fixture')
        self.bundle = dict(research_date='2026-01-05', markdown_sha256='a'*64,
            records=[dict(kind=k, id=i, value=v) for k,i,v in
                     [('source','s1',source()),('master','m1',card()),('thesis','t1',thesis()),('evidence','e1',evidence())]])

    def count(self):
        with self.lib.connect() as db:
            return db.execute('SELECT count(*) FROM records').fetchone()[0]

    def test_dry_run_then_replay(self):
        self.assertEqual(import_week(self.lib,self.bundle)['inserted'],4)
        self.assertEqual(self.count(),0)
        first = import_week(self.lib,self.bundle,apply=True)
        self.assertEqual(first['inserted'],4)
        self.assertEqual(self.count(),5)
        self.assertEqual(import_week(self.lib,self.bundle,apply=True)['inserted'],0)
        self.assertEqual(self.count(),5)

    def test_late_invalid_reference_rolls_back(self):
        self.bundle['records'][-1]['value']['thesis_id']='missing'
        with self.assertRaises(ValueError):
            import_week(self.lib,self.bundle,apply=True)
        self.assertEqual(self.count(),0)

    def test_conflicting_same_original_preserves(self):
        import_week(self.lib,self.bundle,apply=True)
        self.bundle['records'][1]['value']['principle']='different'
        with self.assertRaises(ValueError):
            import_week(self.lib,self.bundle,apply=True)
        self.assertEqual(self.count(),5)

    def test_exact_source_reuses_id_and_remaps(self):
        self.lib.source('old',source())
        result=import_week(self.lib,self.bundle,apply=True)
        self.assertEqual(result['inserted'],3)
        self.assertEqual(self.lib.get('master','m1')['source_ids'],['old'])
        self.assertEqual(len(self.lib.history('source','s1')),0)

    def test_source_metadata_conflict_preserves(self):
        self.lib.source('old',dict(source(),title='different'))
        with self.assertRaises(ValueError):
            import_week(self.lib,self.bundle,apply=True)
        self.assertEqual(self.count(),1)

    def test_existing_thesis_revision_not_overwritten(self):
        import_week(self.lib,self.bundle,apply=True)
        changed=copy.deepcopy(self.bundle)
        changed['markdown_sha256']='b'*64
        changed['records'][2]['value']['claim']='new claim'
        with self.assertRaises(ValueError):
            import_week(self.lib,changed,apply=True)
        self.assertEqual(len(self.lib.history('thesis','t1')),1)

    def test_link_existing_people_strategies_sector_thesis(self):
        self.lib.source('s0',dict(source(),url='https://example.invalid/old'))
        self.lib.master('m0',dict(card(),source_ids=['s0']))
        self.lib.thesis('t0',dict(thesis(),master_ids=['m0']))
        links=import_week(self.lib,self.bundle,apply=True)['links']
        self.assertTrue(any(x['target']==['master','m0'] and 'same_person' in x['reasons'] and 'same_strategy' in x['reasons'] for x in links))
        self.assertTrue(any(x['target']==['thesis','t0'] and 'same_sector' in x['reasons'] for x in links))
        self.assertTrue(any(x['origin']==['evidence','e1'] and x['target']==['thesis','t1'] and 'explicit_reference' in x['reasons'] for x in links))

    def test_concurrent_replay_inserts_once(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:import_week(self.lib,self.bundle,apply=True),range(2)))
        self.assertEqual(sorted(x['inserted'] for x in results),[0,4])
        self.assertEqual(self.count(),5)

    def test_monday_and_observation_gate(self):
        self.bundle['research_date']='2026-01-06'
        with self.assertRaises(ValueError):import_week(self.lib,self.bundle,apply=True)
        self.bundle['research_date']='2026-01-05'
        self.bundle['records'][-1]['value']['observed_on']='2026-01-06'
        with self.assertRaises(ValueError):import_week(self.lib,self.bundle,apply=True)
        self.assertEqual(self.count(),0)

    def test_deleted_source_blocks_replay(self):
        import_week(self.lib,self.bundle,apply=True)
        annotate(self.lib,'source','s1',dict(stage='deleted',topic='synthetic',sector='미확인',tags=[],persons=[],instruments=[],event_id=None,summary=None,source_note='Synthetic only',reason='Synthetic deletion',reviewed_by=None,reviewed_on=None,human_reviewed=False))
        with self.assertRaises(ValueError):import_week(self.lib,self.bundle,apply=True)
        self.assertEqual(self.count(),6)

    def test_markdown_zip_hash_bound(self):
        root=Path(self.temp.name); raw=b'# synthetic weekly note\n'
        (root/'note.md').write_bytes(raw)
        self.bundle['markdown_sha256']=hashlib.sha256(raw).hexdigest()
        (root/'note.json').write_text(json.dumps(self.bundle),encoding='utf-8')
        with zipfile.ZipFile(root/'note.zip','w') as z:z.writestr('note.md',raw)
        self.assertEqual(read_bundle(root/'note.md',root/'note.json',root/'note.zip'),self.bundle)
        with zipfile.ZipFile(root/'note.zip','w') as z:z.writestr('note.md',b'different')
        with self.assertRaises(ValueError):read_bundle(root/'note.md',root/'note.json',root/'note.zip')
        (root/'note.md').write_bytes(b'changed original')
        with self.assertRaises(ValueError):read_bundle(root/'note.md',root/'note.json')


if __name__ == '__main__':unittest.main()
