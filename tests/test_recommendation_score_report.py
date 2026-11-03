import copy
import hashlib
import io
import sqlite3
import tempfile
import unittest
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path
from investment.recommendations import propose
from tests.test_dashboard_upgrade import recommendation_context
from tools.recommendation_score_report import (candidate_table, funnel, component_stats, leave_one_out, render, latest_snapshot, manifest, main, TERMS)

TODAY='2026-10-02'


def context():
    return copy.deepcopy(recommendation_context())


class ScoreReportTests(unittest.TestCase):
    def test_scores_and_exclusions_match_propose_exactly(self):
        c=context()
        rows=c['snapshot']['companies']
        rows[5]['common_financial']['metrics']['revenue_growth_pct']=5          # excluded: growth < 10
        c['research']['rows']['900006']['technical']['price_strength']['score']=60  # excluded: RS < 70
        table=candidate_table(c,TODAY)
        record=propose(c,created_on=TODAY)
        passed={r['code']:r['score'] for r in table if r['reason'] is None}
        for target in record['targets']+record['alternatives']:
            self.assertAlmostEqual(round(passed[target['code']],2),target['score'])
        self.assertEqual(dict(Counter(r['reason'] for r in table if r['reason'])),record['exclusion_reasons'])  # propose reports reason -> count
        self.assertEqual((len(passed),len(table)-len(passed)),(record['coverage']['qualified'],record['coverage']['excluded']))

    def test_funnel_counts_each_stage_in_order(self):
        c=context();rows=c['snapshot']['companies'];tech=c['research']['rows']
        rows[0]['discovery_allowed']=False
        rows[1]['common_financial']['ttm_complete']=False
        rows[2]['common_financial']['period']='2024-12-31'
        tech['900003']['technical']['short_rs']['1m']['score']=10
        rows[4]['common_financial']['ttm_ocf']=-1
        f=funnel(candidate_table(c,TODAY))
        self.assertEqual((f['universe'],f['not_discovery_allowed'],f['financial_missing'],f['financial_stale'],f['trend_failed'],f['growth_or_financial_failed'],f['passed']),(7,1,1,1,1,1,2))
        self.assertEqual(sum(f[k] for k in ('not_discovery_allowed','financial_missing','financial_stale','trend_failed','growth_or_financial_failed','passed')),7)

    def test_component_stats_cap_saturation_and_correlation(self):
        c=context()
        for i,row in enumerate(c['snapshot']['companies']):
            row['common_financial']['metrics']['revenue_growth_pct']=60+i*20   # 60..180 -> some above the 100 cap
            row['common_financial']['metrics']['roe_pct']=15
        s=component_stats(candidate_table(c,TODAY))
        self.assertEqual(s['n'],7);self.assertEqual(s['cap_binding']['growth'],4);self.assertEqual(s['cap_binding']['roe'],0)
        self.assertIsNone(s['correlations'][('short','roe')]['rho'])           # constant component: undefined, not 0
        self.assertEqual(set(s['correlations'][('rs','growth')]),{'rho','n'})

    def test_leave_one_out_changes_top_set_and_reports_direction(self):
        c=context();rows=c['snapshot']['companies'][:4];c['snapshot']['companies']=rows
        growth=[100,90,80,70];rs=[70,80,90,100]
        for i,row in enumerate(rows):
            row['common_financial']['metrics']['revenue_growth_pct']=growth[i]
            c['research']['rows'][row['code']]['technical']['price_strength']['score']=rs[i]
        out=leave_one_out(candidate_table(c,TODAY),top_n=1)
        self.assertEqual(out['baseline_top'],['900003'])                       # highest weighted score first (RS weight 0.4 dominates)
        self.assertEqual(out['without']['rs']['top_overlap'],0.0)              # without RS the growth leader wins instead
        self.assertEqual(out['without']['roe']['top_overlap'],1.0)
        self.assertEqual(set(out['without']),set(TERMS))

    def test_empty_and_all_excluded_inputs_do_not_crash(self):
        c=context();c['snapshot']['companies']=[]
        t=candidate_table(c,TODAY);self.assertEqual(t,[])
        self.assertEqual(funnel(t)['passed'],0)
        self.assertEqual(component_stats(t)['n'],0)
        self.assertIsNone(leave_one_out(t,top_n=3)['without']['rs']['top_overlap'])
        self.assertIn('통과',render(funnel(t),component_stats(t),leave_one_out(t,3),'빈 입력'))

    def test_latest_snapshot_reads_without_modifying_or_creating(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'research.sqlite3'
            db=sqlite3.connect(path);db.execute('CREATE TABLE snapshots(id TEXT PRIMARY KEY, created TEXT, status TEXT, payload TEXT)')
            db.execute("INSERT INTO snapshots VALUES('a','2026-10-01','complete','{\"companies\":[{\"code\":\"900000\"}],\"meta\":{}}')")
            db.execute("INSERT INTO snapshots VALUES('b','2026-10-02','staging','{\"companies\":[]}')");db.commit();db.close()
            before=hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(latest_snapshot(path)['companies'][0]['code'],'900000')   # newest *complete* row only
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)
            missing=Path(folder)/'none.sqlite3'
            with self.assertRaises(ValueError):latest_snapshot(missing)
            self.assertFalse(missing.exists())

    def test_manifest_detects_any_change_and_ignores_nothing_silently(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'a.json').write_text('1',encoding='utf-8');(root/'sub').mkdir();(root/'sub'/'b.sqlite3').write_bytes(b'x')
            first=manifest([root]);self.assertEqual(first,manifest([root]))
            (root/'sub'/'b.sqlite3').write_bytes(b'y');self.assertNotEqual(first,manifest([root]))
            (root/'new.json').write_text('2',encoding='utf-8');self.assertNotEqual(manifest([root]),first)

    def test_cli_synthetic_prints_sections_and_bad_root_returns_error(self):
        out=io.StringIO()
        with redirect_stdout(out):code=main(['--synthetic'])
        text=out.getvalue();self.assertEqual(code,0)
        for needle in ('필터 통과 깔때기','구성항 간 순위 상관','한 항 제거','상한(cap)','합성 입력'):self.assertIn(needle,text)
        with redirect_stdout(io.StringIO()):self.assertEqual(main(['--root','Z:/definitely/not/here']),2)


if __name__=='__main__':unittest.main()
