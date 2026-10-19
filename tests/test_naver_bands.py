"""Public band response validation, independently from accounting calculations."""
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone
from investment.naver_bands import parse_bands, NaverBands


class BandTests(unittest.TestCase):
    def raw(self):
        stamp=lambda d:int(datetime.fromisoformat(d).replace(tzinfo=timezone.utc).timestamp()*1000)
        chart={'name':{'VAL1':'10배','VAL2':'5배','VAL3':'2배','VAL4':'0배'},
               'price':[{'x':stamp('2026-09-30'),'y':100},{'x':stamp('2026-10-16'),'y':120},
                        {'x':stamp('2026-11-30'),'y':None}]}
        for i in range(1,5):chart['val'+str(i)]=[dict(p,y=100/i) for p in chart['price']]
        return {'bandChart1':chart,'bandChart2':chart}

    def test_observed_prices_only_and_source_labels_preserved(self):
        data=parse_bands(self.raw(),'000660','CFS','2026-10-19T16:00:00+09:00')
        self.assertEqual(data['basis'],'CFS')
        self.assertEqual([p['period_end'] for p in data['bands']['per']['rows']],['2026-09-30','2026-10-16'])
        self.assertEqual(data['bands']['per']['labels'][0],'10배')
        self.assertNotIn('pcr',data['bands'])

    def test_malformed_dates_duplicates_and_alignment_are_rejected(self):
        for mutate in (lambda c:c['price'].append(c['price'][0]),
                       lambda c:c['val1'].pop(),
                       lambda c:c['val1'][0].update(x=0),
                       lambda c:c['price'][0].update(y=float('inf'))):
            raw=self.raw();mutate(raw['bandChart1'])
            with self.assertRaises(ValueError):parse_bands(raw,'000660','CFS','2026-10-19T16:00:00+09:00')

    def test_identity_and_basis(self):
        for code,basis in [('bad','CFS'),('000660','MAIN')]:
            with self.assertRaises(ValueError):parse_bands(self.raw(),code,basis,'2026-10-19T16:00:00+09:00')

    def test_lookup_caches_per_symbol_and_basis_without_files(self):
        response=MagicMock(status_code=200,content=b'{}')
        response.json.return_value=self.raw()
        with patch('investment.naver_bands.requests.Session') as session, patch('investment.naver_bands.fetch_references',return_value={'companies':{}}):
            session.return_value.__enter__.return_value.get.return_value=response
            service=NaverBands()
            a=service.lookup('000660','CFS');a['bands'].clear()
            self.assertIn('per',service.lookup('000660','CFS')['bands'])
            self.assertEqual(session.call_count,1)
            service.lookup('000660','OFS')
            self.assertEqual(session.call_count,2)

    def test_failure_does_not_promote_reference_or_expose_exception(self):
        with patch('investment.naver_bands.requests.Session') as session, patch('investment.naver_bands.fetch_references',return_value={'companies':{}}):
            session.return_value.__enter__.return_value.get.side_effect=ValueError('private diagnostic')
            value=NaverBands().lookup('000660','CFS')
            self.assertEqual(value['status'],'unavailable')
            self.assertNotIn('private diagnostic',str(value))


if __name__=='__main__':unittest.main()
