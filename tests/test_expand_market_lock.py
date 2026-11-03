"""expand_market must hold the dashboard's daily-refresh lock so it cannot roll back newer histories (Codex bug-class hunt, finding 5)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from investment.company_financials import acquire_lock
from tools import expand_market


class ExpandMarketLockTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.folder=self.root/'work/market-expansion'
        self.local=dict(data_dir=self.root,profile='work')

    def run_main(self,collect):
        with patch.object(expand_market,'load_local',return_value=self.local),patch.object(expand_market,'collect',collect),patch('sys.argv',['expand_market.py','--reuse-listing']):
            expand_market.main()

    def test_it_refuses_to_run_while_a_daily_refresh_holds_the_lock(self):
        self.folder.mkdir(parents=True);lease=acquire_lock(self.folder/'daily-refresh.lock');self.addCleanup(lease.close)
        called=[]
        with self.assertRaises(SystemExit) as raised:self.run_main(lambda *a:called.append(a))
        self.assertIn('진행 중',str(raised.exception));self.assertEqual(called,[])

    def test_the_lock_is_held_while_collecting_and_released_afterwards(self):
        seen=[]
        def collect(args,folder):
            with self.assertRaises(ValueError):acquire_lock(folder/'daily-refresh.lock')      # someone else cannot refresh meanwhile
            seen.append(args.reuse_listing)
        self.run_main(collect);self.assertEqual(seen,[True])
        again=acquire_lock(self.folder/'daily-refresh.lock');again.close()                     # released

    def test_the_lock_is_released_even_when_collection_fails(self):
        def collect(args,folder):raise RuntimeError('network down')
        with self.assertRaises(RuntimeError):self.run_main(collect)
        again=acquire_lock(self.folder/'daily-refresh.lock');again.close()


if __name__=='__main__':unittest.main()
