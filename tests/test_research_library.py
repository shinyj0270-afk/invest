"""Synthetic-only Research Library privacy, provenance, history and engine checks."""
import copy
import contextlib
import io
import json
from unittest.mock import patch
import tempfile
import unittest
from pathlib import Path

from investment.core import digest
from investment.research_library import Library, analysis_context, trend_comparison, MASTERS, record_day
from datetime import datetime, timezone
from investment.telegram_research import channels, batch, TERMS
from investment.fixture import make_fixture


def source(access='public', origin='independent'):
    value = dict(title='Synthetic research', url='https://example.invalid/research', published_on='2026-01-01',
                accessed_on='2026-01-02', access=access, origin=origin, locator='synthetic section 1')
    if origin == 'telegram': value['channel_id'] = 'c1'
    return value


def card():
    return dict(master='minervini', strategies=['trend'], source_ids=['s1'], principle='Synthetic original interpretation',
                conditions=['Synthetic applicability'], counterexamples=['Synthetic failure'], interpretation='own_paraphrase')


def thesis():
    return dict(title='Synthetic sector hypothesis', sector='Synthetic industry', theme='Synthetic investment theme',
                claim='Unverified synthetic hypothesis', conditions=['Check demand'], invalidation=['Demand contracts'],
                as_of='2026-01-03', status='active', change_reason='Initial draft', instruments=[dict(code='000001', market='KOSPI', kind='stock')], master_ids=['m1'], seed_source_ids=[])


def evidence(stance='support', revision=1):
    return dict(thesis_id='t1', thesis_revision=revision, source_ids=['s1'], stance=stance,
                observation='Synthetic independent observation', reasoning='Synthetic causal caveat', observed_on='2026-01-04')


def permission():
    return dict(method='manual_reference', terms_url=TERMS, terms_checked_on='2026-01-01',
                platform_basis='Synthetic test only; not real permission', channel_basis='Synthetic test consent',
                reviewer='Synthetic reviewer', local_analysis_allowed=True)


def registry():
    return dict(core=[dict(id='c1', name='Synthetic core 1', enabled=True, permission=permission()),
                      dict(id='c2', name='Synthetic core 2', enabled=False, permission=None)],
                auxiliary=[dict(id='a1', name='Synthetic auxiliary', enabled=False, permission=None)])


def collection():
    return dict(start='2026-01-01', end='2026-01-03', checked_on='2026-01-04', missing='unknown',
                coverage_basis='Synthetic manual interval, not full archive', entries=[
                    dict(message_id=1, published_on='2026-01-02', reference='https://example.invalid/1'),
                    dict(message_id=3, published_on='2026-01-03', reference='https://example.invalid/3')])


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.lib = Library(self.tmp.name, 'home', 'fixture')

    def populated(self, access='public', origin='independent'):
        if origin == 'telegram': channels(self.lib, registry())
        self.lib.source('s1', source(access, origin))
        self.lib.master('m1', card())
        self.lib.thesis('t1', thesis())

    def review(self):
        return dict(reviewer='Synthetic reviewer', reviewed_on=record_day(datetime.now(timezone.utc).isoformat()), content_digest=digest(self.lib.draft('t1')),
                    independent_analysis=True, no_personal_data=True, redistribution_allowed=True)

    def test_real_unknown_profile_denied_and_db_modes_separate(self):
        with self.assertRaises(ValueError): Library(self.tmp.name, 'unknown')
        self.assertNotEqual(self.lib.path, Library(self.tmp.name, 'home').path)

    def test_telegram_home_gate_and_core_count(self):
        work = Library(self.tmp.name, 'work', 'fixture')
        with self.assertRaises(ValueError): channels(work, registry())
        with self.assertRaises(ValueError): batch(work, 'c1', collection())
        with self.assertRaises(ValueError): work.source('s1', source(origin='telegram'))
        wrong = registry(); wrong['core'].pop()
        with self.assertRaises(ValueError): channels(self.lib, wrong)

    def test_permission_required_and_auxiliary_opt_in(self):
        bad = registry(); bad['core'][0]['permission'] = None
        with self.assertRaises(ValueError): channels(self.lib, bad)
        bad = registry(); bad['core'][0]['permission']['method'] = 'scraper'
        with self.assertRaises(ValueError): channels(self.lib, bad)
        channels(self.lib, registry())
        with self.assertRaises(ValueError): batch(self.lib, 'a1', collection())

    def test_batch_coverage_dedup_and_id_gap_is_not_missingness(self):
        channels(self.lib, registry())
        value = collection(); value['entries'].append(copy.deepcopy(value['entries'][0]))
        report = batch(self.lib, 'c1', value)
        self.assertEqual((report['inserted'], report['duplicates']), (2, 1))
        self.assertEqual(report['missing'], 'unknown')
        self.assertEqual(report['completeness'], 'unverified')
        report = batch(self.lib, 'c1', value)
        self.assertEqual((report['inserted'], report['duplicates']), (0, 3))

    def test_conflicting_duplicate_rolls_back_entire_batch(self):
        channels(self.lib, registry()); batch(self.lib, 'c1', collection())
        value = collection(); value['entries'][0]['reference'] = 'https://example.invalid/changed'
        value['entries'].insert(0, dict(message_id=4, published_on='2026-01-02', reference='https://example.invalid/4'))
        with self.assertRaises(ValueError): batch(self.lib, 'c1', value)
        with self.lib.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM records WHERE kind='telegram'").fetchone()[0], 2)

    def test_window_invalid_input_and_raw_body_denied_before_write(self):
        channels(self.lib, registry())
        for mutate in (lambda x:x.update(end='2025-12-31'), lambda x:x['entries'][0].update(body='raw copy'),
                       lambda x:x['entries'][0].update(message_id=True)):
            value = collection(); mutate(value)
            with self.assertRaises(ValueError): batch(self.lib, 'c1', value)
        with self.lib.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM records WHERE kind='telegram'").fetchone()[0], 0)

    def test_source_url_date_and_raw_copy_rejected(self):
        for mutation in ({'url':'file:///private'}, {'published_on':'2027-01-01'}, {'full_text':'copyright copy'}, {'access_token':'synthetic'}):
            value = source(); value.update(mutation)
            with self.assertRaises(ValueError): self.lib.source('s1', value)

    def test_eight_master_slots_and_source_counterexample_required(self):
        self.assertEqual(len(MASTERS), 8)
        self.lib.source('s1', source())
        value = card(); value['counterexamples'] = []
        with self.assertRaises(ValueError): self.lib.master('m1', value)
        value = card(); value['source_ids'] = ['missing']
        with self.assertRaises(ValueError): self.lib.master('m1', value)

    def test_immutable_sources_cards_and_evidence(self):
        self.populated(); self.lib.evidence('e1', evidence())
        for method, key, value in ((self.lib.source,'s1',source()), (self.lib.master,'m1',card()), (self.lib.evidence,'e1',evidence())):
            with self.assertRaises(ValueError): method(key, value, 1)

    def test_thesis_history_conflict_and_chronology(self):
        self.populated(); changed = thesis(); changed.update(claim='Revised synthetic claim', as_of='2026-01-04', change_reason='Counterevidence')
        self.assertEqual(self.lib.thesis('t1', changed, 1), 2)
        with self.assertRaises(ValueError): self.lib.thesis('t1', changed, 1)
        with self.assertRaises(ValueError): self.lib.thesis('t1', thesis(), 2)
        history = self.lib.history('thesis', 't1')
        self.assertEqual(history[0]['value']['claim'], thesis()['claim'])
        self.assertEqual(len(history), 2)

    def test_evidence_dates_revisions_and_both_sides(self):
        self.populated()
        self.lib.evidence('e1', evidence()); self.lib.evidence('e2', evidence('refute'))
        draft = self.lib.draft('t1')
        self.assertIn('지지 근거', draft); self.assertIn('반박 근거', draft)
        self.assertIn('https://example.invalid/research', draft)
        bad = evidence(revision=2)
        with self.assertRaises(ValueError): self.lib.evidence('bad', bad)
        bad = evidence(); bad['observed_on'] = '2026-01-01'
        with self.assertRaises(ValueError): self.lib.evidence('bad', bad)

    def test_prior_evidence_not_presented_as_support_for_revised_claim(self):
        self.populated(); self.lib.evidence('e1', evidence())
        changed = thesis(); changed.update(as_of='2026-01-05', change_reason='Revised assumption')
        self.lib.thesis('t1', changed, 1)
        self.assertEqual(self.lib.evidence_for('t1', 2), [])
        self.assertEqual(len(self.lib.evidence_for('t1')), 1)
        self.assertIn('미확보', self.lib.draft('t1'))

    def test_approved_output_and_stale_digest(self):
        self.populated(); review = self.review()
        result = self.lib.approved_result('t1', review)
        self.assertNotIn('records', result); self.assertEqual(result['mode'], 'fixture')
        self.lib.evidence('e1', evidence())
        with self.assertRaises(ValueError): self.lib.approved_result('t1', review)

    def test_paid_private_and_telegram_derivation_cannot_be_shared(self):
        for access, origin in (('paid','independent'), ('private','independent'), ('public','telegram')):
            with self.subTest(access=access, origin=origin):
                with tempfile.TemporaryDirectory() as folder:
                    self.lib = Library(folder, 'home', 'fixture'); self.populated(access, origin)
                    with self.assertRaises(ValueError): self.lib.approved_result('t1', self.review())
                    changed = thesis(); changed['master_ids'] = []; changed['change_reason'] = 'Remove card'
                    self.lib.thesis('t1', changed, 1)
                    with self.assertRaises(ValueError): self.lib.approved_result('t1', self.review())

    def test_stock_engine_reused_input_unchanged_and_etf_pending(self):
        snapshot = make_fixture(); before = copy.deepcopy(snapshot)
        row = snapshot['companies'][-1]
        value = thesis(); value['instruments'] = [dict(code=row['code'], market=row['market'], kind='stock'), dict(code='999999', market='KOSPI', kind='etf')]
        result = analysis_context(value, snapshot)
        self.assertEqual(snapshot, before)
        self.assertEqual(result[0]['status'], 'linked'); self.assertIn('technical', result[0]['research'])
        self.assertEqual(result[1]['status'], 'pending')
        self.assertEqual(trend_comparison(result)['oneil']['pending'][0], 'EPS')

    def test_propose_links_distinct_sources_without_certifying_hypothesis(self):
        self.populated(); second = source(); second['url'] = 'https://example.invalid/research-2'; self.lib.source('s2', second)
        value = thesis(); value.pop('title'); value.pop('claim'); value.pop('change_reason')
        value.pop('status')
        value.pop('seed_source_ids')
        value['observations'] = [dict(source_id='s1', observation='Synthetic demand thesis', stance='support'),
                                 dict(source_id='s2', observation='Synthetic counterargument', stance='refute')]
        result = self.lib.propose(value)
        self.assertEqual(result['status'], 'unverified_candidate')
        self.assertEqual(result['observations'][1]['stance'], 'refute')
        self.assertEqual(len(self.lib.history('thesis', 't1')), 1)
        value['observations'][1]['source_id'] = 's1'
        with self.assertRaises(ValueError): self.lib.propose(value)

    def test_telegram_source_requires_permission_and_revocation_stops_reuse(self):
        with self.assertRaises(ValueError): self.lib.source('missing', source(origin='telegram'))
        self.populated(origin='telegram')
        revoked = registry(); revoked['core'][0]['enabled'] = False
        channels(self.lib, revoked, 1)
        with self.assertRaises(ValueError): self.lib.evidence('e1', evidence())
        with self.assertRaises(ValueError): self.lib.draft('t1')

    def test_old_refutation_revision_dates_and_restricted_label_remain_visible(self):
        self.populated(access='paid'); self.lib.evidence('e1', evidence('refute'))
        changed = thesis(); changed.update(as_of='2026-01-05', change_reason='Assumption changed')
        self.lib.thesis('t1', changed, 1)
        draft = self.lib.draft('t1')
        for token in ('revision 2', '2026-01-05', 'Assumption changed', 'r1', evidence()['observation'], 's1', '공유 제한', '기록일'):
            self.assertIn(token, draft)

    def test_noncanonical_future_dates_and_telegram_mislabel_rejected(self):
        for mutation in ({'accessed_on':'2026-W01-1'}, {'accessed_on':'2999-01-01'}, {'url':'https://t.me/synthetic/1'}):
            value = source(); value.update(mutation)
            with self.assertRaises(ValueError): self.lib.source('bad', value)

    def test_dart_canonical_query_allowed_sensitive_query_rejected(self):
        value = source(); value['url'] = 'https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260101000001'
        self.lib.source('dart', value)
        value['url'] = 'https://example.invalid/research?access_token=synthetic'
        with self.assertRaises(ValueError): self.lib.source('bad', value)

    def test_invalidated_requires_refutation_and_retired_preserves_history(self):
        self.populated(); changed = thesis(); changed.update(status='invalidated', as_of='2026-01-05', change_reason='Thesis failed')
        with self.assertRaises(ValueError): self.lib.thesis('t1', changed, 1)
        self.lib.evidence('e1', evidence('refute'))
        self.lib.thesis('t1', changed, 1)
        self.assertIn('invalidated', self.lib.draft('t1'))
        changed.update(status='retired', change_reason='Research retired')
        self.lib.thesis('t1', changed, 2)
        self.assertEqual(len(self.lib.history('thesis', 't1')), 3)

    def test_generated_restricted_seed_remains_restricted_after_removal(self):
        for access, origin in (('paid', 'independent'), ('public', 'telegram')):
            with self.subTest(access=access, origin=origin), tempfile.TemporaryDirectory() as folder:
                self.lib = Library(folder, 'home', 'fixture'); self.populated()
                if origin == 'telegram': channels(self.lib, registry())
                seed = source(access, origin); seed['url'] = 'https://example.invalid/restricted-seed'
                self.lib.source('seed', seed)
                value = {k:v for k,v in thesis().items() if k in ('sector','theme','as_of','conditions','invalidation','instruments','master_ids')}
                value['observations'] = [dict(source_id='s1', observation='Public synthetic note', stance='support'),
                                         dict(source_id='seed', observation='Restricted synthetic note', stance='refute')]
                candidate = self.lib.propose(value)
                self.assertTrue(candidate['restricted']); self.assertIn('공유 제한', candidate['sharing'])
                self.lib.thesis('t2', candidate['thesis'])
                review = self.review(); review['content_digest'] = digest(self.lib.draft('t2'))
                with self.assertRaises(ValueError): self.lib.approved_result('t2', review)
                candidate['thesis'].update(seed_source_ids=[], change_reason='Remove seeds')
                self.lib.thesis('t2', candidate['thesis'], 1)
                self.assertIn('공유 제한', self.lib.draft('t2'))
                review['content_digest'] = digest(self.lib.draft('t2'))
                with self.assertRaises(ValueError): self.lib.approved_result('t2', review)

    def test_backfilled_evidence_record_date_visible_and_predated_review_rejected(self):
        self.populated(); self.lib.evidence('e1', evidence('refute'))
        stamp = self.lib.history('evidence', 'e1')[0]['recorded_at']
        self.assertIn(stamp, self.lib.draft('t1')); self.assertIn('소급 입력', self.lib.draft('t1'))
        changed = thesis(); changed.update(as_of='2026-01-05', change_reason='Revision after counterevidence')
        self.lib.thesis('t1', changed, 1)
        self.assertIn(stamp, self.lib.draft('t1'))
        review = self.review(); review['reviewed_on'] = '2026-01-05'
        with self.assertRaises(ValueError): self.lib.approved_result('t1', review)


class CliTests(unittest.TestCase):
    def setUp(self):
        from tools import research_library as cli
        self.cli = cli
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.patch = patch.object(cli, 'ROOT', self.root); self.patch.start(); self.addCleanup(self.patch.stop)
        (self.root / 'config').mkdir(); (self.root / '.local').mkdir()

    def configure(self, profile):
        (self.root / 'config/local.json').write_text(json.dumps(dict(profile=profile, project_root='.')), encoding='utf-8')

    def run_cli(self, args):
        with patch('sys.argv', ['research_library.py']+args), contextlib.redirect_stdout(io.StringIO()) as output:
            self.cli.main()
        return output.getvalue()

    def test_home_gate_before_input_open_and_unknown_denied(self):
        self.configure('work')
        with self.assertRaisesRegex(ValueError, 'requires configured home'):
            self.run_cli(['telegram', '--id', 'c1', '--input', '.local/nonexistent.json'])
        self.assertFalse((self.root / '.local/research-library').exists())
        self.configure('unknown')
        with self.assertRaises(ValueError): self.run_cli(['source', '--id', 's1'])

    def test_path_escape_and_existing_output_preserved(self):
        self.configure('home')
        with self.assertRaises(ValueError): self.cli.local_path('.local/../tracked.json')
        existing = self.root / '.local/output.json'; existing.write_text('preserve', encoding='utf-8')
        with self.assertRaises(ValueError): self.run_cli(['source','--id','s1','--output','.local/output.json'])
        self.assertEqual(existing.read_text(), 'preserve')

    def test_source_input_roundtrip_and_master_catalog_without_config(self):
        self.assertEqual(len(json.loads(self.run_cli(['masters']))), 8)
        self.configure('home')
        (self.root / '.local/source.json').write_text(json.dumps(source()), encoding='utf-8')
        output = self.run_cli(['source','--id','s1','--input','.local/source.json'])
        self.assertEqual(json.loads(output)['revision'], 1)
        output = self.run_cli(['history','--kind','source','--id','s1'])
        self.assertEqual(json.loads(output)[0]['value']['title'], 'Synthetic research')

    def test_inspected_draft_lf_digest_and_approval_roundtrip(self):
        self.configure('home')
        lib = Library(self.root / '.local/research-library', 'home')
        lib.source('s1', source()); lib.master('m1', card()); lib.thesis('t1', thesis())
        output = self.run_cli(['draft','--id','t1','--output','.local/draft.md'])
        draft = self.root / '.local/draft.md'
        self.assertNotIn(b'\r\n', draft.read_bytes())
        self.assertIn(digest(lib.draft('t1')), output)
        review = dict(reviewer='Synthetic reviewer', reviewed_on=record_day(datetime.now(timezone.utc).isoformat()), content_digest=digest(lib.draft('t1')),
                      independent_analysis=True, no_personal_data=True, redistribution_allowed=True)
        (self.root / '.local/review.json').write_text(json.dumps(review), encoding='utf-8')
        args = ['approved-result','--id','t1','--input','.local/review.json','--draft','.local/draft.md']
        result = json.loads(self.run_cli(args))
        self.assertNotIn('reviewer', result['review'])
        draft.write_text('unreviewed change', encoding='utf-8')
        with self.assertRaises(ValueError): self.run_cli(args)


if __name__ == '__main__': unittest.main()
