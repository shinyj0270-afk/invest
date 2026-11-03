"""A second offline submission must not destroy the first queued holdings edit (Codex bug-class hunt, finding 2)."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from investment.holdings_sync import HoldingsService
from tests.test_holdings_sync import MemoryBackend, state, ROOT


class QueuedEditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.backend=MemoryBackend()
        self.cache=Path(self.temp.name)/'work.json';self.service=HoldingsService(ROOT,self.backend,self.cache)
        self.base=state();self.service.submit(self.base,None)
    def tearDown(self):self.temp.cleanup()

    def edits(self):
        a=copy.deepcopy(self.base);b=copy.deepcopy(self.base)
        a['input']['holdings'][0]['quantity']=42;b['input']['holdings'][1]['quantity']=12
        return a,b

    def test_two_offline_edits_from_the_same_base_are_both_kept_and_published_on_reconnect(self):
        a,b=self.edits();self.backend.offline=True
        self.assertEqual(self.service.submit(a,self.base)['status'],'offline')
        second=self.service.submit(b,self.base);self.assertEqual(second['status'],'offline')
        queued=json.loads(self.cache.read_text(encoding='utf-8'))['state']
        self.assertEqual((queued['input']['holdings'][0]['quantity'],queued['input']['holdings'][1]['quantity']),(42,12))
        self.backend.offline=False;self.assertEqual(self.service.poll()['status'],'synced')
        published=self.backend.state['input']['holdings'];self.assertEqual((published[0]['quantity'],published[1]['quantity']),(42,12))

    def test_a_conflicting_second_offline_edit_does_not_replace_the_queued_one(self):
        a,_=self.edits();rival=copy.deepcopy(self.base);rival['input']['holdings'][0]['quantity']=99
        self.backend.offline=True;self.service.submit(a,self.base)
        result=self.service.submit(rival,self.base)
        self.assertEqual(result['status'],'conflict');self.assertTrue(result['local_saved'])
        record=json.loads(self.cache.read_text(encoding='utf-8'))
        self.assertTrue(record['pending']);self.assertEqual(record['state']['input']['holdings'][0]['quantity'],42)

    def test_an_online_conflict_can_still_be_resolved_by_resubmitting(self):
        a,b=self.edits();self.backend.state=copy.deepcopy(a);self.backend.revision='9'   # another PC already published a
        rival=copy.deepcopy(self.base);rival['input']['holdings'][0]['quantity']=99
        self.assertEqual(self.service.submit(rival,self.base)['status'],'conflict')
        resolved=copy.deepcopy(a);resolved['input']['holdings'][1]['quantity']=12
        self.assertEqual(self.service.submit(resolved,a)['status'],'synced')


if __name__=='__main__':unittest.main()
