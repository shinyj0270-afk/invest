"""An interrupted receipt write must not leave a file the inbox reader will choke on (Codex bug-class hunt, finding 7)."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from investment import telegram_listen
from investment.telegram_listen import poll
from tests.test_telegram_listen import channel_post, fake_fetch


class AtomicReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.state=Path(self.tmp.name)/'state.json';self.out=Path(self.tmp.name)/'out'
        self.channel=dict(key='c1',expected_name='Synthetic channel',expected_id=-1001234567890)
        self.now=datetime(2026,1,2,3,4,5,tzinfo=timezone.utc)

    def test_a_crash_while_writing_leaves_no_receipt_for_the_reader_and_no_state_advance(self):
        real_dump=json.dump
        def crashing_dump(obj,stream,**kw):
            stream.write('{"schema":');stream.flush();raise OSError('disk full')       # a partial document reaches the file
        # patching Path.unlink models a hard kill: the process dies before any cleanup code can run
        with patch.object(telegram_listen.json,'dump',crashing_dump),patch('pathlib.Path.unlink',lambda *a,**k:None),self.assertRaises(OSError):
            poll('tok',self.channel,self.state,self.out,fetch=fake_fetch([[channel_post()]]),now=self.now)
        self.assertEqual(list(self.out.glob('receipt-*.json')),[])                    # nothing the inbox glob can match
        self.assertFalse(self.state.exists())                                          # the update offset did not advance, so a retry re-fetches it
        receipt=poll('tok',self.channel,self.state,self.out,fetch=fake_fetch([[channel_post()]]),now=self.now)
        files=list(self.out.glob('receipt-*.json'));self.assertEqual(len(files),1)
        self.assertEqual(json.loads(files[0].read_text(encoding='utf-8'))['counts'],receipt['counts'])   # complete, parseable

    def test_a_normal_poll_leaves_no_temporary_files_behind(self):
        poll('tok',self.channel,self.state,self.out,fetch=fake_fetch([[channel_post()]]),now=self.now)
        self.assertEqual(sorted(p.name[:8] for p in self.out.iterdir()),['receipt-'])


if __name__=='__main__':unittest.main()
