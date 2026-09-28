import copy
import unittest

from investment.fixture import make_fixture
from tools.returns_history import build


class ReturnsHistoryTests(unittest.TestCase):
    def setUp(self):
        self.base = make_fixture()
        self.base['meta'].update(data_mode='user_input', as_of='2026-09-28')
        row = self.base['companies'][0]
        self.base['companies'] = [row]
        row['observed_financial_history'] = dict(observed_on='2026-09-28',
            annual=[dict(period_end='2025-12-31', op=10_000_000_000_000)])
        row['financial_accounts'] = dict(balance={
            '2024-12-31': {'자본':100_000_000_000, '현금및현금성자산':10_000_000_000,
                '차입금':20_000_000_000, '단기차입금(요약재무)':10_000_000_000,
                '장기차입금(요약재무)':10_000_000_000},
            '2025-12-31': {'자본':110_000_000_000, '현금및현금성자산':10_000_000_000,
                '차입금':20_000_000_000, '단기차입금(요약재무)':10_000_000_000,
                '장기차입금(요약재무)':10_000_000_000}})
        self.review = dict(source_priority='infomax_balance_official_cashflow',
            unit='million_krw_except_dps', observed_on='2026-09-28',
            period_end='2025-12-31', companies={row['code']:dict(
                balances={'2024':dict(equity=100_000_000,cash=10_000_000),
                          '2025':dict(equity=110_000_000,cash=10_000_000)},
                pretax_2025=5_000_000, tax_expense_2025=1_000_000,
                cashflow={'2024':dict(ocf=5_000,capex_ppe=1_000,capex_intangible=500),
                          '2025':dict(ocf=6_000,capex_ppe=1_200,capex_intangible=300)},
                dividend={'2024':dict(common_dps_components_won=[100],year_end_status='reported'),
                          '2025':dict(common_dps_components_won=[70,50],year_end_status='proposed')},
                source=dict(url='https://example.invalid/report.pdf',file='report.pdf',sha256='fixture'),
                pages=dict(balance=[1],income=[2],cashflow=[3],dividend=[4]))})
        self.balance_review = dict(companies={row['code']:dict(debt_fields=['차입금'])})

    def test_calculates_descriptive_values_without_changing_existing_metrics(self):
        original = copy.deepcopy(self.base)
        output = build(self.base,self.review,self.balance_review,'review','balance')
        record = output['companies'][0]['observed_returns_history']
        self.assertAlmostEqual(record['roic_proxy_2025_pct'],8_000_000_000_000/115_000_000_000_000*100)
        self.assertEqual(record['annual'][1]['fcf_won'],4_500_000_000)
        self.assertEqual(record['annual'][1]['common_dps_won'],120)
        self.assertAlmostEqual(record['common_dps_growth_1y_pct'],20)
        self.assertEqual(self.base,original)
        for key in ('metrics','prices','annual','quarters'):
            self.assertEqual(output['companies'][0].get(key),original['companies'][0].get(key))

    def test_official_balance_mismatch_rejected(self):
        self.review['companies']['900000']['balances']['2025']['equity'] += 200
        with self.assertRaisesRegex(ValueError,'자본'):
            build(self.base,self.review,self.balance_review,'review','balance')

    def test_debt_split_disagreement_withholds_roic_but_keeps_cashflow(self):
        self.base['companies'][0]['financial_accounts']['balance']['2024-12-31']['단기차입금(요약재무)'] -= 1_000_000
        output = build(self.base,self.review,self.balance_review,'review','balance')
        record = output['companies'][0]['observed_returns_history']
        self.assertIsNone(record['roic_proxy_2025_pct'])
        self.assertIn('차입금',record['roic_missing_reason'])
        self.assertEqual(record['annual'][1]['fcf_won'],4_500_000_000)


if __name__ == '__main__': unittest.main()
