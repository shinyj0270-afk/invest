"""Thesis v2.1: Lynch type + adopted master guidelines (1-4, 6-11) with type-adjusted thresholds, stored data only."""
import copy
import json
import unittest
from pathlib import Path

from investment.thesis_monitor import (ADOPTED, METRICS, REFERENCE_ONLY, THRESHOLDS, TYPES, TRIGGERED, CLEAR, INSUFFICIENT,
                                       evaluate, observe, threshold, validate_thesis)

ROOT = Path(__file__).resolve().parents[1]
ENDS = ['2025-03-31', '2025-06-30', '2025-09-30', '2025-12-31', '2026-03-31', '2026-06-30']


def column(end, revenue, op, net, gross):
    return dict(period_end=end, statement_values=dict(revenue=revenue, operating_profit=op, net_income=net, gross_profit=gross))


def table(rev=(100, 110, 120, 130, 150, 165), op=(10, 11, 12, 13, 18, 22), net=(8, 9, 10, 11, 15, 18),
          gross=(30, 33, 36, 39, 48, 56), basis='CFS', annual=None):
    groups = [dict(basis=basis, cadence='quarter', columns=[column(e, *v) for e, *v in zip(ENDS, rev, op, net, gross)])]
    if annual:
        groups.append(dict(basis=basis, cadence='annual', columns=[
            dict(period_end=f'{y}-12-31', statement_values=dict(operating_profit=v)) for y, v in annual]))
    return dict(groups=groups)


WEAK = dict(rev=(100, 110, 120, 130, 95, 100), op=(10, 11, 12, 13, 8, 6), net=(8, 9, 10, 11, 6, 5), gross=(30, 33, 36, 39, 28, 25))
FLAT5 = dict(rev=(100, 100, 100, 100, 102, 105), op=(10, 10, 10, 10, 10.2, 10.5), net=(8,) * 6, gross=(30, 30, 30, 30, 30.6, 31.5))
TECH = dict(as_of='2026-10-07', close=100.0)
MA_IDS = ('price_long', 'long_stack', 'long_rising', 'short_stack', 'price50')


def trend(fail=(), unknown=(), phase='추세·횡보 관찰', rs=82.0, blocked=False):
    def status(i):
        return 'fail' if i in fail else 'unknown' if i in unknown else 'pass'
    ids = MA_IDS + ('above_low', 'near_high', 'rs')
    checks = [dict(id=i, status=status(i), value=rs if i == 'rs' else 1.0) for i in ids]
    return dict(ready=True, rs=rs, analysis=dict(checks=checks, phase=phase, blocked=blocked, volume_multiple=1.2, contraction=False))


def entry(kind='fast', conditions=None, scenarios=None):
    conditions = conditions or [
        dict(id='ma', kind='auto', metric='trend_template_failed'),
        dict(id='rev', kind='auto', metric='revenue_yoy_pct'),
        dict(id='op', kind='auto', metric='op_profit_yoy_pct'),
        dict(id='mkt', kind='auto', metric='market_uptrend'),
        dict(id='cust', kind='manual', label='핵심 고객 이탈')]
    scenarios = scenarios or [dict(title='성장 둔화', description='d', conditions=['rev', 'op']),
                              dict(title='추세 훼손', description='d', conditions=['ma']),
                              dict(title='고객 이탈', description='d', conditions=['cust', 'rev'])]
    return dict(type=kind, scenarios=scenarios, invalidation=conditions, status='draft', drafted_by='Claude 초안')


def statuses(result):
    return {c['id']: c['status'] for c in result['conditions']}


class ObservationTests(unittest.TestCase):
    def test_earnings_growth_acceleration_and_margins(self):
        m = observe(table(), TECH)['metrics']
        self.assertAlmostEqual(m['revenue_yoy_pct'], 50.0)
        self.assertAlmostEqual(m['op_profit_yoy_pct'], 100.0)
        self.assertAlmostEqual(m['net_income_yoy_pct'], 100.0)
        self.assertAlmostEqual(m['op_profit_accel_pp'], 20.0, msg='latest YoY 100% vs previous quarter YoY 80%')
        self.assertAlmostEqual(m['operating_margin_change_pp'], 22 / 165 * 100 - 10, places=6)
        self.assertAlmostEqual(m['gross_margin_change_pp'], 56 / 165 * 100 - 30, places=6)
        self.assertAlmostEqual(m['operating_margin_drop_from_peak_pp'], 0.0, msg='latest quarter is the peak')

    def test_declining_company(self):
        m = observe(table(**WEAK), TECH)['metrics']
        self.assertAlmostEqual(m['revenue_yoy_pct'], 100 / 110 * 100 - 100, places=6)
        self.assertAlmostEqual(m['op_profit_accel_pp'], (6 / 11 - 1) * 100 - (8 / 10 - 1) * 100, places=6)
        self.assertAlmostEqual(m['operating_margin_change_pp'], -4.0)
        self.assertAlmostEqual(m['gross_margin_change_pp'], -5.0)
        self.assertAlmostEqual(m['operating_margin_drop_from_peak_pp'], -4.0)

    def test_growth_needs_positive_base_and_year_ago_quarter(self):
        loss = table(op=(-10, -5, 12, 13, 18, 22))
        m = observe(loss, TECH)['metrics']
        self.assertIsNone(m['op_profit_yoy_pct'], 'year-ago operating loss gives no growth rate')
        self.assertIsNone(m['op_profit_accel_pp'])
        short = table()
        short['groups'][0]['columns'] = short['groups'][0]['columns'][-2:]
        m = observe(short, TECH)['metrics']
        self.assertIsNone(m['revenue_yoy_pct'])
        self.assertIsNone(m['operating_margin_drop_from_peak_pp'], 'peak needs at least four quarters')

    def test_annual_three_year_growth_requires_four_annual_columns(self):
        years = [(2022, 100), (2023, 120), (2024, 150), (2025, 200)]
        self.assertAlmostEqual(observe(table(annual=years), TECH)['metrics']['annual_op_profit_cagr_3y_pct'], (2 ** (1 / 3) - 1) * 100, places=6)
        self.assertIsNone(observe(table(annual=years[-1:]), TECH)['metrics']['annual_op_profit_cagr_3y_pct'])
        self.assertIsNone(observe(table(annual=[(2022, -5)] + years[1:]), TECH)['metrics']['annual_op_profit_cagr_3y_pct'])
        self.assertIsNone(observe(table(), TECH)['metrics']['annual_op_profit_cagr_3y_pct'])

    def test_trend_guidelines_from_stored_diagnostics(self):
        m = observe(table(), TECH, trend(fail=('price50', 'long_rising', 'near_high'), rs=64.0), '상승 정렬')['metrics']
        self.assertEqual(m['trend_template_failed'], 2)
        self.assertEqual(m['range_failed'], 1)
        self.assertEqual(m['rs_score'], 64.0)
        self.assertIs(m['market_uptrend'], True)
        self.assertIs(m['breakout_failed'], False)
        self.assertIs(observe(table(), TECH, trend(phase='돌파 후 되밀림'), '하락 정렬')['metrics']['breakout_failed'], True)
        self.assertIs(observe(table(), TECH, trend(), '혼조 · 전환 관찰')['metrics']['market_uptrend'], False)

    def test_unknown_or_blocked_trend_is_not_counted_as_clear(self):
        m = observe(table(), TECH, trend(unknown=('price50',)), '자료 대기')['metrics']
        self.assertIsNone(m['trend_template_failed'])
        self.assertIsNone(m['market_uptrend'])
        blocked = observe(table(), TECH, trend(blocked=True, phase='거래 없음 · 판정 보류'))['metrics']
        self.assertIsNone(blocked['breakout_failed'])
        none = observe(None, {}, None, None)['metrics']
        self.assertTrue(all(v is None for v in none.values()))

    def test_separate_basis_used_only_when_consolidated_absent(self):
        self.assertEqual(observe(table(basis='OFS'), TECH)['basis'], 'OFS')


class ThresholdTests(unittest.TestCase):
    def test_type_adjusted_values(self):
        self.assertEqual(threshold('op_profit_yoy_pct', 'fast'), ('<', 25))
        self.assertEqual(threshold('op_profit_yoy_pct', 'stalwart'), ('<', 10))
        self.assertEqual(threshold('op_profit_yoy_pct', 'cyclical'), ('<', 0))
        self.assertEqual(threshold('revenue_yoy_pct', 'fast'), ('<', 20))
        self.assertEqual(threshold('op_profit_accel_pp', 'fast'), ('<', 0))
        self.assertIsNone(threshold('op_profit_accel_pp', 'cyclical'), 'acceleration is a growth-stock rule only')
        self.assertEqual(threshold('market_uptrend', 'cyclical'), ('==', False))
        self.assertIsNone(threshold('revenue_yoy_pct', 'slow'), 'types without defined criteria have no thresholds yet')

    def test_config_matches_metric_registry(self):
        self.assertEqual(set(THRESHOLDS), set(METRICS) - REFERENCE_ONLY)
        for key, spec in THRESHOLDS.items():
            self.assertIn(spec['op'], ('<', '<=', '>', '>=', '=='), key)
            self.assertIn(METRICS[key][1], ADOPTED, key)
            self.assertTrue(set(spec['values']) - {'*'} <= set(TYPES), key)
        self.assertEqual(sorted(ADOPTED), [1, 2, 3, 4, 6, 7, 8, 9, 10, 11])


class EvaluationTests(unittest.TestCase):
    def test_same_numbers_trigger_differently_by_type(self):
        flat = table(**FLAT5)
        fast = statuses(evaluate(entry('fast'), flat, TECH, trend(), '상승 정렬'))
        cyc = statuses(evaluate(entry('cyclical'), flat, TECH, trend(), '상승 정렬'))
        self.assertEqual((fast['rev'], fast['op']), (TRIGGERED, TRIGGERED), 'growth stock below 20% / 25%')
        self.assertEqual((cyc['rev'], cyc['op']), (CLEAR, CLEAR), 'cyclicals only need non-negative growth')

    def test_stalwart_profit_floor_ten_percent(self):
        s = statuses(evaluate(entry('stalwart'), table(**FLAT5), TECH, trend(), '상승 정렬'))
        self.assertEqual(s['rev'], CLEAR)
        self.assertEqual(s['op'], TRIGGERED, 'operating profit +5% is below the stalwart 10% floor')

    def test_weak_company_rolls_up_without_changing_opinion(self):
        e = entry('fast')
        before = copy.deepcopy(e)
        r = evaluate(e, table(**WEAK), TECH, trend(fail=('price50', 'short_stack')), '상승 정렬')
        s = statuses(r)
        self.assertEqual((s['ma'], s['rev'], s['op'], s['cust']), (TRIGGERED, TRIGGERED, TRIGGERED, 'manual'))
        self.assertEqual(r['action'], '재검토 권고')
        self.assertEqual([x['status'] for x in r['scenarios']], ['warning', 'warning', 'warning'])
        self.assertEqual(r['type'], 'fast')
        self.assertEqual(r['type_label'], '고성장')
        self.assertIn('판단을 자동으로 바꾸지 않습니다', r['note'])
        self.assertEqual(e, before)
        json.dumps(r, allow_nan=False)

    def test_labels_carry_guideline_number_and_resolved_threshold(self):
        r = evaluate(entry('fast'), table(), TECH, trend(), '상승 정렬')
        by_id = {c['id']: c for c in r['conditions']}
        self.assertEqual(by_id['op']['guideline'], 7)
        self.assertIn('25%', by_id['op']['text'])
        self.assertEqual(by_id['rev']['guideline'], 10)
        self.assertIn('20%', by_id['rev']['text'])
        self.assertIsNone(by_id['cust']['guideline'])

    def test_healthy_growth_stock_is_clear(self):
        r = evaluate(entry('fast'), table(), TECH, trend(), '상승 정렬')
        self.assertEqual({k: v for k, v in statuses(r).items() if k != 'cust'}, dict(ma=CLEAR, rev=CLEAR, op=CLEAR, mkt=CLEAR))
        self.assertEqual(r['action'], '유지 점검')

    def test_market_context_is_reported_but_never_drives_the_action(self):
        r = evaluate(entry('fast'), table(), TECH, trend(), '혼조 · 전환 관찰')
        mkt = next(c for c in r['conditions'] if c['id'] == 'mkt')
        self.assertEqual((mkt['status'], mkt['role']), (TRIGGERED, 'context'))
        self.assertEqual(r['action'], '유지 점검')

    def test_missing_data_is_insufficient_not_clear(self):
        r = evaluate(entry('fast'), None, {}, None, None)
        self.assertTrue(all(c['status'] in (INSUFFICIENT, 'manual') for c in r['conditions']))
        self.assertEqual(r['action'], '자료 부족')


class ValidationTests(unittest.TestCase):
    def test_valid_entry(self):
        validate_thesis(entry('fast'))
        validate_thesis(entry('cyclical'))

    def test_rejects_bad_structures(self):
        e = entry()
        bad = [
            dict(e, type='unknown'),
            {k: v for k, v in e.items() if k != 'type'},
            dict(e, type='slow'),
            dict(e, scenarios=e['scenarios'][:2]),
            dict(e, invalidation=[dict(id='x', kind='auto', metric='ocf_to_profit_ttm')] + e['invalidation']),
            dict(e, scenarios=[dict(e['scenarios'][0], conditions=['mkt'])] + e['scenarios'][1:]),
            dict(e, scenarios=[dict(e['scenarios'][0], conditions=['nope'])] + e['scenarios'][1:]),
            dict(entry('cyclical'), invalidation=entry()['invalidation'] + [dict(id='acc', kind='auto', metric='op_profit_accel_pp')]),
        ]
        for broken in bad:
            with self.assertRaises(ValueError):
                validate_thesis(broken)


class ProjectFileTests(unittest.TestCase):
    def test_project_theses_are_valid_typed_drafts(self):
        data = json.loads((ROOT / 'config/business_theses.json').read_text(encoding='utf-8'))
        self.assertEqual(data['schema'], 2)
        self.assertEqual(len(data['companies']), 5)
        for code, e in data['companies'].items():
            for key in ('fact', 'thesis', 'counter', 'keep', 'sources', 'type'):
                self.assertIn(key, e, code)
            validate_thesis(e)
            self.assertEqual(e['status'], 'draft', 'AI drafts stay unconfirmed until the user reviews them')
            used = {c['metric'] for c in e['invalidation'] if c['kind'] == 'auto'}
            self.assertTrue(used <= set(METRICS), code)
            self.assertTrue(any(c['kind'] == 'manual' for c in e['invalidation']), 'business-specific conditions stay manual')


if __name__ == '__main__':
    unittest.main()
