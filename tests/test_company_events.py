import json,tempfile,unittest
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo
from investment.company_events import parse,view

class CompanyEventsTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,16,10,tzinfo=ZoneInfo('Asia/Seoul'))
        self.news={'clusters':[{'items':[dict(title='제목 &amp; 확인',officeId='001',articleId='0012345678',officeName='가상 언론',datetime='202610160900',body='본문 미저장')]}]}
        self.notice=[dict(itemcode='000660',no='123',title='가상 공시',datetime='2026-10-15T15:00:00',contents='<script>never stored</script>')]
    def test_metadata_only_and_independent_dates(self):
        n=parse(self.news,'000660','news',self.now)[0]
        self.assertEqual(n['published_on'],'2026-10-16');self.assertNotIn('body',n)
        self.assertEqual(n['title'],'제목 & 확인');self.assertIn('/001/0012345678',n['url'])
        d=parse(self.notice,'000660','disclosure',self.now)[0]
        self.assertNotIn('contents',d);self.assertIn('시간대 미명시',d['published_display'])
    def test_identity_dates_and_duplicates(self):
        self.notice[0]['itemcode']='005930'
        with self.assertRaises(ValueError):parse(self.notice,'000660','disclosure',self.now)
        self.news['clusters']*=2;self.assertEqual(len(parse(self.news,'000660','news',self.now)),1)
        self.news['clusters'][0]['items'][0]['datetime']='202610161100'
        self.assertEqual(parse(self.news,'000660','news',self.now),[])
    def test_cache_partial_failure_and_read_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);data=root/'data';market=data/'work'/'market-expansion';market.mkdir(parents=True)
            (market/'universe.json').write_text(json.dumps({'companies':[{'code':'000660','name':'가상 기업'}]}))
            calls=[]
            def fetcher(code,kind,now):calls.append(kind);return parse(self.news if kind=='news' else self.notice,code,kind,now)
            with patch('investment.company_events.load_local',return_value={'data_dir':data,'profile':'work'}):
                blank=view(root,'000660',now=self.now,read_only=True,fetcher=fetcher)
                self.assertFalse(calls);self.assertEqual(blank['groups']['news']['status'],'unavailable')
                first=view(root,'000660',now=self.now,fetcher=fetcher);self.assertEqual(len(calls),2)
                cached=view(root,'000660',now=self.now+timedelta(minutes=1),fetcher=fetcher)
                self.assertEqual(len(calls),2);self.assertEqual(cached['groups']['news']['status'],'cached')
                def failing(code,kind,now):
                    if kind=='news':raise ValueError('schema changed')
                    return []
                stale=view(root,'000660',now=self.now+timedelta(minutes=11),fetcher=failing)
                self.assertEqual(stale['groups']['news']['status'],'stale');self.assertEqual(stale['groups']['news']['items'],first['groups']['news']['items'])
                self.assertEqual(stale['groups']['disclosure']['status'],'complete');self.assertEqual(stale['groups']['disclosure']['items'],[])
                with self.assertRaises(ValueError):view(root,'000001',now=self.now)

if __name__=='__main__':unittest.main()
