"""Daily summary tests with synthetic observations, never user holdings."""
import copy
import json
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from investment.daily_dashboard import daily_model, market_rows
from investment.holdings_bridge import holdings_input, linked_dashboard
from tests import test_infomax_daily


class DailyDashboardTests(unittest.TestCase):
    def setUp(self):
        helper=test_infomax_daily.DailyImportTests(); helper.setUp(); self.snapshot=helper.convert()
        self.context=dict(pending={},rows=[],receipt={'status':'partial'},error=None)
        self.receipt=dict(stale=True,target_date='2026-09-29',status='cached',checked_at='2026-09-30')

    def test_market_missing_is_not_undated_metric_or_zero(self):
        rows=market_rows(self.snapshot,{})
        self.assertEqual(rows[0]['관측종가'],100)
        del self.snapshot['companies'][0]['prices']
        self.snapshot['companies'][0]['metrics']['price']=123456
        rows=market_rows(self.snapshot,None)
        self.assertIsNone(rows[0]['관측종가'])
        self.assertIsNone(rows[0]['가격일'])
        self.assertIsNone(rows[0]['주요이벤트'])

    def test_existing_engine_holdings_and_null_total_preserved(self):
        holdings=holdings_input(self.snapshot,'2026-09-30')
        holdings['holdings']=[dict(code=self.snapshot['companies'][0]['code'],quantity=2,avg_cost_krw=50)]
        original=copy.deepcopy((self.snapshot,holdings))
        model=daily_model(self.snapshot,self.receipt,self.context,holdings,as_of='2026-09-30')
        result=model['analysis']
        self.assertEqual(result['holdings_review']['rows'][0]['value_krw'],200)
        self.assertEqual(result['holdings_review']['rows'][0]['opinion'],'WAIT')
        self.assertIsNone(result['holdings_review']['book']['total_krw'])
        self.assertEqual(result['portfolio_status'],'SETTINGS_REQUIRED')
        self.assertEqual((self.snapshot,holdings),original)

    def test_staleness_uses_displayed_snapshot_not_previous_receipt(self):
        receipt=dict(self.receipt,stale=False)
        model=daily_model(self.snapshot,receipt,self.context,as_of='2026-09-30')
        self.assertTrue(any('오래되었습니다' in s for s in model['issues']))
        receipt.update(stale=True,target_date='2026-09-26')
        model=daily_model(self.snapshot,receipt,self.context,as_of='2026-09-30')
        self.assertFalse(any('오래되었습니다' in s for s in model['issues']))

    def test_engine_failure_keeps_market_data_and_hides_private_error(self):
        with patch('investment.daily_dashboard.verify',side_effect=FileNotFoundError('private local path')):
            model=daily_model(self.snapshot,self.receipt,self.context)
        self.assertIsNone(model['analysis'])
        self.assertEqual(model['error'],'FileNotFoundError')
        self.assertTrue(model['market'])
        self.assertNotIn('private local path',json.dumps(model))

    def test_news_connection_unknown_does_not_report_zero(self):
        self.context.update(pending=None,error='OSError')
        model=daily_model(self.snapshot,self.receipt,self.context)
        self.assertIsNone(model['market'][0]['주요이벤트'])
        self.assertTrue(any('읽지 못했습니다' in s for s in model['issues']))

    def test_initial_input_and_policy_are_safe_script_data(self):
        holdings=holdings_input(self.snapshot)
        holdings['research'][0]['review']['invalidation']='</script><script>injected=true</script>'
        html=linked_dashboard('<script>start()</script>',self.snapshot,
                              initial_input=holdings,policy={'maxCompanies':3})
        self.assertNotIn('</script><script>injected',html)
        self.assertIn('INVESTMENT_INITIAL_HOLDINGS',html)
        self.assertIn('INVESTMENT_INITIAL_POLICY',html)

    def test_ui_empty_holdings_and_mode_isolation(self):
        source=f'''
from investment.daily_dashboard import render_daily
snapshot={self.snapshot!r}
context={self.context!r}
render_daily(snapshot,{self.receipt!r},context)
'''
        at=AppTest.from_string(source,default_timeout=20).run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(next(m.value for m in at.metric if m.label=='보유 검토 대기'),'미입력')
        self.assertTrue(any('보유 입력 대기' in i.value for i in at.info))
        holdings=holdings_input(self.snapshot)
        holdings['holdings']=[dict(code=self.snapshot['companies'][0]['code'],quantity=1,avg_cost_krw=None)]
        at.session_state['daily_holdings_user_input']=holdings
        at.run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(next(m.value for m in at.metric if m.label=='보유 검토 대기'),'1 / 1')
        next(b for b in at.button if b.label=='일일 요약 입력 비우기').click().run()
        self.assertIsNone(at.session_state['daily_holdings_user_input'])
        fixture=copy.deepcopy(self.snapshot);fixture['meta']['data_mode']='fixture'
        with patch('investment.daily_dashboard.verify') as engine:
            at=AppTest.from_string(source.replace(repr(self.snapshot),repr(fixture)),default_timeout=20).run()
        engine.assert_not_called()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(len(at.metric),0)
        self.assertTrue(any('가상 테스트 모드' in i.value for i in at.info))


if __name__=='__main__':
    unittest.main()
