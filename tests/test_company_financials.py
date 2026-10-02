import json,tempfile,unittest
import threading
from http.server import HTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from pathlib import Path
from unittest.mock import Mock,patch
from investment.company_financials import FinancialMonitor,fetch_filings,acquire_lock,resolve_company
from investment.dart_statements import parse_viewer
from investment.live_dashboard import handler_for


class CompanyFinancialTests(unittest.TestCase):
    def test_name_fallback_still_requires_exact_ticker_identity(self):
        s=Mock();a=Mock();a.content=b'<table><tr><td>none</td></tr></table>';b=Mock();b.content=('<table><tr><td>0001A0</td></tr></table><input name="hiddenCikCD0" value="12345678"><input name="hiddenCikNM0" value="가상기업">').encode()
        s.post.side_effect=[a,b];self.assertEqual(resolve_company(s,'0001A0','가상기업')[0],'12345678')
        s.post.side_effect=[a,a]
        with self.assertRaises(ValueError):resolve_company(s,'0001A0','가상기업')

    def test_empty_day_requires_explicit_marker(self):
        session=Mock();session.post.return_value.content=b'<input id="totalCnt" value="0">'
        with self.assertRaises(ValueError):fetch_filings('2026-10-02',session=session)
        session.post.return_value.content='<input id="totalCnt" value="0">검색된 자료가 없습니다.'.encode()
        self.assertEqual(fetch_filings('2026-10-02',session=session),[])

    def test_abbreviated_net_requires_two_equations(self):
        def table(title,rows):
            return '<table><tr><td>'+title+'</td></tr><tr><td>2026.06.30 단위 : 원</td></tr></table><table>'+''.join('<tr><td>'+a+'</td><td>'+str(b)+'</td></tr>' for a,b in rows)+'</table>'
        html=table('연결 재무상태표',[('자산총계',100),('부채총계',40),('자본총계',60)])+table('연결 손익계산서',[
            ('매출액',100),('영업이익',15),('법인세비용차감전순이익',10),('법인세비용',3),
            ('분기',7),('지배기업소유주지분순이익',6),('비지배지분순이익(손실)',1)])+table('연결 현금흐름표',[('영업활동현금흐름',9)])
        def parse(text):return parse_viewer(text,code='298040',name='효성중공업',market='KOSPI',basis='CFS',year=2026,quarter=2,receipt='20260813001554',url='https://dart.fss.or.kr/report/viewer.do?rcpNo=20260813001554')
        self.assertEqual(parse(html)['values']['net_income'],7)
        with self.assertRaises(ValueError):parse(html.replace('<td>3</td>','<td>0</td>'))
        with self.assertRaises(ValueError):parse(html.replace('<td>6</td>','<td>2</td>'))
        with self.assertRaises(ValueError):parse(html.replace('2026.06.30','2026.03.31'))

    def test_public_aliases_and_total_attribution_reconcile(self):
        def table(title,rows):
            return '<table><tr><td>'+title+'</td></tr><tr><td>2026.06.30 단위 : 원</td></tr></table><table>'+''.join('<tr><td>'+a+'</td><td>'+str(b)+'</td></tr>' for a,b in rows)+'</table>'
        html=table('연결 재무상태표',[('자산총계',100),('부채총계',40),('자본총계',60),('비지배지분',10)])+table('연결 손익계산서',[
            ('영업수익',100),('매출액',100),('영업이익',15),('반기순이익',10),
            ('계속영업순이익의 귀속',''),('지배기업 소유주지분',6),('비지배지분',1),
            ('반기순이익의 귀속',''),('지배기업 소유주 귀속 반기순이익',9),('비지배지분',1),
            ('지배기업 총포괄손익',19),('비지배지분 총포괄손익',1)])+table('연결 현금흐름표',[('영업활동순현금흐름',9)])
        def parse(text):return parse_viewer(text,code='900000',name='가상 검증',market='KOSPI',basis='CFS',year=2026,quarter=2,receipt='20260813001554',url='https://dart.fss.or.kr/report/viewer.do?rcpNo=20260813001554')
        r=parse(html)['values'];self.assertEqual(r['revenue'],100);self.assertEqual(r['parent_net'],9);self.assertEqual(r['parent_equity'],50);self.assertEqual(r['ocf'],9)
        with self.assertRaises(ValueError):parse(html.replace('<td>매출액</td><td>100</td>','<td>매출액</td><td>99</td>'))
        mismatch=parse(html.replace('<td>9</td>','<td>7</td>'))['values'];self.assertNotIn('parent_net',mismatch)

    def test_numbered_loss_and_optional_ambiguity_preserve_core_financials(self):
        def table(title,rows):
            return '<table><tr><td>'+title+'</td></tr><tr><td>2026.06.30 단위 : 원</td></tr></table><table>'+''.join('<tr><td>'+a+'</td><td>'+str(b)+'</td></tr>' for a,b in rows)+'</table>'
        html=table('연결 재무상태표',[('자산 합계',100),('부채 합계',40),('기말자본',60)])+table('연결 손익계산서',[('Ⅰ. 매출액',100),('Ⅱ. 영업손실',3),('Ⅲ. 반기순이익',-2)])+table('연결 현금흐름표',[('Ⅰ. 영업활동순현금흐름',9),('현금및현금성자산의증가(감소)',5),('현금및현금성자산의증감',4)])
        r=parse_viewer(html,code='900000',name='가상 검증',market='KOSPI',basis='CFS',year=2026,quarter=2,receipt='20260813001554',url='https://dart.fss.or.kr/report/viewer.do?rcpNo=20260813001554')
        self.assertEqual(r['values']['operating_profit'],-3);self.assertEqual(r['values']['revenue'],100)
        self.assertEqual(r['values']['ocf'],9);self.assertNotIn('cash_change',r['values'])

    def test_explicit_consolidated_total_and_unlabelled_parent_require_two_equations(self):
        def table(title,rows):
            return '<table><tr><td>'+title+'</td></tr><tr><td>2026.06.30 단위 : 원</td></tr></table><table>'+''.join('<tr><td>'+a+'</td><td>'+str(b)+'</td></tr>' for a,b in rows)+'</table>'
        text=table('연결 재무상태표',[('자산총계',100),('부채총계',40),('자본총계',60)])+table('연결 손익계산서',[('매출액',100),('영업이익',15),('법인세차감전순이익',40),('법인세비용',10),('반기연결순이익',30),('반기순이익',20),('비지배지분',10)])+table('연결 현금흐름표',[('영업활동현금흐름',9)])
        def parse(html):return parse_viewer(html,code='900000',name='가상 검증',market='KOSPI',basis='CFS',year=2026,quarter=2,receipt='20260813001554',url='https://dart.fss.or.kr/report/viewer.do?rcpNo=20260813001554')
        r=parse(text)['values'];self.assertEqual(r['net_income'],30);self.assertEqual(r['parent_net'],20)
        with self.assertRaises(ValueError):parse(text.replace('<td>40</td>','<td>45</td>'))

    def test_monitor_scans_gap_and_only_refreshes_changed_saved_companies(self):
        with tempfile.TemporaryDirectory() as directory:
            dest=Path(directory)
            rows=[dict(code='028260',name='삼성물산',eligibility='candidate',metrics={'market_cap_eok':1000}),dict(code='298040',name='효성중공업',eligibility='candidate',metrics={'market_cap_eok':1000})]
            for row in rows:(dest/(row['code']+'.json')).write_text('{}')
            (dest/'monitor-status.json').write_text(json.dumps({'checked_on':'2026-10-01'}))
            filings=Mock(return_value=[dict(name='삼성물산',title='[기재정정]반기보고서 (2026.06)')])
            collector=Mock(return_value={'action':'defer'})
            service=Mock();service.running.return_value=False
            monitor=FinancialMonitor('.',service,filings=filings,collector=collector)
            with patch('investment.company_financials.folder',return_value=dest),patch('investment.company_financials.load_market_cache',return_value={'universe':{'companies':rows}}),patch('investment.company_financials.time.sleep'):
                monitor.run()
            self.assertEqual(collector.call_count,1)
            self.assertTrue(collector.call_args.kwargs['force'])
            self.assertEqual(collector.call_args.kwargs['extra_targets'],{(2026,2)})
            self.assertEqual(monitor.poll()['deferred'],1)
            self.assertEqual(monitor.poll()['status'],'complete')

    def test_monitor_failure_keeps_stamp_for_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            dest=Path(directory);stamp=dest/'monitor-status.json';stamp.write_text('{"checked_on":"2026-10-01"}')
            monitor=FinancialMonitor('.',Mock(),filings=Mock(side_effect=ValueError()))
            with patch('investment.company_financials.folder',return_value=dest),patch('investment.company_financials.load_market_cache',return_value={'universe':{'companies':[dict(code='028260',name='삼성물산',eligibility='candidate',metrics={'market_cap_eok':1000})]}}):monitor.run()
            self.assertEqual(monitor.poll()['status'],'failed')
            self.assertEqual(json.loads(stamp.read_text())['checked_on'],'2026-10-01')
            with acquire_lock(dest/'monitor.lock'):pass

    def test_lock_releases_without_deleting_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'monitor.lock'
            with acquire_lock(path):
                with self.assertRaises(ValueError):acquire_lock(path)
            with acquire_lock(path):pass


class FinancialRouteTests(unittest.TestCase):
    def setUp(self):
        self.financial=Mock();self.financial.poll.return_value={'status':'idle'}
        self.financial.start.return_value={'status':'running'}
        self.monitor=Mock();self.monitor.ensure_due.return_value={'status':'running','updated':0}
        self.server=HTTPServer(('127.0.0.1',0),handler_for('.',token='test',financial=self.financial,financial_monitor=self.monitor))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)

    def test_monitor_authentication(self):
        with self.assertRaises(HTTPError):urlopen(self.base+'/financial-monitor')
        self.monitor.ensure_due.assert_not_called()
        with urlopen(Request(self.base+'/financial-monitor',headers={'X-Dashboard-Token':'test'})) as response:
            self.assertEqual(json.load(response)['status'],'running')
        self.monitor.ensure_due.assert_called_once()

    def test_company_query_and_same_origin_mutation(self):
        path=self.base+'/company-financials?code=028260'
        with self.assertRaises(HTTPError):urlopen(Request(path,data=b'',headers={'X-Dashboard-Token':'test'},method='POST'))
        self.financial.start.assert_not_called()
        with urlopen(Request(path,data=b'',headers={'X-Dashboard-Token':'test','Origin':self.base},method='POST')) as response:
            self.assertEqual(response.status,202)
        self.financial.start.assert_called_once_with('028260')
        with self.assertRaises(HTTPError):urlopen(Request(self.base+'/company-financials?code=028260&code=298040',headers={'X-Dashboard-Token':'test'}))
