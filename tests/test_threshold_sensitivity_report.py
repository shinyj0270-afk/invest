import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from investment.trial_log import read_all, summary, record
from tests.test_dashboard_upgrade import recommendation_context
from tools.recommendation_score_report import candidate_table, synthetic_context
from tools.threshold_sensitivity_report import (BASE, feature_rows, passed_codes, conditions, variants, trial_entries, record_trials, sensitivity, blockers, render, main)

TODAY='2026-10-02'


def context():
    return copy.deepcopy(recommendation_context())


class SensitivityTests(unittest.TestCase):
    def test_baseline_matches_candidate_table_exactly(self):
        for c in (context(),synthetic_context()):
            rows=feature_rows(c,TODAY)
            expected={r['code'] for r in candidate_table(c,TODAY) if r['stage']=='passed'}
            self.assertEqual(passed_codes(rows,BASE),expected)
        self.assertGreater(len(expected),0)

    def test_feature_rows_cover_only_companies_that_reach_the_trend_check(self):
        c=context();c['snapshot']['companies'][0]['discovery_allowed']=False;c['snapshot']['companies'][1]['common_financial']['ttm_complete']=False
        self.assertEqual(len(feature_rows(c,TODAY)),5)

    def test_each_threshold_moves_the_pass_set_in_the_expected_direction(self):
        c=synthetic_context();rows=feature_rows(c,TODAY);base=passed_codes(rows,BASE)
        looser=passed_codes(rows,{**BASE,'rs_min':60});tighter=passed_codes(rows,{**BASE,'rs_min':80})
        self.assertTrue(base<=looser);self.assertTrue(tighter<=base)
        self.assertTrue(passed_codes(rows,{**BASE,'growth_min':20})<=base);self.assertTrue(base<=passed_codes(rows,{**BASE,'debt_max':250}))
        self.assertTrue(base<=passed_codes(rows,{**BASE,'use_sma':False}));self.assertTrue(base<=passed_codes(rows,{**BASE,'use_trend_status':False}))

    def test_boundary_values_are_inclusive_exactly_as_propose(self):
        c=context();t=c['research']['rows']
        t['900000']['technical']['price_strength']['score']=70      # rs == min passes
        t['900001']['technical']['short_rs']['1m']['score']=50      # short == min passes
        c['snapshot']['companies'][2]['common_financial']['metrics']['revenue_growth_pct']=10
        c['snapshot']['companies'][3]['common_financial']['metrics']['debt_ratio_pct']=200
        t['900004']['technical']['close']=90                        # close == sma200 fails
        rows=feature_rows(c,TODAY);got=passed_codes(rows,BASE)
        self.assertEqual({'900000','900001','900002','900003'}<=got,True);self.assertNotIn('900004',got)
        self.assertEqual(got,{r['code'] for r in candidate_table(c,TODAY) if r['stage']=='passed'})

    def test_blockers_count_failures_and_sole_blockers(self):
        c=context();t=c['research']['rows'];rows=c['snapshot']['companies']
        t['900000']['technical']['price_strength']['score']=60                 # sole blocker: rs
        t['900001']['technical']['price_strength']['score']=60;t['900001']['technical']['short_rs']['1m']['score']=10   # two blockers
        rows[2]['common_financial']['metrics']['debt_ratio_pct']=300            # sole blocker: debt
        t['900003']['technical']['close']=None                                  # missing data
        b=blockers(feature_rows(c,TODAY))
        self.assertEqual((b['rs']['failed'],b['rs']['sole']),(2,1));self.assertEqual((b['short']['failed'],b['short']['sole']),(1,0))
        self.assertEqual((b['debt']['failed'],b['debt']['sole']),(1,1));self.assertEqual((b['trend_data']['failed'],b['trend_data']['sole']),(1,1))
        self.assertEqual(set(conditions(feature_rows(c,TODAY)[0],BASE)),set(b))

    def test_sensitivity_reports_retained_added_dropped_without_company_codes(self):
        rows=feature_rows(synthetic_context(),TODAY);out=sensitivity(rows,variants())
        self.assertEqual(out[0]['params'],BASE);self.assertEqual((out[0]['added'],out[0]['dropped']),(0,0))
        for v in out:
            self.assertEqual(v['retained']+v['dropped'],out[0]['passed']);self.assertEqual(v['retained']+v['added'],v['passed'])
            self.assertFalse({'codes','passed_codes'}&set(v))

    def test_variants_are_distinct_and_baseline_is_first(self):
        vs=variants();self.assertEqual(vs[0],BASE)
        keys={json.dumps(v,sort_keys=True) for v in vs};self.assertEqual(len(keys),len(vs))
        self.assertEqual(len(trial_entries(vs,'S10-test')),len(vs)-1)           # baseline is the existing rule, not a new trial

    def test_trial_entries_are_valid_and_never_adopt(self):
        with tempfile.TemporaryDirectory() as folder:
            record_trials(folder,'work',variants(),'S10-test')
            rows=read_all(folder,'work');self.assertEqual(len(rows),len(variants())-1)
            self.assertEqual({r['decision'] for r in rows},{'rejected'});self.assertTrue(all(r['discard_reason'] for r in rows))
            self.assertEqual(summary(folder,'work')['trials'],len(rows))
            record_trials(folder,'work',variants(),'S10-test')                    # a second run counts as more trials, honestly
            self.assertEqual(summary(folder,'work')['trials'],2*len(rows))

    def test_render_states_no_adoption_and_has_no_company_codes(self):
        c=synthetic_context();rows=feature_rows(c,TODAY);text=render(sensitivity(rows,variants()),blockers(rows),'합성 입력',len(variants())-1)
        for needle in ('채택하지 않','단독 차단','rs_min','합성 입력'):self.assertIn(needle,text)
        self.assertNotIn('900000',text)

    def test_cli_synthetic_does_not_write_a_trial_log(self):
        out=io.StringIO()
        with redirect_stdout(out):code=main(['--synthetic'])
        self.assertEqual(code,0);self.assertIn('시도 로그',out.getvalue())
        with redirect_stdout(io.StringIO()):self.assertEqual(main(['--root','Z:/definitely/not/here']),2)


if __name__=='__main__':unittest.main()
