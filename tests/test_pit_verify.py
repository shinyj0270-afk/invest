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


def inv(no, rcept, period='2025-12', corr='none'):
    return dict(rcept_no=no, rcept_dt=rcept, title_period=period, correction=corr, kind='annual')


class VerifyTests(unittest.TestCase):
    def good(self):
        return [receipt(), receipt(no='20260520000002', rcept='2026-05-20', revenue=90.0), receipt(no='20270310000003', rcept='2027-03-10', year=2026, revenue=120.0)]

    def test_a_correct_projection_passes_every_check_and_reports_counts(self):
        out = verify(self.good(), sessions())
        self.assertTrue(out['ok']);self.assertEqual({k: v['ok'] for k, v in out['checks'].items()},
            {'filing_day_exclusion': True, 'correction_replay': True, 'order_independence': True, 'single_scope': True})
        self.assertEqual((out['counts']['rows'], out['counts']['ambiguous'], out['counts']['blocked']), (3, 0, {}))
        self.assertIn('회사 단위 복원', out['notice'])

    def test_a_projection_that_leaks_the_filing_day_is_caught(self):
        def leaky(receipts, cal):
            result = project(receipts, cal)
            return dict(result, rows=[dict(r, available_at=r.get('rcept_dt', r['available_at'])) for r in result['rows']])
        out = verify(self.good(), sessions(), project_fn=leaky)
        self.assertFalse(out['ok']);self.assertFalse(out['checks']['filing_day_exclusion']['ok'])

    def test_a_projection_where_a_later_receipt_changes_earlier_cutoffs_is_caught(self):
        def retroactive(receipts, cal):                    # a correction overwrites the original's row, dated early
            result = project(receipts, cal);rows = [dict(r) for r in result['rows']]
            for r in rows:
                if r.get('rcept_no') == '20260520000002':r['available_at'] = '2026-03-12'
            return dict(result, rows=rows)
        out = verify(self.good(), sessions(), project_fn=retroactive)
        self.assertFalse(out['checks']['correction_replay']['ok'])

    def test_an_order_dependent_projection_is_caught(self):
        def unstable(receipts, cal):
            result = project(receipts, cal);return dict(result, rows=result['rows'][::1] if receipts and receipts[0]['rcept_no'] == '20260310000001' else result['rows'][::-1])
        self.assertFalse(verify(self.good(), sessions(), project_fn=unstable)['checks']['order_independence']['ok'])

    def test_mixed_companies_are_reported_instead_of_silently_merged(self):
        out = verify([receipt(), receipt(no='20260310000009', company='011170')], sessions())
        self.assertFalse(out['checks']['single_scope']['ok'])

    def test_blocked_and_ambiguous_receipts_are_counted(self):
        two_same_day = [receipt(no='20260520000001', rcept='2026-05-20', revenue=90.0), receipt(no='20260520000002', rcept='2026-05-20', revenue=80.0)]
        bad = receipt(no='20260310000007');bad['report_kind'] = 'quarter'
        out = verify([receipt()] + two_same_day + [bad], sessions())
        self.assertEqual(out['counts']['ambiguous'], 1);self.assertEqual(out['counts']['blocked'], {'ambiguous_same_availability': 2, 'not_annual': 1})

    def test_a_known_later_correction_that_never_produced_a_row_is_reported_as_unresolved(self):
        known = [inv('20260310000001', '2026-03-10'), inv('20260520000002', '2026-05-20', corr='기재정정')]
        out = verify([receipt()], sessions(), inventory=known)                         # the correction failed extraction: no receipt for it
        self.assertEqual([u['rcept_no'] for u in out['unresolved']], ['20260520000002'])
        self.assertFalse(out['ok'])
        resolved = verify([receipt(), receipt(no='20260520000002', rcept='2026-05-20', revenue=90.0)], sessions(), inventory=known)
        self.assertEqual(resolved['unresolved'], []);self.assertTrue(resolved['ok'])

    def test_an_unresolved_receipt_that_is_not_the_latest_for_its_period_is_not_flagged(self):
        known = [inv('20260310000001', '2026-03-10'), inv('20260520000002', '2026-05-20', corr='기재정정')]
        out = verify([receipt(no='20260520000002', rcept='2026-05-20', revenue=90.0)], sessions(), inventory=known)
        self.assertEqual(out['unresolved'], [])                                           # the older original is simply not needed
    def test_two_rows_with_the_same_identity_and_availability_shadow_each_other_and_are_caught(self):
        def tied(receipts, cal):
            result = project(receipts, cal);rows = [dict(r) for r in result['rows']]
            extra = dict(rows[0], rcept_no='20260310000099');return dict(result, rows=rows + [extra])
        out = verify([receipt()], sessions(), project_fn=tied)
        self.assertFalse(out['checks']['filing_day_exclusion']['ok'])
        self.assertIn('not_visible_when_usable', [p['problem'] for p in out['checks']['filing_day_exclusion']['problems']])

    def test_receipts_inside_an_ambiguity_group_are_accounted_for_not_reported_as_unresolved(self):
        a = receipt(no='20260520000001', rcept='2026-05-20', revenue=90.0);b = receipt(no='20260520000002', rcept='2026-05-20', revenue=80.0)
        known = [inv('20260310000001', '2026-03-10'), inv('20260520000001', '2026-05-20', corr='기재정정'), inv('20260520000002', '2026-05-20', corr='기재정정')]
        out = verify([receipt(), a, b], sessions(), inventory=known)
        self.assertEqual(out['unresolved'], []);self.assertEqual(out['counts']['ambiguous'], 1)


    def test_inputs_are_not_mutated(self):
        r = self.good();s = sessions();i = [inv('20260310000001', '2026-03-10')];before = copy.deepcopy((r, s, i))
        verify(r, s, inventory=i);self.assertEqual((r, s, i), before)


if __name__ == '__main__':unittest.main()
