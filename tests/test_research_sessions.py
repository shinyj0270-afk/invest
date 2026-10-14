from copy import deepcopy
import unittest
from unittest.mock import patch
from tests import test_research_agents as fixtures
from investment.agent_providers import generate, worker, ProviderError
from investment.research_sessions import SessionRunner
from investment.research_agents import approve


class SessionTests(unittest.TestCase):
    setUp = fixtures.AgentTests.setUp
    approval = fixtures.AgentTests.approval
    def test_offline_handoff_and_human_gate(self):
        runner = SessionRunner(self.lib, self.root/'sessions')
        with patch('subprocess.run', side_effect=AssertionError('No subprocess allowed')):
            job = runner.create(self.input); folder = runner.save(job)
            self.assertIn('Do not use an API key', runner.packet(job))
            result = dict(agent='Claude', model='unknown', value=self.draft)
            job = runner.accept(job, 'research', result)
            runner.save(job, 'awaiting_session_draft')
            result = dict(agent='Codex', model='unknown', value=self.review)
            job = runner.accept(job, 'review', result)
            runner.save(job, 'awaiting_session_review')
            self.assertEqual('awaiting_human', job['state'])
            self.assertEqual(1, approve(self.lib, job, self.approval(job)))

    def test_same_agent_and_wrong_stage_rejected(self):
        runner = SessionRunner(self.lib, self.root/'sessions')
        job = runner.create(self.input)
        job = runner.accept(job, 'research', dict(agent='Claude', model='unknown', value=self.draft))
        with self.assertRaises(ValueError):
            runner.accept(job, 'review', dict(agent='Claude', model='unknown', value=self.review))
        with self.assertRaises(ValueError):
            runner.accept(job, 'research', dict(agent='Codex', model='unknown', value=self.draft))

    def test_api_blocked_even_with_keys(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'synthetic-only'}):
            with patch('subprocess.run', side_effect=AssertionError('Must not launch')):
                with self.assertRaisesRegex(ProviderError, 'api_disabled_by_project_policy'):
                    generate(self.config['review'], 'JSON')
                with self.assertRaisesRegex(ProviderError, 'api_disabled_by_project_policy'): worker()

    def test_revision_preserves_failed_attempt_and_requires_new_review(self):
        runner=SessionRunner(self.lib,self.root/'sessions')
        job=runner.accept(runner.create(self.input),'research',dict(agent='Claude',model='unknown',value=self.draft))
        review=dict(verdict='revise',issues=['Missing data is context'],summary='Revise')
        job=runner.accept(job,'review',dict(agent='Codex',model='unknown',value=review))
        self.assertIn('Missing data is context',runner.packet(job))
        with self.assertRaises(ValueError):
            runner.accept(job,'revision',dict(agent='Codex',model='unknown',value=self.draft))
        job=runner.accept(job,'revision',dict(agent='Claude',model='unknown',value=self.draft))
        self.assertEqual('awaiting_session_review',job['state'])
        self.assertIsNone(job['review']);self.assertNotIn('review_digest',job)
        self.assertEqual(review,job['attempts'][0]['review'])
        self.assertEqual('awaiting_human',runner.accept(job,'review',dict(agent='Codex',model='unknown',value=self.review))['state'])


if __name__ == '__main__': unittest.main()
