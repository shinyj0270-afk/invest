"""A stale review must not overwrite a job that went through revise -> new draft meanwhile (Codex bug-class hunt, finding 3)."""
import json
import unittest
from tests import test_research_agents as fixtures
from investment.core import digest
from investment.research_sessions import SessionRunner


class StaleSaveTests(unittest.TestCase):
    setUp = fixtures.AgentTests.setUp

    def prepared_job(self):
        runner = SessionRunner(self.lib, self.root / 'sessions')
        job = runner.create(self.input);runner.save(job)
        job = runner.accept(job, 'research', dict(agent='Claude', model='unknown', value=self.draft))
        runner.save(job, 'awaiting_session_draft')
        return runner, job

    def test_state_cycle_does_not_let_a_stale_process_overwrite_the_newer_draft(self):
        runner, job = self.prepared_job()
        stale = json.loads(json.dumps(job))                                  # process A read the job in awaiting_session_review
        before = digest(stale)
        revise = dict(verdict='revise', issues=['x'], summary='s')           # process B: revise review, then the author's new draft
        b = runner.accept(json.loads(json.dumps(job)), 'review', dict(agent='Codex', model='unknown', value=revise))
        runner.save(b, 'awaiting_session_review', expected_digest=before)
        b = runner.accept(b, 'revision', dict(agent='Claude', model='unknown', value=self.draft))
        runner.save(b, 'needs_revision')
        self.assertEqual(b['state'], 'awaiting_session_review')              # same state label as when A read the job
        a = runner.accept(stale, 'review', dict(agent='Codex', model='unknown', value=self.review))
        with self.assertRaisesRegex(ValueError, 'Concurrent'):
            runner.save(a, 'awaiting_session_review', expected_digest=before)
        saved = json.loads((runner.root / self.lib.profile / self.lib.mode / job['id'] / 'run.json').read_text(encoding='utf-8'))
        self.assertTrue(saved['attempts'])                                    # the revision history was not lost

    def test_matching_digest_still_saves_and_state_only_callers_still_work(self):
        runner, job = self.prepared_job()
        done = runner.accept(job, 'review', dict(agent='Codex', model='unknown', value=self.review))
        runner.save(done, 'awaiting_session_review', expected_digest=digest(job))
        again, other = self.prepared_job()
        other2 = runner.accept(other, 'review', dict(agent='Codex', model='unknown', value=self.review))
        runner.save(other2, 'awaiting_session_review')                        # legacy call without a digest


if __name__ == '__main__': unittest.main()
