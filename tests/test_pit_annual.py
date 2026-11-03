import copy
import unittest
from datetime import date, timedelta
from investment.core import select_vintage
from investment.research import annual_signals, quality_factors
from investment.pit_annual import project, project_all, available_at, POLICY


def sessions(start='2020-01-02', end='2028-12-29', holidays=()):
    out=[];d=date.fromisoformat(start);stop=date.fromisoformat(end)
    while d<=stop:
        if d.weekday()<5 and d.isoformat() not in holidays:out.append(d.isoformat())
        d+=timedelta(days=1)
    return out


def receipt(no='20260310000001',rcept='2026-03-10',year=2025,revenue=100.0,**over):
    base=dict(company='005930',period_end=f'{year}-12-31',basis='CFS',report_kind='annual',rcept_no=no,rcept_dt=rcept,
        values=dict(revenue=revenue,op=10.0,ocf=12.0))
    base.update(over);return base


class AvailabilityTests(unittest.TestCase):
    def test_usable_from_is_the_first_session_strictly_after_the_receipt_date(self):
        s=sessions()
        self.assertEqual(available_at('2026-03-19',s),'2026-03-20')       # Thursday -> Friday
        self.assertEqual(available_at('2026-03-20',s),'2026-03-23')       # Friday -> Monday
        self.assertEqual(available_at('2026-03-21',s),'2026-03-23')       # Saturday -> Monday
    def test_holidays_are_skipped_only_if_the_calendar_omits_them(self):
        s=sessions(holidays=('2026-03-23',))
        self.assertEqual(available_at('2026-03-20',s),'2026-03-24')
    def test_receipt_after_the_calendar_end_has_no_date(self):
        self.assertIsNone(available_at('2028-12-29',sessions()))


class ProjectionTests(unittest.TestCase):
    def test_row_carries_values_provenance_and_policy_and_is_hidden_on_the_filing_day(self):
        out=project([receipt()],sessions());row=out['rows'][0]
        self.assertEqual((row['period_end'],row['basis'],row['available_at'],row['revenue']),('2025-12-31','CFS','2026-03-11',100.0))
        self.assertEqual((row['rcept_no'],row['rcept_dt'],row['policy']),('20260310000001','2026-03-10',POLICY))
        self.assertEqual(out['blocked'],[])
        self.assertEqual(select_vintage(out['rows'],'2026-03-10'),[]);self.assertEqual(len(select_vintage(out['rows'],'2026-03-11')),1)

    def test_a_later_correction_never_changes_what_an_earlier_cutoff_sees(self):
        original=receipt();correction=receipt(no='20260520000002',rcept='2026-05-20',revenue=90.0)
        base=project([original],sessions())['rows'];both=project([original,correction],sessions())['rows']
        self.assertEqual(select_vintage(base,'2026-05-20'),select_vintage(both,'2026-05-20'))
        self.assertEqual(select_vintage(both,'2026-05-20')[0]['revenue'],100.0)
        self.assertEqual(select_vintage(both,'2026-05-21')[0]['revenue'],90.0)       # even a 10% correction is seen once usable

    def test_receipt_order_in_the_input_does_not_matter(self):
        a=receipt();b=receipt(no='20260520000002',rcept='2026-05-20',revenue=90.0)
        self.assertEqual(project([a,b],sessions()),project([b,a],sessions()))

    def test_same_day_competing_versions_with_different_values_are_blocked(self):
        a=receipt();b=receipt(no='20260310000002',revenue=95.0)
        out=project([a,b],sessions())
        self.assertEqual([r.get('ambiguous') for r in out['rows']],[True]);self.assertNotIn('revenue',out['rows'][0])      # a value-less marker, never a guess
        self.assertEqual({x['reason'] for x in out['blocked']},{'ambiguous_same_availability'})
        self.assertEqual(len(out['blocked']),2)

    def test_same_day_duplicates_with_identical_values_keep_one_row(self):
        out=project([receipt(),receipt(no='20260310000002')],sessions())
        self.assertEqual(len(out['rows']),1);self.assertEqual(out['rows'][0]['rcept_no'],'20260310000001');self.assertEqual(out['blocked'],[])

    def test_two_receipt_days_that_map_to_the_same_session_with_different_values_are_blocked(self):
        a=receipt(no='20260320000001',rcept='2026-03-20');b=receipt(no='20260321000002',rcept='2026-03-21',revenue=80.0)   # Fri and Sat both usable Monday
        out=project([a,b],sessions());self.assertEqual([r.get('ambiguous') for r in out['rows']],[True]);self.assertEqual(len(out['blocked']),2)

    def test_bad_receipts_are_blocked_with_a_reason_and_never_projected(self):
        s=sessions()
        cases={'identity':receipt(no='20260311000001'),                       # receipt number date differs from rcept_dt
               'identity_format':receipt(no='123'),
               'not_annual':receipt(report_kind='quarter'),
               'calendar_gap':receipt(no='20281229000001',rcept='2028-12-29'),
               'bad_values':receipt(values=dict(revenue=float('nan'))),
               'bad_period':receipt(period_end='2025-13-31')}
        for reason,r in cases.items():
            with self.subTest(reason=reason):
                out=project([r],s);self.assertEqual(out['rows'],[]);self.assertEqual(out['blocked'][0]['reason'],reason)

    def test_missing_values_stay_missing_and_nothing_is_imputed(self):
        row=project([receipt(values=dict(revenue=100.0))],sessions())['rows'][0]
        self.assertNotIn('op',row);self.assertNotIn('ocf',row)

    def test_inputs_are_not_mutated(self):
        r=[receipt(),receipt(no='20260520000002',rcept='2026-05-20',revenue=90.0)];s=sessions();before=copy.deepcopy((r,s))
        project(r,s);self.assertEqual((r,s),before)


class ResearchIntegrationTests(unittest.TestCase):
    def four_years(self,extra=()):
        rs=[receipt(no=f'{y+1}0310000001',rcept=f'{y+1}-03-10',year=y,revenue=100.0*1.1**(y-2022)) for y in range(2022,2026)]
        return project(rs+list(extra),sessions())['rows']

    def test_four_consecutive_years_feed_annual_signals_only_after_each_is_usable(self):
        rows=self.four_years()
        self.assertIsNone(annual_signals(rows,'2026-03-10')['g_sales'])         # 2025 annual not yet usable: only three years
        self.assertAlmostEqual(annual_signals(rows,'2026-03-11')['g_sales'],0.1,places=6)

    def test_a_future_restatement_leaves_the_earlier_cutoff_signal_unchanged(self):
        restate=receipt(no='20260901000009',rcept='2026-09-01',year=2025,revenue=50.0)
        base=self.four_years();with_future=self.four_years([restate])
        self.assertEqual(annual_signals(base,'2026-06-30'),annual_signals(with_future,'2026-06-30'))
        self.assertNotEqual(annual_signals(base,'2026-09-02')['g_sales'],annual_signals(with_future,'2026-09-02')['g_sales'])


class CodexReviewTests(unittest.TestCase):
    def four_years(self,company='005930',**values):
        rs=[receipt(no=f'{y+1}0310000001',rcept=f'{y+1}-03-10',year=y,company=company,values=dict(dict(revenue=100.0,op=10.0,ocf=12.0),**values)) for y in range(2022,2026)]
        return project(rs,sessions())['rows']

    def test_project_requires_one_company_and_basis_and_project_all_partitions(self):
        a=receipt();b=receipt(company='000660',revenue=200.0)
        with self.assertRaises(ValueError):project([a,b],sessions())
        with self.assertRaises(ValueError):project([a,receipt(basis='OFS')],sessions())
        out=project_all([a,b],sessions())
        self.assertEqual(set(out),{('005930','CFS'),('000660','CFS')});self.assertEqual(out[('000660','CFS')]['rows'][0]['revenue'],200.0)
        self.assertEqual(len(out[('005930','CFS')]['rows']),1)       # same availability, different values, different companies: both kept, none blocked

    def test_verification_flag_must_be_a_real_boolean(self):
        base=dict(equity=100.0,debt=20.0,cash=20.0,effective_tax_rate=.2)
        ok=project([receipt(values=dict(revenue=1.0,tax_verified=True,**base))],sessions());self.assertEqual(ok['blocked'],[])
        for bad in ('false',1,0,'True'):
            with self.subTest(flag=bad):
                out=project([receipt(values=dict(revenue=1.0,tax_verified=bad,**base))],sessions())
                self.assertEqual(out['blocked'][0]['reason'],'bad_values')
        rows=self.four_years(equity=100.0,debt=20.0,cash=20.0,effective_tax_rate=.2,tax_verified=True)
        self.assertAlmostEqual(quality_factors(dict(annual=rows,metrics={}),'2026-03-11')['Q'],.08)

    def test_numeric_fields_reject_bool_text_overflow_and_domain_violations(self):
        for key,val in (('revenue',True),('revenue','100'),('revenue',10**400),('revenue',-1.0),('debt',-1.0),('cash',-1.0),('dps',-1.0),('effective_tax_rate',1.5),('effective_tax_rate',-.1),('op',float('inf'))):
            with self.subTest(key=key):
                out=project([receipt(values={key:val})],sessions());self.assertEqual(out['rows'],[]);self.assertEqual(out['blocked'][0]['reason'],'bad_values')

    def test_unknown_keys_and_empty_payloads_are_blocked_not_silently_erased(self):
        for values in ({'reveneu':100.0},{},{'revenue':1.0,'extra':float('nan')}):
            with self.subTest(values=values):self.assertEqual(project([receipt(values=values)],sessions())['blocked'][0]['reason'],'bad_values')
        self.assertEqual(project([receipt(fiscal_year=1900)],sessions())['blocked'][0]['reason'],'unknown_field')

    def test_int_and_float_values_are_canonically_equal_and_output_is_order_independent(self):
        a=receipt(values=dict(revenue=100));b=receipt(no='20260310000001',values=dict(revenue=100.0))
        x=project([a,b],sessions());y=project([b,a],sessions());self.assertEqual(x,y);self.assertEqual(repr(x),repr(y))
        self.assertIsInstance(x['rows'][0]['revenue'],float)

    def test_ambiguous_corrections_supersede_the_original_with_a_value_less_row(self):
        o=receipt();c1=receipt(no='20260520000001',rcept='2026-05-20',revenue=90.0);c2=receipt(no='20260520000002',rcept='2026-05-20',revenue=80.0)
        out=project([o,c1,c2],sessions());rows=out['rows']
        self.assertEqual(select_vintage(rows,'2026-05-20')[0]['revenue'],100.0)           # before the corrections are usable
        later=select_vintage(rows,'2026-05-21')[0]
        self.assertNotIn('revenue',later);self.assertTrue(later['ambiguous']);self.assertEqual(len(out['blocked']),2)

    def test_calendar_is_validated_and_coverage_is_required(self):
        for bad in (['2026-03-10x'],[None],['2026-03-21'],[]):                               # not ISO / not a date / Saturday session / empty
            with self.subTest(calendar=bad),self.assertRaises(ValueError):project([receipt()],bad)
        out=project([receipt()],['2027-01-04']+sessions('2027-01-05','2027-12-31'))                          # first session far after the receipt
        self.assertEqual(out['blocked'][0]['reason'],'calendar_gap')

    def test_unsorted_and_duplicate_sessions_are_normalised(self):
        s=['2026-03-12','2026-03-11','2026-03-11']+sessions('2026-03-13','2026-03-31')
        self.assertEqual(project([receipt()],s)['rows'][0]['available_at'],'2026-03-11')

    def test_identity_and_scope_checks(self):
        cases={'bad_company':receipt(company=''),'bad_basis':receipt(basis='garbage'),'period_after_receipt':receipt(period_end='2026-12-31'),
               'not_december':receipt(period_end='2025-09-30')}
        for reason,r in cases.items():
            with self.subTest(reason=reason):self.assertEqual(project([r],sessions())['blocked'][0]['reason'],reason)

    def test_surviving_mutant_killers(self):
        o=receipt();down=receipt(no='20260520000002',rcept='2026-05-20',revenue=90.0);back=receipt(no='20260910000003',rcept='2026-09-10',revenue=100.0)
        rows=project([o,down,back],sessions())['rows'];self.assertEqual(len(rows),3)                            # equal values on different dates are not deduplicated
        self.assertEqual(select_vintage(rows,'2026-09-14')[0]['rcept_no'],'20260910000003')
        small=receipt(no='20260520000009',rcept='2026-05-20',revenue=99.0)
        self.assertEqual(select_vintage(project([o,small],sessions())['rows'],'2026-05-21')[0]['revenue'],99.0)  # no materiality threshold here
        partial=receipt(no='20260520000008',rcept='2026-05-20',values=dict(revenue=90.0))
        sel=select_vintage(project([o,partial],sessions())['rows'],'2026-05-21')[0]
        self.assertNotIn('op',sel);self.assertNotIn('ocf',sel)                                                   # snapshot semantics: nothing is inherited


class RealDataDateGapTests(unittest.TestCase):
    def test_a_later_receipt_date_than_the_number_date_is_accepted_and_the_later_date_drives_eligibility(self):
        real = receipt(no='20230308000776', rcept='2023-03-09', year=2022)                      # shape seen in real DART data
        out = project([real], sessions())
        self.assertEqual(out['blocked'], []);self.assertEqual(out['rows'][0]['available_at'], '2023-03-10')   # next session after 03-09, not after 03-08
        self.assertEqual(select_vintage(out['rows'], '2023-03-09'), [])

    def test_a_receipt_date_earlier_than_the_number_date_or_more_than_seven_days_later_is_blocked(self):
        for no, rcept in (('20230310000001', '2023-03-09'), ('20230301000001', '2023-03-09')):
            out = project([receipt(no=no, rcept=rcept, year=2022)], sessions())
            self.assertEqual([b['reason'] for b in out['blocked']], ['identity'])
        self.assertEqual(project([receipt(no='20230302000001', rcept='2023-03-09', year=2022)], sessions())['blocked'], [])      # exactly 7 days


if __name__=='__main__':unittest.main()
