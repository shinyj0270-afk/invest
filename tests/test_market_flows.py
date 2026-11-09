import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from investment import market_flows as f


NOW = datetime(2026, 11, 9, 9, tzinfo=f.KST)
DAYS = ['2026-11-02', '2026-11-03', '2026-11-04', '2026-11-05', '2026-11-06']


def series(counts):
    return {day: dict(foreign=n, institution=-n, close=100, volume=100) for day, n in zip(DAYS, counts)}


def trades(code):
    return [dict(itemCode=code, bizdate=d.replace('-', ''), closePrice='1,000',
                 accumulatedTradingVolume='100', foreignerPureBuyQuant='-10', organPureBuyQuant='+5')
            for d in reversed(DAYS)]


class MarketFlowsTest(unittest.TestCase):
    def test_evidence_needs_both_legs_and_same_investor(self):
        equity, bond = series([-2]*5), series([3]*5)
        for actor, way in [('foreign','to_bond'), ('institution','to_equity')]:
            path = f.episode(equity, bond, DAYS, actor)
            self.assertEqual([p['state'] for p in path], ['waiting','waiting','early','early','persistent'])
            self.assertEqual(path[-1]['direction'], way)
            self.assertEqual(path[:3], f.episode(equity, bond, DAYS[:3], actor))
        self.assertEqual(f.episode(bond,bond,DAYS,'foreign')[-1]['state'],'mixed')

    def test_spike_or_immaterial_net_share_is_not_an_alert(self):
        for a, b in [([-15,0,0],[15,0,0]), ([-1,-1,0],[1,1,0])]:
            self.assertEqual(f.episode(series(a),series(b),DAYS[:3],'foreign')[-1]['state'],'mixed')

    def test_missing_or_zero_volume_never_compresses_time(self):
        left, right = series([-4]*5), series([4]*5)
        del left[DAYS[1]]
        self.assertIsNone(f.window(left,DAYS,'foreign'))
        self.assertEqual(f.episode(left,right,DAYS,'foreign')[-1]['state'],'early')
        right[DAYS[-1]]['foreign'] = None
        self.assertEqual(f.episode(left,right,DAYS,'foreign')[-1]['state'],'waiting')
        right[DAYS[-1]].update(foreign=0,volume=0)
        self.assertIsNone(f.window(right,DAYS,'foreign'))

    def test_identity_dates_units_and_cutoff(self):
        rows=trades('069500')
        today=dict(rows[0],bizdate='20261109',organPureBuyQuant='-')
        observed=f.parse_trades('069500',[today]+rows,NOW.date()-timedelta(days=1))
        self.assertNotIn('2026-11-09',observed)
        self.assertEqual(observed[DAYS[-1]]['foreign'],-10)
        for fields in ({'itemCode':'091160'}, {'accumulatedTradingVolume':'-5'}, {'closePrice':'1,2'},
                       {'foreignerPureBuyQuant':'101'}, {'bizdate':'20261105'}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                f.parse_trades('069500',[dict(rows[0],**fields)]+rows[1:],NOW.date())

    def test_us_date_unit_sign_and_revision(self):
        header=['','10/28/2026','10/21/2026']
        rows=[header,['Equity','+1,234','-200'],['Bond','-12','0']]
        sample='<h2>Combined Estimated Long-Term Fund Flows</h2>Washington, DC; November 4, 2026. Millions of dollars<table>'+''.join('<tr>'+''.join('<td>'+v+'</td>' for v in row)+'</tr>' for row in rows)+'</table>'
        data=f.parse_ici_release(sample.encode(),NOW.date())
        self.assertEqual(data['weeks'][0],dict(day='2026-10-28',equity=1234,bond=-12))
        for bad in (sample.replace('Millions','Billions'),sample.replace('10/21','10/28'),sample.replace('Bond','Total')):
            with self.assertRaises(ValueError):
                f.parse_ici_release(bad.encode(),NOW.date())
        with tempfile.TemporaryDirectory() as tmp:
            f.import_ici(tmp,rows,date(2026,11,4),NOW)
            with self.assertRaises(ValueError):
                f.import_ici(tmp,rows,date(2026,11,3),NOW)
            self.assertEqual(f.view(tmp,NOW)['us']['weeks'],data['weeks'])
            self.assertTrue(f.view(tmp,NOW+timedelta(days=10))['us']['stale'])

    def test_failed_refresh_keeps_last_real_observation(self):
        root=tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        def fetch(url,params=None):
            if url==f.ICI:raise ValueError('offline')
            code=url.split('/')[-2]
            return json.dumps(trades(code)).encode()
        self.assertEqual(set(f.refresh(root.name,now=NOW,fetch=fetch)),{'us'})
        first=f.view(root.name,NOW)
        self.assertFalse(first['kr']['stale'])
        self.assertIsNone(first['us'])
        with patch.object(f,'parse_trades',side_effect=ValueError()):
            self.assertEqual(set(f.refresh(root.name,now=NOW,fetch=fetch)),{'kr','us'})
        self.assertEqual(f.view(root.name,NOW)['kr'],first['kr'])
        self.assertTrue(f.view(root.name,NOW+timedelta(days=1))['kr']['stale'])
        self.assertNotIn('/*FLOW_DATA*/',f.render_page(first))
        self.assertFalse((Path(root.name)/'data').exists())

