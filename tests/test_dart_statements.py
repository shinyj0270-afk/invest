import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from investment.dart_statements import amount, quarter_records, valid_report, load_bundle, displayed_debt, parse_viewer, reconciliation_reference
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
    def test_explicit_same_statement_reference_discloses_small_residual(self):
        r=report(1);r['values'].update(net_income=13351375878,parent_net=12526499343,nci_net=824876444)
        raw=[{'label':'지배기업의 소유주에게 귀속되는 당기순이익(손실)','value':12526499343},
             {'label':'비지배지분에 귀속되는 당기순이익(손실)','value':824876444}]
        r['raw']={'income':raw};r['units']={'income':1};r['reconciliation_notes']=reconciliation_reference(r['values'],raw,'income',1)
        self.assertEqual(r['reconciliation_notes']['parent_net']['difference_krw'],-91)
        self.assertTrue(valid_report(r))
        quarters=quarter_records([r],'2024-04-01')
        self.assertIn('-91',quarters[0]['cell_notes']['parent_net'])
        forged=copy.deepcopy(r);forged['reconciliation_notes']['parent_net']['difference_krw']=0
        self.assertFalse(valid_report(forged))
        ambiguous=raw+[dict(raw[0],value=12526499344)]
        self.assertEqual(reconciliation_reference(dict(r['values']),ambiguous,'income',1),{})
        boundary=dict(r['values'],net_income=12526499343+824876444+100000000)
        self.assertEqual(reconciliation_reference(boundary,raw,'income',1),{})

    def test_attribution_balances_must_reconcile_at_reported_precision(self):
        r=report(1);r['units']={'balance':1,'income':1}
        r['values'].update(parent_net=4,nci_net=1,parent_equity=100,nci=20)
        self.assertTrue(valid_report(r))
        for key in ('parent_net','parent_equity'):
            bad=copy.deepcopy(r);bad['values'][key]+=2
            self.assertFalse(valid_report(bad),key)
        rounded=copy.deepcopy(r);rounded['values']['parent_net']+=1
        self.assertTrue(valid_report(rounded))

    def test_cache_repair_reparses_html_and_withholds_conflicting_attribution(self):
        from tools.complete_financials import repair_saved
        def table(title,rows):
            return '<table><tr><td>'+title+'</td></tr><tr><td>2023.03.31 단위 : 원</td></tr></table><table>'+''.join('<tr><td>'+k+'</td><td>'+str(v)+'</td></tr>' for k,v in rows)+'</table>'
        html=table('연결 재무상태표',[('자산총계',20000000000),('부채총계',8000000000),('자본총계',12000000000),('지배기업소유주지분',12000000000),('비지배지분',2000000000)])+table('연결 손익계산서',[('매출액',100),('영업이익',10),('분기순이익',5),('지배기업소유주',3),('비지배지분',0)])+table('연결 현금흐름표',[('영업활동현금흐름',15)])
        keys={k:report(1)[k] for k in ('code','name','market','basis','year','quarter','receipt','url')}
        parsed=parse_viewer(html,**keys)
        self.assertTrue(valid_report(parsed))
        for key in ('parent_net','nci_net','parent_equity','nci'):self.assertNotIn(key,parsed['values'])
        old=copy.deepcopy(parsed);old['values'].update(parent_net=3,nci_net=0,parent_equity=120,nci=20)
        old.update(parser_version=8,sha256=hashlib.sha256(html.encode()).hexdigest())
        bundle=dict(schema='dart-public-statements-1',unit='KRW',companies={'005930':dict(reports=[old])})
        with tempfile.TemporaryDirectory() as directory:
            dest=Path(directory);sources=dest/'sources';sources.mkdir()
            source=sources/'005930-CFS-2023q1.json';source.write_text(json.dumps(old),encoding='utf-8')
            source.with_suffix('.html').write_text(html,encoding='utf-8')
            target=dest/'005930.json';target.write_text(json.dumps(bundle),encoding='utf-8')
            result=repair_saved(dest)
            self.assertEqual(result['repaired_companies'],1);self.assertEqual(result['revalidation_failures'],[])
            repaired=json.loads(target.read_text(encoding='utf-8'))['companies']['005930']['reports'][0]
            self.assertEqual(repaired['values'],parsed['values']);self.assertEqual(repaired['parser_version'],10)
            self.assertEqual(repaired['sha256'],old['sha256'])

    def test_displayed_debt_does_not_add_subtotals_leases_or_missing_as_zero(self):
        rows=[{'label':k,'value':v} for k,v in [('유동부채',100),('차입금및사채',30),('단기차입금',20),('사채',10),('비유동부채',200),('장기차입금',40),('리스부채',9)]]
        self.assertEqual(displayed_debt(rows),70)
        self.assertIsNone(displayed_debt([{'label':'리스부채','value':9}]))
        self.assertEqual(displayed_debt([{'label':'단기차입금','value':0}]),0)
        self.assertIsNone(displayed_debt([{'label':'사채','value':50},{'label':'전환사채','value':30}]))

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

    def test_quarter_eps_is_not_difference_of_weighted_share_denominators(self):
        # Q1 profit 100 / 100 shares = 1; Q2 profit 400 / 200 shares = 2.
        # H1 profit 500 / 150 weighted shares differs from the sum of EPS.
        reports=[report(q) for q in range(1,5)]
        for r,profit,eps in zip(reports,(100,500,800,1100),(1,500/150,800/(500/3),1100/175)):
            r['values'].update(net_income=profit,eps=eps)
        rows=quarter_records(reports,'2024-04-01')
        quarters=[r for r in rows if r['cadence']=='quarter']
        self.assertNotEqual(reports[1]['values']['eps']-reports[0]['values']['eps'],400/200)
        self.assertEqual([r['eps'] for r in quarters],[1,None,None,None])
        self.assertEqual([r['net_income'] for r in quarters],[100,400,300,300])
        annual=next(r for r in rows if r['cadence']=='annual')
        self.assertEqual(annual['eps'],1100/175)

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
