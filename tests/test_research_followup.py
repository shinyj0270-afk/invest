import copy
import json
import tempfile
import unittest
from pathlib import Path
from investment.research_followup import freeze, evaluate, project, plan_path
from tests.test_portfolio_risk import risk_fixture


class FollowupTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)
        self.targets,self.cache,self.cutoff=risk_fixture()
        for index in self.cache['history']['benchmarks'].values():
            index['prices'].insert(0,dict(index['prices'][0],date='2024-12-31'))
        self.record=dict(id='THESIS-SYNTHETIC',revision=1,recorded_at='2024-12-30T00:00:00+00:00',
                         value=dict(as_of='2024-12-30',claim='Synthetic hypothesis'))
        self.candidates=[dict(code='900000',name='Synthetic',market='KOSPI',industry='Synthetic sector')]

    def freeze(self):
        return freeze(self.root,'work',self.record,self.candidates,'Synthetic fixed cohort',frozen_at='2024-12-31T00:00:00+00:00')

    def test_idempotent_immutable_plan_and_conflicts(self):
        first=self.freeze();path=plan_path(self.root,'work',self.record['id'],1);before=path.read_bytes()
        self.assertTrue(first['created']);self.assertFalse(self.freeze()['created']);self.assertEqual(path.read_bytes(),before)
        self.candidates[0]['code']='900001'
        with self.assertRaises(ValueError):self.freeze()
        self.assertEqual(path.read_bytes(),before)

    def test_fixed_initial_path_known_returns_and_completed_horizons(self):
        plan=self.freeze()['plan'];before=copy.deepcopy(self.cache)
        result=evaluate(plan,self.cache,self.cutoff)
        self.assertEqual(result['status'],'observing')
        self.assertEqual([h['status'] for h in result['horizons']],['ready']*3)
        for h in result['horizons']:
            expected=((1.1*.9)**(h['days']//2)*(1.1 if h['days']%2 else 1)-1)*100
            self.assertAlmostEqual(h['return_pct'],expected)
            self.assertEqual(h['benchmark_return_pct'],0)
            self.assertEqual(h['observations'],h['days'])
        self.assertEqual(self.cache,before)

    def test_no_retrospective_freeze_and_revision_changes(self):
        self.record['recorded_at']='2025-01-03T00:00:00+00:00'
        with self.assertRaises(ValueError):self.freeze()
        self.record['recorded_at']='2024-12-30T00:00:00+00:00';self.freeze()
        self.record['value']['claim']='Changed'
        self.assertEqual(project(self.root,'work',self.record,self.cache)['status'],'pending')

    def test_unmatured_is_not_zero_or_backfilled(self):
        # Today-created plans cannot use historical returns, even if long histories exist.
        p=freeze(self.root,'work',self.record,self.candidates,'Fixed now')['plan']
        r=evaluate(p,self.cache,self.cutoff)
        self.assertIsNone(r['entry_date'])
        self.assertTrue(all(h['status']=='waiting' and 'return_pct' not in h for h in r['horizons']))

    def test_missing_member_date_and_identity_never_drops_candidate(self):
        p=self.freeze()['plan']
        for kind in ('gap','identity','basis'):
            cache=copy.deepcopy(self.cache);row=cache['history']['histories']['900000']
            if kind=='gap':del row['prices'][20]
            elif kind=='identity':row['symbol']='999999'
            else:row['prices'][20]['adjustment_basis']='index_level'
            r=evaluate(p,cache,self.cutoff)
            self.assertTrue(all(h['status']=='pending' and 'return_pct' not in h for h in r['horizons']))

    def test_future_observations_do_not_change_results(self):
        p=self.freeze()['plan'];before=evaluate(p,self.cache,self.cutoff)
        for r in list(self.cache['history']['benchmarks'].values())+list(self.cache['history']['histories'].values()):
            r['prices'].append(dict(r['prices'][-1],date='2030-01-01',close=1e12,final=False))
        self.assertEqual(evaluate(p,self.cache,self.cutoff),before)

    def test_truncated_calendar_does_not_move_entry_forward(self):
        p=self.freeze()['plan']
        for index in self.cache['history']['benchmarks'].values():index['prices'].pop(0)
        r=evaluate(p,self.cache,self.cutoff)
        self.assertEqual(r['status'],'pending');self.assertEqual(r['horizons'],[])

    def test_invalid_digest_and_empty_cohort(self):
        with self.assertRaises(ValueError):freeze(self.root,'work',self.record,[],'Empty')
        self.freeze();path=plan_path(self.root,'work',self.record['id'],1)
        p=json.loads(path.read_text(encoding='utf-8'));p['frozen_on']='2000-01-01';path.write_text(json.dumps(p))
        self.assertEqual(project(self.root,'work',self.record,self.cache)['status'],'pending')


if __name__=='__main__':unittest.main()
