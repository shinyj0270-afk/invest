"""Killers for mutants that survived the independent Codex mutation sweep of 2026-11-03 (recommendations.py, trial_log.py).
Each assertion was shown to pass on the original and fail on its mutant."""
import copy
import json
import tempfile
import unittest
from investment import recommendations as rec
from investment import trial_log
from investment.core import digest
from tests.test_dashboard_upgrade import recommendation_context

TODAY='2026-10-02'


def one_candidate():
    c=copy.deepcopy(recommendation_context());c['snapshot']['companies']=c['snapshot']['companies'][:1];return c


class RecommendationBoundaryTests(unittest.TestCase):
    def test_price_snapshot_exactly_seven_days_old_is_accepted(self):
        c=one_candidate();c['snapshot']['meta']['price_date']='2026-09-25'
        self.assertEqual(rec.propose(c,created_on=TODAY)['coverage']['qualified'],1)

    def test_revenue_growth_exactly_ten_percent_qualifies(self):
        c=one_candidate();c['snapshot']['companies'][0]['common_financial']['metrics']['revenue_growth_pct']=10
        self.assertEqual(rec.propose(c,created_on=TODAY)['coverage']['qualified'],1)

    def test_debt_ratio_exactly_two_hundred_percent_qualifies(self):
        c=one_candidate();c['snapshot']['companies'][0]['common_financial']['metrics']['debt_ratio_pct']=200
        self.assertEqual(rec.propose(c,created_on=TODAY)['coverage']['qualified'],1)

    def test_highest_scores_are_selected_first(self):
        value=rec.propose(recommendation_context(),created_on=TODAY)
        self.assertEqual([r['code'] for r in value['targets']],[str(900000+i) for i in range(5)])


class TrialLogBoundaryTests(unittest.TestCase):
    def test_text_field_of_exactly_the_maximum_length_is_accepted(self):
        with tempfile.TemporaryDirectory() as t:
            e=dict(experiment_id='x'*100,rule_version='v',parameter_set={'a':1},decision='pending')
            self.assertEqual(trial_log.record(t,'work',e)['experiment_id'],'x'*100)

    def test_single_day_period_is_accepted(self):
        with tempfile.TemporaryDirectory() as t:
            e=dict(experiment_id='x',rule_version='v',parameter_set={'a':1},decision='pending',train_period=['2026-01-01']*2)
            self.assertEqual(trial_log.record(t,'work',e)['train_period'],['2026-01-01']*2)

    def test_a_row_with_a_wrong_previous_digest_breaks_the_chain_even_if_its_own_digest_is_recomputed(self):
        with tempfile.TemporaryDirectory() as t:
            e=dict(experiment_id='x',rule_version='v',parameter_set={'a':1},decision='pending')
            trial_log.record(t,'work',e);trial_log.record(t,'work',e);p=trial_log.log_path(t,'work')
            rows=[json.loads(s) for s in p.read_text(encoding='utf-8').splitlines()];rows[-1]['prev_digest']='0'*64
            body={k:v for k,v in rows[-1].items() if k!='digest'};rows[-1]['digest']=digest(body)
            p.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
            with self.assertRaises(ValueError):trial_log.read_all(t,'work')


if __name__=='__main__':unittest.main()
