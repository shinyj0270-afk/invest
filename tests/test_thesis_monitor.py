"""Thesis v2: three failure scenarios and invalidation conditions checked against stored data only."""
import copy
import json
import unittest
from pathlib import Path

from investment.thesis_monitor import observe, evaluate, validate_thesis, TRIGGERED, CLEAR, INSUFFICIENT

ROOT = Path(__file__).resolve().parents[1]


def column(end, revenue, op, net, ocf):
    return dict(period_end=end, statement_values=dict(revenue=revenue, operating_profit=op, net_income=net, ocf=ocf, liabilities=60.0, equity=100.0))


ENDS = ['2025-03-31', '2025-06-30', '2025-09-30', '2025-12-31', '2026-03-31', '2026-06-30']


def table(revenues=(100, 110, 120, 130, 95, 100), margins=(10, 10, 10, 10, 8, 6), ocf=(5, 5, 5, 5, -3, -2), basis='CFS'):
    cols = [column(e, r, r * m / 100, r * m / 100 * .8, o) for e, r, m, o in zip(ENDS, revenues, margins, ocf)]
    return dict(groups=[dict(basis=basis, cadence='quarter', columns=cols)])


TECH = dict(as_of='2026-10-07', close=90.0, sma={'200': 100.0}, short_rs={'1m': dict(score=35.0)}, price_trend_status='fail')


def thesis(conditions=None):
    conditions = conditions or [
        dict(id='rev', label='매출 YoY 2분기 연속 감소', kind='auto', metric='revenue_yoy_negative_streak', op='>=', value=2),
        dict(id='margin', label='영업이익률 전년 대비 3%p 이상 하락', kind='auto', metric='operating_margin_change_pp', op='<=', value=-3),
        dict(id='ocf', label='TTM 영업현금흐름이 순이익의 50% 미만', kind='auto', metric='ocf_to_profit_ttm', op='<', value=0.5),
        dict(id='ma', label='200일선 아래', kind='auto', metric='below_ma200', op='==', value=True),
        dict(id='client', label='핵심 고객 이탈', kind='manual')]
    return dict(scenarios=[dict(title='수요 둔화', description='d', conditions=['rev', 'margin']),
                           dict(title='현금 악화', description='d', conditions=['ocf']),
                           dict(title='고객 이탈', description='d', conditions=['client', 'ma'])],
                invalidation=conditions, status='draft', drafted_by='Claude 초안')


class ThesisMonitorTests(unittest.TestCase):
    def test_observations_from_stored_quarters_and_price(self):
        o = observe(table(), TECH)
        self.assertEqual(o['period'], '2026-06-30')
        self.assertAlmostEqual(o['metrics']['revenue_yoy_pct'], 0.0 - 9.0909, places=3)
        self.assertEqual(o['metrics']['revenue_yoy_negative_streak'], 2)
        self.assertAlmostEqual(o['metrics']['operating_margin_change_pp'], -4.0)
        self.assertEqual(o['metrics']['ocf_ttm'], 5)  # last four quarters: 5,5,-3,-2
        self.assertTrue(o['metrics']['below_ma200'])
        self.assertAlmostEqual(o['metrics']['ocf_to_profit_ttm'], 5 / 30.88, places=4)
        self.assertEqual(o['metrics']['rs_1m'], 35.0)
        self.assertEqual(o['price_date'], '2026-10-07')

    def test_conditions_trigger_and_scenarios_roll_up_without_changing_opinion(self):
        t = thesis()
        before = copy.deepcopy(t)
        r = evaluate(t, table(), TECH)
        status = {c['id']: c['status'] for c in r['conditions']}
        self.assertEqual(status, dict(rev=TRIGGERED, margin=TRIGGERED, ocf=TRIGGERED, ma=TRIGGERED, client='manual'))
        self.assertEqual([s['status'] for s in r['scenarios']], ['warning', 'warning', 'warning'])
        self.assertEqual(r['action'], '재검토 권고')
        self.assertIn('판단을 자동으로 바꾸지 않습니다', r['note'])
        self.assertEqual(t, before)
        json.dumps(r, allow_nan=False)

    def test_healthy_company_is_clear(self):
        healthy = table(revenues=(100, 100, 100, 100, 120, 125), margins=(10,) * 6, ocf=(5,) * 6)
        tech = dict(TECH, close=120.0, short_rs={'1m': dict(score=80.0)})
        r = evaluate(thesis(), healthy, tech)
        self.assertTrue(all(c['status'] in (CLEAR, 'manual') for c in r['conditions']))
        self.assertEqual(r['action'], '유지 점검')
        self.assertEqual(r['scenarios'][1]['status'], 'watch')

    def test_missing_data_is_insufficient_not_clear(self):
        r = evaluate(thesis(), None, {})
        self.assertTrue(all(c['status'] in (INSUFFICIENT, 'manual') for c in r['conditions']))
        self.assertEqual(r['action'], '자료 부족')
        short = table(revenues=(100, 110, 120, 130, 95, 100))
        short['groups'][0]['columns'] = short['groups'][0]['columns'][-2:]
        self.assertEqual(observe(short, TECH)['metrics']['revenue_yoy_pct'], None, 'no year-ago quarter, no growth')

    def test_separate_basis_used_only_when_consolidated_absent(self):
        self.assertEqual(observe(table(basis='OFS'), TECH)['basis'], 'OFS')

    def test_schema_validation(self):
        validate_thesis(thesis())
        for broken in (dict(thesis(), scenarios=thesis()['scenarios'][:2]),
                       dict(thesis(), invalidation=[dict(id='x', label='?', kind='auto', metric='unknown', op='<', value=0)]),
                       dict(thesis(), invalidation=thesis()['invalidation'][:-1])):
            with self.assertRaises(ValueError):
                validate_thesis(broken)

    def test_project_theses_file_is_valid_v2(self):
        data = json.loads((ROOT / 'config/business_theses.json').read_text(encoding='utf-8'))
        self.assertEqual(data['schema'], 2)
        for code, entry in data['companies'].items():
            for key in ('fact', 'thesis', 'counter', 'keep', 'sources'):
                self.assertIn(key, entry, code)
            validate_thesis(entry)
            self.assertEqual(entry['status'], 'draft', 'AI drafts stay unconfirmed until the user reviews them')


if __name__ == '__main__':
    unittest.main()
