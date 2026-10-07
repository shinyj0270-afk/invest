import copy,hashlib,json,tempfile,unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock,patch
from investment.fiscal_contract import fiscal_bounds,validate_contract,contiguous_quarters
from investment.dart_statements import parse_viewer,valid_report,quarter_records,load_bundle
from investment.native_financial import build_native_payload,native_payload_at,financial_completeness
from investment.financial_table import build_table
from investment.financial_metrics import common_metrics
from investment.financial_update_policy import decide_update
from tools.company_statements import collect_receipt


def fiscal_report(fy=2026,month=3,q=2,currency='KRW',basis='CFS',multiple=1,available='2026-08-13',segment=None):
    start,end=fiscal_bounds(fy,month,q);receipt=available.replace('-','')+'001554'
    title_prefix='연결 ' if basis=='CFS' else ''
    def table(title,context,rows):
        current='당기말' if context=='balance' else '당기누적'
        dates=end.isoformat().replace('-','.') if context=='balance' else start.isoformat().replace('-','.')+' 부터 '+end.isoformat().replace('-','.')+' 까지'
        first='<table><tr><td>'+title_prefix+title+'</td></tr><tr><td>'+current+' '+dates+'</td></tr><tr><td>전기말 2020.01.01</td></tr><tr><td>(단위 : '+('원' if currency=='KRW' else 'USD')+')</td></tr></table>'
        header='<tr><td></td><td>'+current+'</td><td>전기</td></tr>'
        return first+'<table>'+header+''.join('<tr><td>'+label+'</td><td>'+str(value)+'</td><td>999</td></tr>' for label,value in rows)+'</table>'
    text=table('재무상태표','balance',[('자산총계',1000),('부채총계',400),('자본총계',600),('비지배지분',100)])+table('손익계산서','income',[('매출액',100*multiple),('영업이익',20*multiple),('당기순이익',10*multiple),('지배기업소유주지분순이익',8*multiple),('비지배지분순이익(손실)',2*multiple),('기본주당이익',1.5*multiple)])+table('현금흐름표','cash',[('영업활동현금흐름',15*multiple),('기초현금및현금성자산',10),('기말현금및현금성자산',10+15*multiple)])
    url='https://dart.fss.or.kr//report/viewer.do?rcpNo='+receipt+'&dcmNo=123&eleId=19&offset=10&length=999&dtd=dart4.xsd'
    contract=dict(fiscal_year=fy,fiscal_quarter=q,year_end_month=month,period_start=start.isoformat(),period_end=end.isoformat(),currency=currency,calendar_segment=segment or f'calendar-{month}',report_kind='annual' if q==4 else 'half' if q==2 else 'quarter',source=dict(receipt=receipt,url=url,sha256=hashlib.sha256(text.encode()).hexdigest(),available_at=available),current_columns={c:dict(title_row=1,header_row=0,header_column=1,value_column=1,label='당기말' if c=='balance' else '당기누적') for c in ('balance','income','cash')})
    args=dict(code='900000',name='가상 기업',market='KOSPI',basis=basis,year=fy,quarter=q,receipt=receipt,url=url,period_contract=contract)
    return parse_viewer(text,**args),text,args


class FiscalNativeTests(unittest.TestCase):
    def test_march_june_september_november_and_leap_bounds(self):
        for month in (3,6,9,11):
            r,_,_=fiscal_report(month=month,q=4,available='2027-03-01')
            self.assertTrue(valid_report(r));self.assertEqual(r['period_end'][5:7],f'{month:02d}')
            self.assertEqual(len(quarter_records([r],'2027-03-01')),2)
        r,_,_=fiscal_report(fy=2024,month=11,q=1,available='2024-04-01')
        self.assertEqual(r['period_end'],'2024-02-29')

    def test_comparative_end_does_not_prove_current_period(self):
        r,text,args=fiscal_report()
        wrong=text.replace(' 당기누적',' 当期') if False else text.replace('당기누적 2025.04.01 부터 2025.09.30 까지','당기누적 2025.04.01 부터 2025.06.30 까지')
        args=copy.deepcopy(args);args['period_contract']['source']['sha256']=hashlib.sha256(wrong.encode()).hexdigest()
        with self.assertRaises(ValueError):parse_viewer(wrong,**args)
        swapped=text.replace('<td>당기말</td><td>전기</td>','<td>전기</td><td>당기말</td>')
        args['period_contract']['source']['sha256']=hashlib.sha256(swapped.encode()).hexdigest()
        with self.assertRaises(ValueError):parse_viewer(swapped,**args)

    def test_all_three_current_periods_currency_and_unsupported_scale(self):
        _,text,args=fiscal_report(currency='USD')
        for wrong in (text.replace('(단위 : USD)','(단위 : 만USD)',1),text.replace('(단위 : USD)','(단위 : 원)',1),text.replace('(단위 : USD)','(단위 : 억USD)',1)):
            params=copy.deepcopy(args);params['period_contract']['source']['sha256']=hashlib.sha256(wrong.encode()).hexdigest()
            with self.assertRaises(ValueError):parse_viewer(wrong,**params)

    def test_parent_attribution_loss_marker_requires_two_equations(self):
        _,text,args=fiscal_report(month=6,q=4,multiple=1)
        marker='<tr><td>당기순이익(손실)의 귀속</td><td></td><td></td></tr>'
        equations='<tr><td>법인세비용차감전순이익</td><td>13</td><td>999</td></tr><tr><td>법인세비용</td><td>3</td><td>999</td></tr>'
        total='<tr><td>당기순이익</td><td>10</td><td>999</td></tr>'
        text=text.replace(total,equations+total+marker+'<tr><td>당기순이익</td><td>8</td><td>999</td></tr>')
        args['period_contract']['source']['sha256']=hashlib.sha256(text.encode()).hexdigest()
        record=parse_viewer(text,**args);self.assertEqual(record['values']['net_income'],10);self.assertEqual(record['values']['parent_net'],8)
        wrong=text.replace('<td>13</td>','<td>15</td>');args['period_contract']['source']['sha256']=hashlib.sha256(wrong.encode()).hexdigest()
        with self.assertRaises(ValueError):parse_viewer(wrong,**args)

    def test_adjacent_ytd_subtraction_independent_arithmetic_eps_and_availability(self):
        a,_,_=fiscal_report(q=1,multiple=1,available='2025-08-15');b,_,_=fiscal_report(q=2,multiple=3,available='2025-11-15')
        records=quarter_records([a,b],'2025-11-15');q2=next(p for p in records if p['cadence']=='quarter' and p['fiscal_quarter']==2)
        self.assertEqual(q2['revenue'],200);self.assertEqual(q2['operating_profit'],40);self.assertEqual(q2['ocf'],30);self.assertIsNone(q2['eps'])
        self.assertEqual(q2['period_start'],'2025-07-01');self.assertEqual(q2['available_at'],'2025-11-15')
        self.assertEqual(len(q2['dependencies']),2)

    def test_future_prior_missing_q3_does_not_hide_independent_annual(self):
        prior,_,_=fiscal_report(q=3,multiple=3,available='2026-09-01');annual,_,_=fiscal_report(q=4,multiple=4,available='2026-06-01')
        records=quarter_records([prior,annual],'2026-06-01')
        self.assertEqual([p['cadence'] for p in records],['annual']);self.assertEqual(records[0]['revenue'],400)
        records=quarter_records([annual],'2026-06-01')
        self.assertEqual(next(p for p in records if p['cadence']=='annual')['revenue'],400)
        self.assertIsNone(next(p for p in records if p['cadence']=='quarter')['revenue'])

    def test_currency_segment_company_basis_transition_never_subtract(self):
        a,_,_=fiscal_report(q=1,multiple=1,available='2025-08-15');b,_,_=fiscal_report(q=2,multiple=3,available='2025-11-15')
        for field,value in [('currency','USD'),('calendar_segment','transition'),('code','900001'),('basis','OFS')]:
            changed=copy.deepcopy(a);changed[field]=value
            q2=next(p for p in quarter_records([changed,b],'2025-11-15') if p['cadence']=='quarter' and p['fiscal_quarter']==2)
            self.assertIsNone(q2['revenue'])
        short=copy.deepcopy(b['period_contract']);short['period_start']='2025-05-01'
        with self.assertRaises(ValueError):validate_contract(short)

    def test_native_usd_preserved_ratios_krw_valuation_pending_and_ttm(self):
        reports=[fiscal_report(fy=fy,month=11,q=q,currency='USD',multiple=q,available='2027-03-01')[0] for fy in (2025,2026) for q in (1,2,3,4)]
        payload=build_native_payload(reports,'2027-03-01');f=payload['common_financial']
        self.assertTrue(f['ttm_complete']);self.assertEqual(f['ttm_ocf'],60)
        self.assertEqual(f['metrics']['operating_margin_pct'],20);self.assertAlmostEqual(f['metrics']['revenue_growth_pct'],0)
        self.assertAlmostEqual(f['metrics']['roe_pct'],32/500*100)
        self.assertIsNone(f['metrics']['per']);self.assertIsNone(f['metrics']['pbr']);self.assertEqual(f['amounts'],{})
        self.assertEqual(f['currency'],'USD');self.assertEqual(payload['groups'][0]['amount_unit'],'백만 USD')
        qs=[p for g in payload['groups'] if g['cadence']=='quarter' for p in g['columns']]
        self.assertTrue(contiguous_quarters(qs[-4:]))

    def test_older_cutoff_native_filter_and_mismatched_identity(self):
        r,_,_=fiscal_report(currency='USD',available='2026-08-13');payload=build_native_payload([r],'2026-10-07')
        old=native_payload_at(payload,'2026-06-30');self.assertEqual(old['groups'],[]);self.assertIsNone(old['common_financial'])
        row=dict(code='900000',name='가상 기업',market='KOSPI')
        snapshot=dict(meta=dict(price_date='2026-06-30',data_mode='user_input'))
        source=dict(row,periods=[],native_financial=payload)
        table=build_table(row,snapshot,source);self.assertIsNone(common_metrics(row,table))
        source['name']='다른 회사';snapshot['meta']['price_date']='2026-10-07'
        self.assertIsNone(build_table(row,snapshot,source)['native_financial'])

    def test_completeness_latest_not_equal_ttm_or_roe(self):
        r,_,_=fiscal_report(q=2,multiple=2)
        c=build_native_payload([r],'2026-10-07')['completeness']
        self.assertEqual(c['latest_stored']['status'],'ready');self.assertEqual(c['ttm']['status'],'pending');self.assertEqual(c['required_accounts']['status'],'pending');self.assertEqual(c['roe']['status'],'pending')

    def test_krw_native_does_not_wait_for_fx_but_usd_does(self):
        krw,_,_=fiscal_report(q=1);usd,_,_=fiscal_report(q=1,currency='USD')
        a=build_native_payload([krw],'2026-10-07');b=build_native_payload([usd],'2026-10-07')
        self.assertEqual(a['fx']['status'],'not_required');self.assertEqual(b['fx']['status'],'pending')
        self.assertIn('가격·시총',a['common_financial']['metric_details']['per']['reason']);self.assertIn('환산 불필요',a['common_financial']['metric_details']['pbr']['reason'])
        self.assertIn('검증된 환산',b['common_financial']['metric_details']['per']['reason'])
        self.assertEqual(native_payload_at(a,'2026-10-01')['fx']['status'],'not_required')

    def test_contract_change_review_precedes_seven_percent(self):
        r,_,_=fiscal_report();before={'companies':{'900000':{'reports':[r]}}}
        for field,value in [('currency','USD'),('calendar_segment','changed'),('period_start','2025-05-01')]:
            after=copy.deepcopy(before);changed=after['companies']['900000']['reports'][0];changed[field]=value;changed['values']['revenue']=9999
            self.assertEqual(decide_update(before,after)['reason'],'financial_contract_changed')

    def test_fiscal_quarter_and_native_roe_keep_source_tolerance_notes(self):
        reports=[fiscal_report(fy=fy,month=9,q=q,multiple=q,available='2027-03-01')[0] for fy in (2025,2026) for q in (1,2,3,4)]
        _,text,args=fiscal_report(fy=2026,month=9,q=1,multiple=1,available='2027-03-01')
        text=text.replace('<td>지배기업소유주지분순이익</td><td>8</td>','<td>지배기업소유주지분순이익</td><td>11</td>')
        args['period_contract']['source']['sha256']=hashlib.sha256(text.encode()).hexdigest()
        changed=parse_viewer(text,**args);self.assertTrue(valid_report(changed));self.assertEqual(changed['reconciliation_notes']['parent_net']['difference_krw'],3)
        reports[4]=changed;payload=build_native_payload(reports,'2027-03-01')
        q1=next(p for g in payload['groups'] if g['cadence']=='quarter' for p in g['columns'] if p['fiscal_year']==2026 and p['fiscal_quarter']==1)
        self.assertIn('잔차 +3 KRW',q1['cell_notes']['parent_net'])
        detail=payload['common_financial']['metric_details']['roe_pct']
        self.assertTrue(detail['within_tolerance']);self.assertEqual(detail['status'],'reference_with_tolerance');self.assertIn('2025-12-31',detail['reason'])

    def test_legacy_annual_own_availability_independent_future_q3(self):
        a=dict(code='900000',basis='CFS',year=2025,quarter=3,period_end='2025-09-30',available_at='2026-08-01',source='synthetic',url='https://example.test/3',receipt='20260801000001',values=dict(revenue=300,operating_profit=60,net_income=30,ocf=40))
        b=dict(a,quarter=4,period_end='2025-12-31',available_at='2026-04-01',values=dict(revenue=400,operating_profit=80,net_income=40,ocf=60))
        periods=quarter_records([a,b],'2026-04-01');self.assertEqual(len(periods),1);self.assertEqual(periods[0]['cadence'],'annual');self.assertEqual(periods[0]['available_at'],'2026-04-01');self.assertEqual(periods[0]['revenue'],400)

    def test_explicit_native_bundle_keeps_usd_out_of_krw_periods(self):
        r,_,_=fiscal_report(currency='USD');bundle=dict(schema='dart-native-statements-1',unit='native',companies={'900000':{'reports':[r]}})
        snapshot=dict(meta=dict(price_date='2026-10-07'),companies=[dict(code='900000',name='가상 기업',market='KOSPI')])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bundle.json';path.write_text(json.dumps(bundle),encoding='utf-8');value=load_bundle(path,snapshot)['900000']
            self.assertEqual(value['periods'],[]);self.assertEqual(value['native_financial']['status'],'ready')

    def test_verified_receipt_route_binds_company_tree_hash_and_kind(self):
        r,text,args=fiscal_report(month=6,q=4,available='2026-09-22')
        entry=dict(basis='CFS',year=2026,quarter=4,period_contract=args['period_contract']);corp='12345678';receipt=r['receipt']
        main=f"<span onclick=\"openCorpInfoNew('{corp}', 'winCorpInfo', '/dsae001/selectPopup.ax');\">가상 기업</span>"+''.join("node1['"+k+"'] = \""+v+"\";" for k,v in dict(rcpNo=receipt,dcmNo='123',eleId='19',offset='10',length='999',dtd='dart4.xsd').items())+"node1['tocNo']='19';"
        session=Mock();session.get.side_effect=[Mock(content=main.encode()),Mock(content=text.encode())]
        with tempfile.TemporaryDirectory() as tmp,patch('investment.company_financials.resolve_company',return_value=(corp,'가상 기업')),patch('investment.company_financials.fetch_filings',return_value=[dict(receipt=receipt,corp=corp,name='가상 기업',title='사업보고서 (2026.06)')]):
            collected=collect_receipt(session,entry,Path(tmp),code='900000',name='가상 기업',market='KOSPI')
            self.assertEqual(collected['collection_route'],'verified_receipt_inventory');self.assertTrue(valid_report(collected))
            self.assertNotIn('selectYear',str(session.post.call_args_list))
        session=Mock()
        with tempfile.TemporaryDirectory() as tmp,patch('investment.company_financials.resolve_company',return_value=('87654321','가상 기업')),patch('investment.company_financials.fetch_filings',return_value=[dict(receipt=receipt,corp=corp,name='가상 기업',title='사업보고서')]):
            with self.assertRaises(ValueError):collect_receipt(session,entry,Path(tmp),code='900000',name='가상 기업',market='KOSPI')
            self.assertEqual(session.get.call_count,0)

if __name__=='__main__':unittest.main()
