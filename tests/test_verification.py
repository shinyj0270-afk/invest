"""Common verification engine: pass / conditional / review, separating calculation errors from missing data."""
import copy
import json
import unittest

from investment.verification import verify_company, overclaim, opinion_change, review_report, report_markdown, compact, PASS, CONDITIONAL, REVIEW


def row(**over):
    common = dict(basis='CFS', period='2026-06-30', currency='KRW', ttm_complete=True,
                  amounts=dict(revenue=1000.0, operating_profit=100.0, net_income=80.0),
                  metrics=dict(operating_margin_pct=10.0, revenue_growth_pct=5.0, roe_pct=12.0, debt_ratio_pct=50.0, per=11.0, pbr=1.2),
                  metric_details=dict(operating_margin_pct=dict(status='calculated', source='DART', observed_on='2026-08-14'),
                                      roe_pct=dict(status='calculated', source='DART', observed_on='2026-08-14')),
                  source_urls=['https://dart.fss.or.kr/x'])
    r = dict(code='000001', name='가상', market='KOSPI', common_financial=common,
             financial_completeness=dict(latest_stored=dict(status='ready'), required_accounts=dict(status='ready', missing=[]),
                                         ttm=dict(status='ready'), roe=dict(status='ready')))
    for k, v in over.items():
        r[k] = v
    return r


TECH = dict(as_of='2026-10-07', close=100.0)
AS_OF = '2026-10-08'


def ids(result, status):
    return [c['id'] for c in result['checks'] if c['status'] == status]


class VerificationTests(unittest.TestCase):
    def test_complete_consolidated_record_passes(self):
        r = row()
        before = copy.deepcopy(r)
        result = verify_company(r, TECH, AS_OF)
        self.assertEqual(result['status'], PASS)
        self.assertEqual(result['label'], '통과')
        self.assertEqual(result['cause'], None)
        self.assertEqual(r, before, 'verification never changes source values')
        json.dumps(result, allow_nan=False)

    def test_recompute_mismatch_is_calculation_error(self):
        r = row()
        r['common_financial']['metrics']['operating_margin_pct'] = 12.0
        result = verify_company(r, TECH, AS_OF)
        self.assertEqual(result['status'], REVIEW)
        self.assertEqual(result['cause'], 'error')
        self.assertIn('recompute', ids(result, REVIEW))
        self.assertEqual(result['label'], '재검토 필요 · 계산 오류')

    def test_rounding_within_tolerance_still_passes(self):
        r = row()
        r['common_financial']['metrics']['operating_margin_pct'] = 10.04
        self.assertEqual(verify_company(r, TECH, AS_OF)['status'], PASS)

    def test_missing_period_or_price_is_missing_data_not_error(self):
        r = row(common_financial=None)
        result = verify_company(r, TECH, AS_OF)
        self.assertEqual(result['status'], REVIEW)
        self.assertEqual(result['cause'], 'missing')
        self.assertEqual(result['label'], '재검토 필요 · 자료 부족')
        self.assertEqual(verify_company(row(), {}, AS_OF)['cause'], 'missing')

    def test_future_dates_are_errors(self):
        r = row()
        r['common_financial']['metric_details']['roe_pct']['observed_on'] = '2026-12-01'
        self.assertEqual(verify_company(r, TECH, AS_OF)['cause'], 'error')
        self.assertEqual(verify_company(row(), dict(TECH, as_of='2026-10-09'), AS_OF)['cause'], 'error')

    def test_separate_basis_currency_and_approximation_are_conditional(self):
        for change in (dict(basis='OFS'), dict(currency='USD')):
            r = row()
            r['common_financial'].update(change)
            result = verify_company(r, TECH, AS_OF)
            self.assertEqual(result['status'], CONDITIONAL, change)
            self.assertEqual(result['label'], '조건부 통과')
        r = row()
        r['common_financial']['metric_details']['roe_pct']['status'] = 'reference_with_tolerance'
        self.assertIn('approximation', ids(verify_company(r, TECH, AS_OF), CONDITIONAL))

    def test_partial_accounts_are_conditional_missing(self):
        r = row()
        r['financial_completeness']['ttm'] = dict(status='pending')
        r['common_financial']['ttm_complete'] = False
        result = verify_company(r, TECH, AS_OF)
        self.assertEqual(result['status'], CONDITIONAL)
        self.assertIn('completeness', ids(result, CONDITIONAL))

    def test_uncomputed_key_metrics_are_conditional_missing(self):
        r = row()
        r['common_financial']['metrics'].update(per=None, pbr=None)
        result = verify_company(r, TECH, AS_OF)
        self.assertEqual(result['status'], CONDITIONAL)
        check = next(c for c in result['checks'] if c['id'] == 'completeness')
        self.assertIn('PER', check['detail']); self.assertIn('PBR', check['detail'])

    def test_overclaim_flags_positive_conclusion_on_weak_evidence(self):
        weak = verify_company(row(common_financial=None), TECH, AS_OF)
        self.assertTrue(overclaim('HOLD', weak)['flag'])
        self.assertTrue(overclaim('편입', weak)['flag'])
        self.assertFalse(overclaim('REVIEW', weak)['flag'], 'cautious conclusions are not over-claims')
        self.assertFalse(overclaim('HOLD', verify_company(row(), TECH, AS_OF))['flag'])

    def test_opinion_change_records_difference(self):
        self.assertEqual(opinion_change(None, dict(opinion='HOLD', on='2026-10-08'))['kind'], 'first')
        same = opinion_change(dict(opinion='HOLD', on='2026-10-07'), dict(opinion='HOLD', on='2026-10-08'))
        self.assertEqual(same['kind'], 'unchanged')
        moved = opinion_change(dict(opinion='HOLD', on='2026-10-07'), dict(opinion='REVIEW', on='2026-10-08', reasons=['조건 충족']))
        self.assertEqual((moved['kind'], moved['before'], moved['after']), ('changed', 'HOLD', 'REVIEW'))
        self.assertEqual(moved['reasons'], ['조건 충족'])

    def test_review_report_lists_inputs_basis_and_unconfirmed_items(self):
        r = row(common_financial=None)
        report = review_report([dict(row=r, technical=TECH, opinion='HOLD', previous=dict(opinion='HOLD', on='2026-10-07'))], AS_OF, mode='user_input')
        self.assertEqual(report['schema'], 'investment-review-report-1')
        self.assertEqual(report['as_of'], AS_OF)
        item = report['items'][0]
        for key in ('code', 'name', 'data_used', 'calculations', 'previous', 'current', 'verification', 'unconfirmed', 'overclaim'):
            self.assertIn(key, item)
        self.assertTrue(item['unconfirmed'])
        self.assertTrue(item['overclaim']['flag'])
        self.assertEqual(report['summary'][REVIEW], 1)
        self.assertIn('원본을 수정하지 않습니다', report['reviewer_note'])
        json.dumps(report, allow_nan=False)
        md = report_markdown(report)
        self.assertIn('재검토 필요 · 자료 부족', md)
        self.assertIn('기존 판단: HOLD', md)
        self.assertIn('과도한 결론: 예', md)

    def test_compact_keeps_only_non_passing_checks(self):
        ok = compact(verify_company(row(), TECH, AS_OF))
        self.assertEqual((ok['status'], ok['issues']), (PASS, []))
        r = row(); r['common_financial']['basis'] = 'OFS'
        c = compact(verify_company(r, TECH, AS_OF))
        self.assertEqual(c['issues'], [['basis', '연결·별도 구분', '별도 기준 · 연결 미확보', CONDITIONAL]])


if __name__ == '__main__':
    unittest.main()
