import io
import unittest
from contextlib import redirect_stdout
from tools.factor_overlap_report import spearman, factor_percentiles, correlation_matrix, leave_one_out, missing_report, build_report, main, FACTORS


def row(code, **factors):
    base=dict(Q=None,G=None,C=None,V=None,B=None);base.update(factors)
    return dict(code=code,factors=base)


def six(**override):
    rows=[]
    for i in range(6):
        f=dict(Q=i/10,G=i/10,C=(5-i)/10,V=0.05,B=-0.1*(i%3))
        f.update({k:v for k,v in override.items()})
        rows.append(row(f'90000{i}',**f))
    return rows


class FactorOverlapTests(unittest.TestCase):
    def test_spearman_known_values_ties_and_small_samples(self):
        self.assertAlmostEqual(spearman([1,2,3,4],[10,20,30,40]),1.0)
        self.assertAlmostEqual(spearman([1,2,3,4],[4,3,2,1]),-1.0)
        self.assertIsNone(spearman([1,1,1,1],[1,2,3,4]))          # constant factor: correlation undefined, not 0
        self.assertIsNone(spearman([1,2],[1,2]))                    # fewer than 3 pairs
        self.assertAlmostEqual(spearman([1,2,2,4],[1,2,2,4]),1.0)  # ties use average ranks

    def test_matrix_skips_missing_pairs_and_reports_pair_counts(self):
        rows=six();rows[0]['factors']['G']=None
        m=correlation_matrix(rows)
        self.assertEqual(m[('Q','G')]['n'],5);self.assertAlmostEqual(m[('Q','G')]['rho'],1.0)
        self.assertAlmostEqual(m[('Q','C')]['rho'],-1.0);self.assertIsNone(m[('Q','V')]['rho'])
        self.assertEqual(m[('Q','G')],m[('G','Q')])

    def test_percentiles_use_cohort_midrank(self):
        p=factor_percentiles(six())
        self.assertAlmostEqual(p['Q'][0],0.5/6);self.assertAlmostEqual(p['Q'][5],5.5/6)

    def test_leave_one_out_constant_factor_changes_nothing_and_dominant_factor_changes_top_set(self):
        rows=six(V=0.05)
        loo=leave_one_out(rows,dict(Q=.3,G=.25,C=.2,V=.15,B=.1),top_n=3)
        self.assertEqual(loo['baseline_scored'],6)
        self.assertAlmostEqual(loo['without']['V']['top_overlap'],1.0)
        pair=[row(f'91000{i}',Q=i/10,G=(3-i)/10) for i in range(4)]
        swap=leave_one_out(pair,dict(Q=.6,G=.4),top_n=1)
        self.assertEqual(swap['baseline_top'],['910003'])           # highest weighted percentile is ranked first
        self.assertEqual(swap['without']['Q']['top_overlap'],0.0)   # Q decides the baseline winner; without it G picks another
        self.assertEqual(swap['without']['G']['top_overlap'],1.0)
        self.assertEqual(set(loo['without']),set(FACTORS))

    def test_rows_missing_any_factor_get_no_score_and_reasons_are_counted(self):
        rows=six();rows[1]['factors']['V']=None;rows[2]['factors']['V']=None;rows[3]['factors']['Q']=None
        r=missing_report(rows)
        self.assertEqual((r['total'],r['scored'],r['unscored']),(6,3,3))
        self.assertEqual(r['missing_by_factor'],dict(Q=1,G=0,C=0,V=2,B=0))
        loo=leave_one_out(rows,dict(Q=.3,G=.25,C=.2,V=.15,B=.1),top_n=2)
        self.assertEqual(loo['baseline_scored'],3)

    def test_empty_and_tiny_inputs_do_not_crash(self):
        r=build_report([],top_n=3);self.assertEqual(r['missing']['total'],0)
        self.assertIsNone(build_report(six()[:2],top_n=3)['correlations'][('Q','G')]['rho'])

    def test_cli_on_synthetic_fixture_prints_all_sections_and_reads_no_real_data(self):
        out=io.StringIO()
        with redirect_stdout(out):code=main(['--fixture'])
        text=out.getvalue();self.assertEqual(code,0)
        for needle in ('요인 간 순위 상관','한 요인 제거','점수 미계산','합성 fixture'):self.assertIn(needle,text)


if __name__=='__main__':unittest.main()
