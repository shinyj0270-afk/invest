import copy
import unittest
from datetime import date, timedelta
from investment.pit_annual import project
from investment.pit_verify import verify


def sessions():
    out = [];d = date(2020, 1, 2)
    while d < date(2028, 12, 30):
        if d.weekday() < 5:out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def receipt(no='20260310000001', rcept='2026-03-10', year=2025, revenue=100.0, company='298040'):
    return dict(company=company, period_end=f'{year}-12-31', basis='CFS', report_kind='annual', rcept_no=no, rcept_dt=rcept, values=dict(revenue=revenue))


def inv(no, rcept, period='2025-12', corr='none', company=None, kind='annual'):
    return dict(rcept_no=no, rcept_dt=rcept, title_period=period, correction=corr, kind=kind, company=company)


def broken(transform):
    def fn(receipts, cal):
        result = project(receipts, cal);return dict(result, rows=transform([dict(r) for r in result['rows']]))
    return fn


class VerifyTests(unittest.TestCase):
    def good(self):
        return [receipt(), receipt(no='20260520000002', rcept='2026-05-20', revenue=101.0), receipt(no='20270310000003', rcept='2027-03-10', year=2026, revenue=120.0)]

    def test_a_correct_projection_passes_every_check_and_reports_counts(self):
        out = verify(self.good(), sessions())
        self.assertTrue(out['ok']);self.assertEqual({k: v['ok'] for k, v in out['checks'].items()},
            {'single_scope': True, 'eligibility_oracle': True, 'correction_replay': True, 'order_independence': True})
        self.assertEqual((out['counts']['rows'], out['counts']['ambiguous'], out['counts']['blocked']), (3, 0, {}))
        self.assertIn('회사 단위 복원', out['notice'])

    def test_projections_that_are_missing_wrong_or_mistimed_are_all_caught_by_the_independent_oracle(self):
        def zero(rows):
            return [dict(r, revenue=0.0) for r in rows]
        def shift(rows):
            return [dict(r, available_at=(date.fromisoformat(r['available_at']) + timedelta(days=1)).isoformat()) for r in rows]
        cases = {'no_rows': broken(lambda rows: []), 'drops_the_correction': broken(lambda rows: [r for r in rows if r.get('rcept_no') != '20260520000002']),
                 'zero_values': broken(zero), 'delayed_one_day': broken(shift),
                 'leaks_the_filing_day': broken(lambda rows: [dict(r, available_at=r['rcept_dt']) for r in rows]),
                 'correction_dated_early': broken(lambda rows: [dict(r, available_at='2026-03-12') if r.get('rcept_no') == '20260520000002' else r for r in rows])}
        for name, fn in cases.items():
            with self.subTest(name=name):
                out = verify(self.good(), sessions(), project_fn=fn)
                self.assertFalse(out['ok']);self.assertFalse(out['checks']['eligibility_oracle']['ok'])

    def test_an_order_dependent_projection_is_caught(self):
        def unstable(receipts, cal):
            result = project(receipts, cal)
            return result if receipts and receipts[0]['rcept_no'] == '20260310000001' else dict(result, rows=result['rows'][::-1])
        self.assertFalse(verify(self.good(), sessions(), project_fn=unstable)['checks']['order_independence']['ok'])

    def test_a_projection_where_a_later_receipt_changes_earlier_cutoffs_is_caught_by_replay(self):
        def retro(receipts, cal):
            result = project(receipts, cal);rows = [dict(r, available_at='2026-03-12') if r.get('rcept_no') == '20260520000002' else dict(r) for r in result['rows']]
            return dict(result, rows=rows)
        self.assertFalse(verify(self.good(), sessions(), project_fn=retro)['checks']['correction_replay']['ok'])

    def test_mixed_companies_are_reported_instead_of_silently_merged(self):
        out = verify([receipt(), receipt(no='20260310000009', company='011170')], sessions())
        self.assertFalse(out['checks']['single_scope']['ok'])

    def test_blocked_and_ambiguous_receipts_are_counted(self):
        two_same_day = [receipt(no='20260520000001', rcept='2026-05-20', revenue=90.0), receipt(no='20260520000002', rcept='2026-05-20', revenue=80.0)]
        bad = receipt(no='20260310000007');bad['report_kind'] = 'quarter'
        out = verify([receipt()] + two_same_day + [bad], sessions())
        self.assertEqual(out['counts']['ambiguous'], 1);self.assertEqual(out['counts']['blocked'], {'ambiguous_same_availability': 2, 'not_annual': 1})
        self.assertTrue(out['checks']['eligibility_oracle']['ok'])                      # the ambiguity marker matches the oracle's expectation

    def test_a_known_correction_that_never_produced_a_row_is_unresolved_with_its_interval(self):
        known = [inv('20260310000001', '2026-03-10'), inv('20260520000002', '2026-05-20', corr='기재정정')]
        out = verify([receipt()], sessions(), inventory=known)
        self.assertEqual([(u['rcept_no'], u['affects_from'], u['affects_until'], u['problem']) for u in out['unresolved']],
            [('20260520000002', '2026-05-21', None, 'receipt_without_usable_row')])
        self.assertFalse(out['ok'])
        resolved = verify([receipt(), receipt(no='20260520000002', rcept='2026-05-20', revenue=90.0)], sessions(), inventory=known)
        self.assertEqual(resolved['unresolved'], []);self.assertTrue(resolved['ok'])

    def test_a_failed_middle_correction_is_not_hidden_by_a_later_success(self):
        known = [inv('20260310000001', '2026-03-10'), inv('20260415000002', '2026-04-15', corr='기재정정'), inv('20260520000003', '2026-05-20', corr='기재정정')]
        out = verify([receipt(), receipt(no='20260520000003', rcept='2026-05-20', revenue=90.0)], sessions(), inventory=known)
        self.assertEqual([(u['rcept_no'], u['affects_from'], u['affects_until']) for u in out['unresolved']], [('20260415000002', '2026-04-16', '2026-05-21')])
        self.assertFalse(out['ok'])

    def test_a_missing_original_is_unresolved_even_though_a_later_correction_exists(self):
        known = [inv('20260310000001', '2026-03-10'), inv('20260520000002', '2026-05-20', corr='기재정정')]
        out = verify([receipt(no='20260520000002', rcept='2026-05-20', revenue=90.0)], sessions(), inventory=known)
        self.assertEqual([(u['rcept_no'], u['affects_until']) for u in out['unresolved']], [('20260310000001', '2026-05-21')])

    def test_an_unknown_period_is_reported_as_unresolved_not_ignored(self):
        out = verify([receipt()], sessions(), inventory=[inv('20260601000009', '2026-06-01', period=None, kind='uncertain')])
        self.assertEqual([(u['rcept_no'], u['problem']) for u in out['unresolved']], [('20260601000009', 'unknown_period')]);self.assertFalse(out['ok'])

    def test_one_companys_missing_receipt_is_not_masked_by_another_companys_receipt_for_the_same_period(self):
        known = [inv('20260310000001', '2026-03-10', company='298040'), inv('20260310000555', '2026-03-10', company='011170')]
        out = verify([receipt()], sessions(), inventory=known)
        self.assertEqual([(u['rcept_no'], u['company']) for u in out['unresolved']], [('20260310000555', '011170')])

    def test_identical_same_day_duplicates_collapse_without_being_reported_unresolved(self):
        known = [inv('20260310000001', '2026-03-10'), inv('20260310000002', '2026-03-10')]
        out = verify([receipt(), receipt(no='20260310000002')], sessions(), inventory=known)
        self.assertEqual(out['unresolved'], []);self.assertTrue(out['ok'])

    def test_receipts_inside_an_ambiguity_group_are_accounted_for_not_reported_as_unresolved(self):
        a = receipt(no='20260520000001', rcept='2026-05-20', revenue=90.0);b = receipt(no='20260520000002', rcept='2026-05-20', revenue=80.0)
        known = [inv('20260310000001', '2026-03-10'), inv('20260520000001', '2026-05-20', corr='기재정정'), inv('20260520000002', '2026-05-20', corr='기재정정')]
        out = verify([receipt(), a, b], sessions(), inventory=known)
        self.assertEqual(out['unresolved'], []);self.assertEqual(out['counts']['ambiguous'], 1)
    def test_a_disagreement_between_the_projection_rule_and_the_independent_availability_is_reported(self):
        from unittest.mock import patch
        import investment.pit_annual as annual
        real = annual._check
        def drifted(r, cal):
            reason, when = real(r, cal);return reason, when and (date.fromisoformat(when) + timedelta(days=3)).isoformat()
        with patch('investment.pit_verify._check', drifted):
            out = verify(self.good(), sessions())
        self.assertIn('availability_computation_disagrees', [p['problem'] for p in out['checks']['eligibility_oracle']['problems']])

    def test_a_later_receipt_of_another_company_does_not_set_the_end_of_an_unresolved_interval(self):
        known = [inv('20260415000002', '2026-04-15', corr='기재정정', company='011170'), inv('20260520000003', '2026-05-20', corr='기재정정', company='298040')]
        out = verify([receipt(no='20260520000003', rcept='2026-05-20', revenue=90.0)], sessions(), inventory=known)
        self.assertEqual([(u['rcept_no'], u['affects_until']) for u in out['unresolved']], [('20260415000002', None)])


    def test_inputs_are_not_mutated(self):
        r = self.good();s = sessions();i = [inv('20260310000001', '2026-03-10')];before = copy.deepcopy((r, s, i))
        verify(r, s, inventory=i);self.assertEqual((r, s, i), before)


if __name__ == '__main__':unittest.main()
