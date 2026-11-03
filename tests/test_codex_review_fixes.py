"""Regression tests for the independent Codex review of 2026-11-03 (each finding reproduced before it was fixed)."""
import copy
import io
import tempfile
import threading
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch
import numpy as np
from investment import trial_log
from investment.market_discovery import technical
from investment.market_history import benchmark_calendar
from investment.recommendations import propose
from tests.test_dashboard_upgrade import recommendation_context
from tests.test_trend_sensitivity_report import sessions, bars, DAYS
from tools import factor_overlap_report, recommendation_score_report, threshold_sensitivity_report, trend_sensitivity_report
from tools.factor_overlap_report import spearman
from tools.overlap_coverage_sim import stationary_bootstrap_means
from tools.recommendation_score_report import candidate_table, leave_one_out
from tools.trend_sensitivity_report import TREND_BASE, price_status

ENTRY=dict(experiment_id='x',rule_version='v',parameter_set={'a':1},decision='pending')


class TrendParityTests(unittest.TestCase):
    def test_sma_arithmetic_matches_production_on_a_floating_point_edge(self):
        days=sessions();closes=[0.03]*100+[0.1]*50+[0.08]*100+[0.1397959183673469]*49+[0.15]
        bench={s:dict(symbol=s,kind='index',prices=bars(days,[100.0]*DAYS,True),source=dict(url='x://'+s)) for s in ('KOSPI','KOSDAQ')}
        t=technical(dict(symbol='A',kind='item',prices=bars(days,closes)),bench['KOSPI'],benchmark_calendar(bench),include_series=False)
        e=dict(dates=days,closes=closes,bm={d:100.0 for d in days},base_status=t['price_trend_status'])
        self.assertEqual(price_status(e,TREND_BASE),t['price_trend_status'])

    def test_report_fails_loudly_when_baseline_parity_is_broken(self):
        out=io.StringIO()
        with patch('tools.trend_sensitivity_report.parity',return_value=1),redirect_stdout(out):
            self.assertEqual(trend_sensitivity_report.main(['--synthetic']),4)
        self.assertIn('불일치',out.getvalue())


class TrialLogIntegrityTests(unittest.TestCase):
    def test_concurrent_writers_keep_a_valid_chain(self):
        with tempfile.TemporaryDirectory() as folder:
            errors=[]
            def work():
                try:trial_log.record(folder,'work',ENTRY)
                except Exception as exc:errors.append(exc)
            threads=[threading.Thread(target=work) for _ in range(8)]
            [t.start() for t in threads];[t.join() for t in threads]
            self.assertEqual(errors,[]);self.assertEqual([r['trial_index'] for r in trial_log.read_all(folder,'work')],list(range(1,9)))
            self.assertFalse(list((Path(folder)/'.local/trial-log').glob('*.lock')))

    def test_unterminated_final_line_is_refused_and_left_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            trial_log.record(folder,'work',ENTRY);path=trial_log.log_path(folder,'work')
            path.write_text(path.read_text(encoding='utf-8').rstrip('\n'),encoding='utf-8',newline='')
            before=path.read_bytes()
            with self.assertRaises(ValueError):trial_log.record(folder,'work',ENTRY)
            self.assertEqual(path.read_bytes(),before)

    def test_stale_lock_times_out_with_a_clear_error_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            path=trial_log.log_path(folder,'work');path.parent.mkdir(parents=True);path.with_suffix('.lock').write_text('stale')
            with patch.object(trial_log,'LOCK_WAIT_SECONDS',0.1),self.assertRaisesRegex(ValueError,'잠금'):trial_log.record(folder,'work',ENTRY)
            self.assertFalse(path.exists())


class SurvivingMutantTests(unittest.TestCase):
    def test_stationary_bootstrap_has_the_variance_of_a_resample(self):
        x=np.random.default_rng(2).normal(size=400)
        means=stationary_bootstrap_means(x,1,4000,np.random.default_rng(3))                      # block length 1 == iid resampling
        self.assertAlmostEqual(float(means.std(ddof=1)),float(x.std(ddof=1))/20,delta=0.15*float(x.std(ddof=1))/20)

    def test_spearman_uses_average_ranks_for_ties(self):
        self.assertAlmostEqual(spearman([1,2,2,4],[1,2,3,4]),0.9486832980505138,places=12)

    def test_recommendation_filters_are_inclusive_at_the_boundary_exactly_like_propose(self):
        c=copy.deepcopy(recommendation_context());t=c['research']['rows']
        t['900000']['technical']['price_strength']['score']=70
        t['900001']['technical']['short_rs']['1m']['score']=50
        today='2026-10-02';table=candidate_table(c,today)
        passed={r['code'] for r in table if r['stage']=='passed'}
        record=propose(c,created_on=today);expected={x['code'] for x in record['targets']+record['alternatives']}
        self.assertTrue({'900000','900001'}<=passed);self.assertEqual(passed,expected)

    def test_top_n_must_be_a_positive_integer(self):
        c=copy.deepcopy(recommendation_context());table=candidate_table(c,'2026-10-02')
        for bad in (0,-1,2.5):
            with self.subTest(top_n=bad),self.assertRaises(ValueError):leave_one_out(table,bad)
            with self.subTest(factor_top_n=bad),self.assertRaises(ValueError):factor_overlap_report.leave_one_out([],factor_overlap_report.WEIGHTS,bad)
        for module,args in ((recommendation_score_report,['--synthetic']),(factor_overlap_report,['--fixture'])):
            with self.subTest(cli=module.__name__),redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):module.main(args+['--top-n','0'])


class RecordBeforeEvaluateTests(unittest.TestCase):
    def run_main(self,module,extra_patches):
        order=[]
        def mark(name,value=None):
            def inner(*a,**k):
                order.append(name);return value
            return inner
        local=dict(data_dir=Path('Z:/nowhere'),profile='work')
        patches=[patch('investment.local_config.load_local',return_value=local),patch.object(module,'manifest',side_effect=mark('manifest',{})),
            patch.object(module,'record_trials',side_effect=mark('record')),patch.object(module,'summary',return_value=dict(trials=1,distinct_parameter_sets=1,head_digest='h'))]
        patches+=extra_patches(order,mark)
        for p in patches:p.start()
        try:
            with redirect_stdout(io.StringIO()):module.main(['--root','Z:/nowhere'])
        finally:
            patch.stopall()
        return order

    def test_threshold_tool_records_trials_before_evaluating(self):
        m=threshold_sensitivity_report
        order=self.run_main(m,lambda o,mark:[patch.object(m,'build_real_context',return_value=({},'2026-10-02',{})),patch.object(m,'feature_rows',return_value=[]),
            patch.object(m,'sensitivity',side_effect=mark('evaluate',[dict(params=m.BASE,passed=0,retained=0,added=0,dropped=0)])),patch.object(m,'blockers',return_value={})])
        self.assertLess(order.index('record'),order.index('evaluate'))

    def test_trend_tool_records_trials_before_evaluating(self):
        m=trend_sensitivity_report
        def extra(o,mark):
            res=[dict(params=m.TREND_BASE,status_pass=0,passed=0,retained=0,added=0,dropped=0,parity_mismatch=0)]
            return [patch.object(m,'build_real_context',return_value=({'snapshot':{'companies':[]}},'2026-10-02',{})),patch.object(m,'feature_rows',return_value=[]),
                patch.object(m,'benchmark_calendar',return_value={}),patch.object(m,'eligible_records',return_value={}),
                patch('investment.market_discovery.load_market_cache',return_value={'history':{}}),patch('tools.recommendation_score_report.latest_snapshot',return_value={}),
                patch.object(m,'trend_sensitivity',side_effect=mark('evaluate',res))]
        order=self.run_main(m,extra)
        self.assertLess(order.index('record'),order.index('evaluate'))


if __name__=='__main__':unittest.main()
