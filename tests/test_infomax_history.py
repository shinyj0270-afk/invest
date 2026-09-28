import copy
import unittest
from investment.metrics import additional,current_history
from investment import research
from investment.refresh import merge_daily
from tools.infomax_history import build,FIELDS
from tests import test_infomax_daily


class HistoryTests(unittest.TestCase):
    def setUp(self):
        helper=test_infomax_daily.DailyImportTests(); helper.setUp()
        self.base=helper.convert()
        self.base['meta']['financial_period']='2026-06-30'
        self.accounts={'900001':{}}
        for year in range(2018,2027):
            for suffix in ('03-31','06-30','09-30','12-31'):
                end=f'{year}-{suffix}'
                if '2018-09-30'<=end<='2026-06-30':
                    revenue=100*1.1**(year-2018)
                    self.accounts['900001'][end]={FIELDS['revenue']:revenue,
                        FIELDS['op']:revenue*.2, FIELDS['parent_income']:revenue*.1}
        self.base['companies'][0]['quarters']=[dict(period_end=d,available_at=None,basis='CFS',
            **{k:v[f]*1000 for k,f in FIELDS.items()}) for d,v in list(self.accounts['900001'].items())[-8:]]
        official={k:sum(v[f] for d,v in self.accounts['900001'].items() if d.startswith('2025'))/1000 for k,f in FIELDS.items()}
        self.review=dict(observed_on='2026-09-28',source_priority='infomax',companies={'900001':dict(
            period_end='2025-12-31',official_million_krw=official,
            source=dict(sha256='synthetic',file='synthetic.pdf'),pdf_page=1)})
        self.provenance=dict(file='synthetic.xlsx',sha256='synthetic',unit='천원')

    def build(self):
        return build(self.base,self.accounts,'2026-09-28',self.provenance,self.review)

    def test_annual_aggregation_and_no_vintage_invention(self):
        original=copy.deepcopy(self.base)
        s=self.build(); row=s['companies'][0]; h=row['observed_financial_history']
        self.assertEqual(len(h['quarters']),32)
        self.assertEqual(len(h['annual']),7)
        self.assertEqual(h['incomplete_years_excluded'],['2018','2026'])
        self.assertEqual(h['annual'][0]['period_end'],'2019-12-31')
        self.assertEqual(row['quarters'],original['companies'][0]['quarters'])
        self.assertEqual(row['annual'],original['companies'][0]['annual'])
        self.assertEqual(row['metrics'],original['companies'][0]['metrics'])
        self.assertEqual(self.base,original)
        self.assertTrue(all(q['available_at'] is None for q in h['quarters']))
        self.assertTrue(all(abs(c['difference_won'])<1e-6 for c in h['annual_comparison']))
        self.assertEqual(research.analyze(s)[0]['signals'],research.analyze(original)[0]['signals'])

    def test_current_metrics_require_explicit_opt_in(self):
        s=self.build(); row=s['companies'][0]
        self.assertIsNone(additional(row,s)[0]['revenue_cagr_5y_pct'])
        metrics,_=additional(row,s,include_current_history=True)
        for n in (3,5): self.assertAlmostEqual(metrics[f'revenue_cagr_{n}y_pct'],10)
        expected=sum(q['revenue'] for q in row['observed_financial_history']['quarters'][-4:])/1e8
        self.assertAlmostEqual(metrics['revenue_ttm_eok'],expected)
        self.assertIsNone(metrics['fcf_proxy_eok'])

    def test_future_observation_not_used(self):
        s=self.build(); s['meta']['as_of']='2026-09-23'
        self.assertIsNone(current_history(s['companies'][0],s))
        self.assertIsNone(additional(s['companies'][0],s,True)[0]['revenue_cagr_3y_pct'])

    def test_gap_rejected(self):
        del self.accounts['900001']['2021-06-30']
        with self.assertRaisesRegex(ValueError,'連続|연속'): self.build()

    def test_missing_income_rejected(self):
        self.accounts['900001']['2020-06-30'][FIELDS['revenue']]=None
        with self.assertRaisesRegex(ValueError,'결측'): self.build()

    def test_existing_reviewed_quarter_mismatch_rejected(self):
        self.accounts['900001']['2026-06-30'][FIELDS['revenue']]+=200_000
        with self.assertRaisesRegex(ValueError,'재검토'): self.build()

    def test_unreviewed_latest_period_rejected(self):
        self.base['meta']['financial_period']='2026-03-31'
        with self.assertRaisesRegex(ValueError,'최신 재무기간'): self.build()

    def test_official_discrepancy_retained_with_provider_priority(self):
        self.review['companies']['900001']['official_million_krw']['revenue']+=200
        h=self.build()['companies'][0]['observed_financial_history']
        self.assertFalse(h['annual_comparison'][0]['within_tolerance'])
        self.assertAlmostEqual(h['annual_comparison'][0]['difference_won'],-200_000_000)

    def test_daily_refresh_keeps_history_and_observation_date(self):
        s=self.build()
        refreshed=merge_daily(s,self.base)
        self.assertEqual(refreshed['companies'][0]['observed_financial_history'],s['companies'][0]['observed_financial_history'])
        self.assertEqual(refreshed['meta']['financial_history_observed_on'],'2026-09-28')

    def test_report_labels_and_current_basis(self):
        from investment.report import onepager
        s=self.build(); row=s['companies'][0]
        row['metrics'].update(additional(row,s,True)[0])
        html=onepager(s,row,research.analyze(s)[0])
        self.assertIn('매출 3년 CAGR · %',html)
        self.assertNotIn('revenue_cagr_',html)
        self.assertIn('조회 2026-09-28',html)
        self.assertIn('과거 시점 판정 미사용',html)


if __name__=='__main__': unittest.main()
