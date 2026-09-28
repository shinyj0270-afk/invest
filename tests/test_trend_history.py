import copy
import json
import tempfile
import unittest
from unittest.mock import Mock, patch
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from investment.fixture import make_fixture
from investment import trend
from tools.trend_history import build,chart,fetch_charts,SYMBOLS,INDEX


class TrendHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.base=make_fixture(); self.base['meta']['data_mode']='user_input'
        self.base['companies']=copy.deepcopy(self.base['companies'][:3])
        self.files={}
        dates=self.base['sessions'][-253:]
        for row,code in zip(self.base['companies'],SYMBOLS):
            row['code']=code
            row['prices']=row['prices'][-99:]
            row['price_venue']=None
        for symbol in (*SYMBOLS.values(),INDEX):
            quotes={'open':[],'high':[],'low':[],'close':[],'volume':[]}
            timestamps=[]
            for i,date in enumerate(dates):
                value=1000+i if symbol==INDEX else 100+i
                timestamps.append(int(datetime.fromisoformat(date+'T15:30:00').replace(tzinfo=ZoneInfo('Asia/Seoul')).timestamp()))
                for key,n in [('open',value),('high',value*1.02),('low',value*.98),('close',value),('volume',100000)]:
                    quotes[key].append(n)
            payload={'chart':{'result':[{'meta':{'symbol':symbol,'exchangeTimezoneName':'Asia/Seoul'},
                'timestamp':timestamps,'indicators':{'quote':[quotes]},'events':{'splits':{}}}]}}
            path=self.folder/(symbol.replace('^','index-')+'.json')
            path.write_text(json.dumps(payload),encoding='utf-8')
            self.files[symbol]=path

    def test_overlay_uses_253_sessions_and_keeps_existing_data(self):
        original=copy.deepcopy(self.base)
        s=build(self.base,self.files)
        self.assertEqual(len(s['meta']['trend_sessions']),253)
        self.assertEqual(len(s['benchmarks']['KOSPI']),253)
        self.assertEqual(len(s['companies'][0]['trend_prices']),253)
        for old,new in zip(original['companies'],s['companies']):
            for key in ('prices','flows','metrics','quarters','annual'):
                self.assertEqual(old.get(key),new.get(key))
        self.assertEqual(self.base,original)
        self.assertNotEqual(trend.analyze(s)[0]['status'],'unknown')
        self.assertEqual(s['companies'][0]['trend_source']['overlaps'],99)

    def test_missing_old_turnover_allowed_recent_turnover_required(self):
        s=build(self.base,self.files)
        self.assertIsNone(s['companies'][0]['trend_prices'][0]['turnover'])
        self.assertNotEqual(trend.analyze(s)[0]['status'],'unknown')
        s['companies'][0]['trend_prices'][-1]['turnover']=None
        target=next(r for r in trend.analyze(s) if r['code']==s['companies'][0]['code'])
        self.assertEqual(target['status'],'unknown')

    def test_stale_overlay_is_not_evaluated(self):
        s=build(self.base,self.files)
        s['meta']['price_date']='2026-09-24'
        self.assertTrue(all(r['status']=='unknown' for r in trend.analyze(s)))
        self.assertIn('오래됨',trend.analyze(s)[0]['reason'])

    def test_split_event_requires_review(self):
        path=self.files['005930.KS']; data=json.loads(path.read_text(encoding='utf-8'))
        data['chart']['result'][0]['events']['splits']={'1':{'splitRatio':'2:1'}}
        path.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'주식분할'):
            build(self.base,self.files)

    def test_fetch_archives_each_response_by_hash(self):
        responses = iter(self.files[s].read_bytes() for s in (*SYMBOLS.values(),INDEX))
        with patch('requests.get', side_effect=lambda *a, **k: Mock(
                content=next(responses), raise_for_status=Mock())) as request:
            files = fetch_charts(self.folder/'archive')
        self.assertEqual(set(files),set((*SYMBOLS.values(),INDEX)))
        self.assertEqual(len(list((self.folder/'archive').glob('*.json'))),4)
        self.assertEqual(request.call_count,4)
        self.assertIn('%5EKS11',request.call_args.args[0])
        self.assertEqual(chart(files['005930.KS'],'005930.KS',self.base['meta']['price_date'])[0],
                         chart(self.files['005930.KS'],'005930.KS',self.base['meta']['price_date'])[0])


if __name__=='__main__': unittest.main()
