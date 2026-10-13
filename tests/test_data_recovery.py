import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from investment.data_recovery import DataRecovery
from investment.collection_failure import failure_detail
from investment.company_financials import collect_company
from http.server import HTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import threading
from investment.live_dashboard import handler_for


class RecoveryTests(unittest.TestCase):
    def test_inventory_and_target_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);fin=base/'work/company-financials';fin.mkdir(parents=True)
            (fin/'005930.status.json').write_text(json.dumps(dict(status='failed',**failure_detail(ValueError('DART 종목 식별 불일치'),financial=True))),encoding='utf-8')
            cache=dict(universe=dict(companies=[dict(code='005930',name='Example',eligibility='candidate',metrics={'market_cap_eok':2000})]),history=dict(errors=[dict(code='005930',reason='old')]))
            daily=Mock();financial=Mock();daily.poll.return_value={};financial.poll.return_value={}
            service=DataRecovery(base,daily,financial)
            with patch('investment.data_recovery.load_local',return_value=dict(data_dir=base,profile='work')),patch('investment.data_recovery.read_market_cache',return_value=cache):
                result=service.view();self.assertEqual(len(result['failures']),2)
                self.assertEqual(result['failures'][0]['stage'],'identity')
                service.retry('price','005930');daily.start.assert_called_once_with(codes=['005930'])
                service.retry('financial','005930');financial.start.assert_called_once_with('005930',retry=True)
                with self.assertRaises(ValueError):service.retry('price','000660')
                with self.assertRaises(ValueError):service.retry('unknown','005930')
                with self.assertRaises(ValueError):service.retry('financial','../abc')

    def test_old_failure_superseded_by_new_verified_observation_and_ineligible_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);dest=base/'work/company-financials';dest.mkdir(parents=True)
            for code in ('005930','000660'):
                (dest/(code+'.status.json')).write_text(json.dumps(dict(status='failed',checked_at='2026-10-01T09:00:00+09:00')),encoding='utf-8')
            (dest/'005930.json').write_text(json.dumps(dict(companies={'005930':dict(reports=[{}])})),encoding='utf-8')
            (dest/'005930.observed.json').write_text(json.dumps(dict(retrieved_on='2026-10-02')),encoding='utf-8')
            cache=dict(universe=dict(companies=[dict(code='005930',eligibility='candidate',metrics={'market_cap_eok':2000}),dict(code='000660',eligibility='candidate',metrics={'market_cap_eok':10})]))
            service=DataRecovery(base,Mock(),Mock())
            with patch('investment.data_recovery.load_local',return_value=dict(data_dir=base,profile='work')),patch('investment.data_recovery.read_market_cache',return_value=cache):
                failures=service.view()['failures'];self.assertEqual([f['code'] for f in failures],['000660'])
                self.assertFalse(failures[0]['can_retry']);self.assertFalse(failures[0]['eligible'])
                with self.assertRaises(ValueError):service.retry('financial','000660')

    def test_financial_failure_keeps_reason_without_raw_exception(self):
        with tempfile.TemporaryDirectory() as temp:
            dest=Path(temp)
            with patch('investment.company_financials.folder',return_value=dest),patch('investment.company_financials._collect_company',side_effect=OSError('secret/path')):
                with self.assertRaises(OSError):collect_company(dest,dict(code='005930'),'2026-10-13')
            saved=json.loads((dest/'005930.status.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['stage'],'network');self.assertIn('retry_at',saved)
            self.assertNotIn('secret',json.dumps(saved))

    def test_identity_diagnostic_is_specific(self):
        self.assertEqual(failure_detail(ValueError('DART 종목 식별 불일치'),financial=True)['stage'],'identity')

    def test_recovery_route_requires_token_and_same_origin(self):
        service=Mock();service.view.return_value={'failures':[]};service.retry.return_value={'status':'running'}
        with patch('investment.data_recovery.DataRecovery',return_value=service):
            server=HTTPServer(('127.0.0.1',0),handler_for('.',token='test'))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        base=f'http://127.0.0.1:{server.server_port}'
        with self.assertRaises(HTTPError) as error:urlopen(base+'/data-recovery')
        self.assertEqual(error.exception.code,403);service.view.assert_not_called()
        with urlopen(Request(base+'/data-recovery',headers={'X-Dashboard-Token':'test'})) as response:self.assertEqual(json.load(response),{'failures':[]})
        body=json.dumps(dict(kind='financial',code='005930')).encode()
        with self.assertRaises(HTTPError) as error:urlopen(Request(base+'/data-recovery',data=body,headers={'X-Dashboard-Token':'test'}))
        self.assertEqual(error.exception.code,403);service.retry.assert_not_called()
        with urlopen(Request(base+'/data-recovery',data=body,headers={'X-Dashboard-Token':'test','Origin':base})) as response:self.assertEqual(response.status,202)
        service.retry.assert_called_once_with('financial','005930')
        service.retry.side_effect=ValueError('bad target')
        with self.assertRaises(HTTPError) as error:urlopen(Request(base+'/data-recovery',data=body,headers={'X-Dashboard-Token':'test','Origin':base}))
        self.assertEqual(error.exception.code,400)


if __name__=='__main__':unittest.main()
