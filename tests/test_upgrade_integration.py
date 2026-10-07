"""Final cross-module user contracts, using only synthetic input and local temp files."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from investment.fixture import make_fixture
from investment.workspace_export import export_workspace
from investment.trend_following import build_trend_following
from investment.workspace_research import build_research
from investment.portfolio_risk import compare_portfolios,validate_policy
from investment.recommendation_allocation import RECOMMENDATION_POLICY
from investment.workspace_export import share_live_text
from investment.workspace_export import market_summary
from tests.test_portfolio_risk import risk_fixture
from tests.test_market_trend_changes import board


def payload(html):
    return json.JSONDecoder().raw_decode(html.split('const WORKSPACE_DATA=',1)[1])[0]


class UpgradeIntegrationTests(unittest.TestCase):
    def test_wire_sharing_cannot_change_cached_benchmark_sources_or_supplied_trend(self):
        _,cache,cutoff=risk_fixture();note='원문 출처와 확인한 자료 범위를 보존합니다. '*10
        for r in cache['history']['benchmarks'].values():r['source']['description']=note
        original=json.loads(json.dumps(cache));summary=market_summary(make_fixture(),cache,cutoff)
        share_live_text({'market_summary':summary})
        self.assertEqual(cache,original)
        trend=board();before=json.loads(json.dumps(trend))
        export_workspace(make_fixture(),live={'token':'synthetic','lazy_company_views':True},trend_following_data=trend)
        self.assertEqual(trend,before)
    def test_current_limit_review_has_a_separate_date_from_historical_decision(self):
        previous=dict(created_on='2026-10-01',targets=[],cash_pct=100)
        before=json.loads(json.dumps(previous))
        result=compare_portfolios(previous,None,None,'2026-10-06',RECOMMENDATION_POLICY,policy_as_of='2026-10-07')
        self.assertEqual(result['policy_status'],'within_limits')
        self.assertEqual(result['policy_assessed_on'],'2026-10-07')
        self.assertEqual(previous,before)
        self.assertEqual(validate_policy(RECOMMENDATION_POLICY,None)['status'],'pending')

    def test_repeated_descriptions_are_shared_but_input_namespaces_are_preserved(self):
        note='검증한 원문 설명과 공개일 미확인 상태를 그대로 보존합니다. '*8
        data={'rows':[{'source':note},{'source':note}], 'wire_format':'live-v2'}
        share_live_text(data)
        self.assertIn(note,data['wire_text'])
        encoded=json.dumps(data,ensure_ascii=False)
        self.assertLess(len(encoded.encode()),len(json.dumps({'rows':[{'source':note},{'source':note}],'wire_format':'live-v2'},ensure_ascii=False).encode()))
        reserved={'rows':[{'__investment_wire_text__':0}],'notes':[note,note]}
        original=json.loads(json.dumps(reserved));share_live_text(reserved)
        self.assertEqual(reserved,original)

    def test_unverified_price_cutoff_shows_pending_without_creating_history(self):
        snapshot=make_fixture();snapshot['meta']['price_date']=None
        trend=build_trend_following(snapshot,{'rows':{}})
        self.assertEqual(trend['changes']['status'],'pending')
        self.assertEqual(trend['changes']['new_qualified'],[])
        self.assertTrue(all(m['status']=='pending' for m in trend['markets']))

    def test_observation_is_opt_in_and_reloads_preserve_prior_decision(self):
        with TemporaryDirectory() as directory:
            data=board()
            no_write=payload(export_workspace(make_fixture(),trend_following_data=data))
            self.assertEqual(list(Path(directory).rglob('*.json')),[])
            first=payload(export_workspace(make_fixture(),trend_following_data=data,trend_checkpoint_directory=directory))
            self.assertEqual(first['trend_following']['changes']['status'],'no_prior')
            self.assertEqual(first['trend_following']['changes']['new_qualified'],[])
            data['rows'][0]['rs']=70
            second=payload(export_workspace(make_fixture(),trend_following_data=data,trend_checkpoint_directory=directory))
            self.assertEqual(second['trend_following']['changes']['new_qualified'][0]['code'],'A')
            third=payload(export_workspace(make_fixture(),trend_following_data=data,trend_checkpoint_directory=directory))
            self.assertEqual(second['trend_following']['changes'],third['trend_following']['changes'])
            self.assertEqual(len(list(Path(directory).rglob('*.json'))),2)

    def test_static_company_models_carry_validated_completeness_and_all_modules(self):
        html=export_workspace(make_fixture())
        data=payload(html)
        for model in data['company_details'].values():
            self.assertIn('financial_completeness',model)
            self.assertIn('native_financial',model)
            self.assertIn('latest_stored',model['financial_completeness'])
        for name in ['MarketExplanationUI','TrendChangesUI','RiskReviewUI','FinancialCompletenessUI']:
            self.assertIn('const '+name,html)
        self.assertEqual(data['market_contract']['same_day_after'],'20:30')
        self.assertFalse(any(marker in html for marker in ['/*MARKET_EXPLANATION','/*RISK_REVIEW','/*FINANCIAL_COMPLETENESS']))


if __name__=='__main__':unittest.main()
