"""The runtime market cache must reload when a policy input of load_market_cache changes (Codex bug-class hunt, finding 4)."""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from investment.market_discovery import MarketCacheReader, load_market_cache


class PolicyInputVersionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.folder=self.root/'work/market-expansion';self.folder.mkdir(parents=True)
        (self.folder/'universe.json').write_text(json.dumps(dict(schema_version='naver-universe-0.1',companies=[])),encoding='utf-8')
        (self.folder/'histories.json').write_text('{}',encoding='utf-8')
        self.exclusions=self.root/'excluded_companies.json';self.exclusions.write_text('{}',encoding='utf-8')
        self.snap=dict(meta=dict(data_mode='user_input'));self.reader=MarketCacheReader()
        self.patches=[patch('investment.market_discovery.load_local',return_value=dict(data_dir=self.root,profile='work')),
            patch('investment.market_discovery.USER_EXCLUSIONS',self.exclusions),
            patch('investment.market_discovery.today_kst',return_value=date(2026,11,3))]
        for p in self.patches:p.start()
        self.addCleanup(patch.stopall)
        self.loads=patch('investment.market_discovery.load_market_cache',wraps=load_market_cache);self.loader=self.loads.start()

    def get(self):return self.reader.get(self.root,self.snap)

    def test_unchanged_inputs_are_served_from_the_cache(self):
        self.get();self.get();self.assertEqual(self.loader.call_count,1)

    def test_listing_dates_change_invalidates(self):
        self.get();(self.folder/'listing-dates.json').write_text(json.dumps(dict(schema_version='listing-dates-0.1',companies={})),encoding='utf-8')
        self.get();self.assertEqual(self.loader.call_count,2)

    def test_user_exclusion_file_change_invalidates(self):
        self.get();self.exclusions.write_text(json.dumps({'005930':'user'}),encoding='utf-8')
        self.get();self.assertEqual(self.loader.call_count,2)

    def test_a_new_kst_day_invalidates_because_listing_seasoning_depends_on_today(self):
        self.get()
        with patch('investment.market_discovery.today_kst',return_value=date(2026,11,4)):self.get()
        self.assertEqual(self.loader.call_count,2)


if __name__=='__main__':unittest.main()
