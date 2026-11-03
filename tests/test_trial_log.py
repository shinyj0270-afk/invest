import json
import tempfile
import unittest
from pathlib import Path
from investment.trial_log import record, read_all, summary, log_path


def entry(**over):
    base=dict(experiment_id='EXP-SYNTH-1',rule_version='rules-v1',parameter_set=dict(z_threshold=1.5,winsor_tail=0.02,window=21),
        label_horizon=63,train_period=['2010-01-04','2015-12-30'],validation_period=['2016-01-04','2017-12-28'],
        test_period=None,decision='pending',discard_reason=None,metrics_ref=None)
    base.update(over);return base


class TrialLogTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup);self.root=Path(self.folder.name)

    def test_append_only_index_and_summary_counts_every_trial(self):
        a=record(self.root,'work',entry());b=record(self.root,'work',entry(parameter_set=dict(z_threshold=1.4,winsor_tail=0.02,window=21),decision='rejected',discard_reason='worse validation'))
        c=record(self.root,'work',entry(decision='adopted'))
        self.assertEqual([a['trial_index'],b['trial_index'],c['trial_index']],[1,2,3])
        s=summary(self.root,'work')
        self.assertEqual((s['trials'],s['distinct_parameter_sets']),(3,2))
        self.assertEqual(s['by_decision'],dict(pending=1,rejected=1,adopted=1))
        self.assertEqual(len(read_all(self.root,'work')),3)

    def test_empty_log_summary_is_zero_not_missing(self):
        s=summary(self.root,'home');self.assertEqual((s['trials'],s['distinct_parameter_sets']),(0,0))

    def test_rejects_invalid_entries_without_writing(self):
        for bad in (entry(decision='maybe'),entry(experiment_id=''),entry(parameter_set={}),entry(parameter_set=dict(z=float('nan'))),
                    entry(parameter_set=dict(z=[1])),entry(label_horizon=100),entry(train_period=['2016-01-01','2015-01-01']),
                    entry(train_period=['2010-13-01','2011-01-01']),entry(decision='rejected',discard_reason=None),entry(extra_field=1)):
            with self.assertRaises(ValueError):record(self.root,'work',bad)
        with self.assertRaises(ValueError):record(self.root,'laptop',entry())
        self.assertFalse(log_path(self.root,'work').exists())

    def test_tampering_or_deletion_is_detected(self):
        for i in range(3):record(self.root,'work',entry(experiment_id=f'EXP-{i}'))
        path=log_path(self.root,'work');lines=path.read_text(encoding='utf-8').splitlines()
        edited=json.loads(lines[1]);edited['decision']='adopted';lines[1]=json.dumps(edited,ensure_ascii=False)
        path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
        with self.assertRaises(ValueError):read_all(self.root,'work')
        path.write_text('\n'.join([lines[0],lines[2]])+'\n',encoding='utf-8')
        with self.assertRaises(ValueError):summary(self.root,'work')

    def test_profiles_are_separate_logs(self):
        record(self.root,'work',entry());record(self.root,'home',entry())
        self.assertNotEqual(log_path(self.root,'work'),log_path(self.root,'home'))
        self.assertEqual(summary(self.root,'work')['trials'],1)


if __name__=='__main__':unittest.main()
