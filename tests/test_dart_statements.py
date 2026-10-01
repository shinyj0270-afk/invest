import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from investment.dart_statements import amount, quarter_records, valid_report, load_bundle
from tools.company_statements import api_check


def report(q, values=None, available=None):
    receipt = ['20230515000001','20230814000001','20231114000001','20240315000001'][q-1]
    end = ['03-31','06-30','09-30','12-31'][q-1]
    return dict(code='005930', name='삼성전자', market='KOSPI', basis='CFS', year=2023,
        quarter=q, period_end='2023-'+end, receipt=receipt,
        available_at=available or receipt[:4]+'-'+receipt[4:6]+'-'+receipt[6:8],
        url='https://dart.fss.or.kr/report/viewer.do?rcpNo='+receipt,
        source='DART', unit='KRW', values=values or dict(assets=200,liabilities=80,equity=120,
        revenue=q*100,operating_profit=q*10,net_income=q*5,ocf=q*15,cash_start=40,cash_end=40+q*2))


class DartStatementsTests(unittest.TestCase):
    def test_amount_negative_missing_zero(self):
        self.assertEqual(amount('(1,234.5)'),-1234.5)
        self.assertEqual(amount('0'),0)
        self.assertIsNone(amount('—'))
        self.assertIsNone(amount('연결 123'))

    def test_quarter_flows_and_cash_opening(self):
        rows=quarter_records([report(q) for q in range(1,5)],'2024-04-01')
        quarters=[r for r in rows if r['cadence']=='quarter']
        self.assertEqual([r['revenue'] for r in quarters],[100]*4)
        self.assertEqual(quarters[1]['ocf'],15)
        self.assertEqual(quarters[1]['cash_start'],42)
        self.assertEqual(quarters[3]['assets'],200)
        self.assertEqual(rows[-1]['revenue'],400)

    def test_missing_prior_never_zero(self):
        r=quarter_records([report(2)],'2024-04-01')[0]
        self.assertIsNone(r['revenue']);self.assertIsNone(r['ocf']);self.assertIsNone(r['cash_start'])
        self.assertEqual(r['assets'],200)

    def test_prior_submission_after_cutoff(self):
        self.assertEqual(quarter_records([report(1,available='2024-06-01'),report(2)],'2024-04-01'),[])

    def test_reject_unsafe_and_invalid_values(self):
        self.assertTrue(valid_report(report(1)))
        for key,value in [('url','javascript:alert(1)'),('basis','unknown'),('quarter',True),
                          ('period_end','2023-04-30'),('available_at','2023-01-01')]:
            r=report(1);r[key]=value;self.assertFalse(valid_report(r),key)
        for bad in [float('inf'),float('nan'),True,None]:
            r=report(1);r['values']['assets']=bad;self.assertFalse(valid_report(r))
        r=report(1);r['values']['equity']=1e9;self.assertFalse(valid_report(r))

    def test_bundle_identity_duplicate_and_future(self):
        snapshot=dict(companies=[dict(code='005930',name='삼성전자',market='KOSPI')],meta=dict(price_date='2023-09-01'))
        bundle=dict(schema='dart-public-statements-1',unit='KRW',companies={'005930':dict(reports=[report(1),report(2),report(3)])})
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'data.json'
            def run(data):
                p.write_text(json.dumps(data),encoding='utf-8');return load_bundle(p,snapshot)
            self.assertEqual(len(run(bundle)['005930']['periods']),2)
            duplicate=copy.deepcopy(bundle);duplicate['companies']['005930']['reports'].append(report(1))
            self.assertEqual(run(duplicate),{})
            wrong=copy.deepcopy(bundle);wrong['companies']['005930']['reports'][0]['name']='다른회사'
            self.assertEqual(run(wrong),{})

    def test_api_balance_crosscheck_and_redaction(self):
        r=report(1);session=Mock();response=session.get.return_value
        response.json.return_value={'status':'000','list':[dict(account_id='ifrs-full_'+k,sj_div='BS',
            rcept_no=r['receipt'],corp_code='00126380',thstrm_amount=str(v))
            for k,v in [('Assets',200),('Liabilities',80),('Equity',120)]]}
        api_check(session,'synthetic-key','00126380',2023,1,'CFS',r)
        self.assertEqual(r['api_checked'],['assets','liabilities','equity'])
        self.assertNotIn('synthetic-key',json.dumps(r))
        response.json.return_value={'status':'010','message':'synthetic-key'}
        with self.assertRaisesRegex(ValueError,'상태 010') as error:
            api_check(session,'synthetic-key','00126380',2023,1,'CFS',r)
        self.assertNotIn('synthetic-key',str(error.exception))
