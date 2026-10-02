import json,tempfile,unittest
from pathlib import Path
from investment.financial_health import collection_health
from investment.recommendations import business_review,propose
from tests.test_dashboard_upgrade import recommendation_context

class JourneyTests(unittest.TestCase):
    def test_failure_does_not_hide_last_success_or_clear_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            for suffix,data in [('.json',{'retrieved_on':'2026-10-01'}),('.status.json',{'status':'failed','checked_at':'2026-10-02T12:00:00+09:00'}),('.incomplete.json',{'errors':[1,2]})]:
                (folder/('900000'+suffix)).write_text(json.dumps(data),encoding='utf-8')
            result=collection_health(folder,'900000',{'periods':[1]})
            self.assertEqual(result['status'],'failed');self.assertEqual(result['last_success'],'2026-10-01')
            self.assertEqual(result['failed_periods'],2)
    def test_missing_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=collection_health(Path(tmp),'900000')
            self.assertEqual(result['status'],'missing');self.assertIsNone(result['last_success'])
    def test_business_review_identity_date_and_staleness(self):
        self.assertIsNone(business_review('000660','다른 기업','2026-10-02'))
        self.assertIsNone(business_review('000660','SK하이닉스','2026-10-01'))
        self.assertIsNone(business_review('228850','레이','2026-10-02'))
        rayence=business_review('228850','레이언스','2026-10-02')
        self.assertIn('디텍터',rayence['fact']);self.assertNotIn('RAYFace',rayence['fact'])
        self.assertFalse(business_review('000660','SK하이닉스','2026-10-02')['stale'])
        self.assertTrue(business_review('000660','SK하이닉스','2026-12-02')['stale'])
    def test_cash_only_and_missing_business_evidence_are_reviewable(self):
        context=recommendation_context()
        record=propose(context,created_on='2026-10-02')
        self.assertTrue(record['review_needed'])
        for r in context['snapshot']['companies']:r['common_financial']['metrics']['revenue_growth_pct']=0
        record=propose(context,created_on='2026-10-02')
        self.assertEqual(record['cash_pct'],100);self.assertTrue(record['review_needed'])
        self.assertEqual(sum(record['exclusion_reasons'].values()),7)

if __name__=='__main__':unittest.main()
