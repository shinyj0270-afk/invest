"""Synthetic isolated tests; never calls a provider or touches operational data."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from investment.agent_providers import decode_response, generate, ProviderError, request_payload, settings
from investment.research_library import Library
from investment.research_agents import Runner, approve, prepare, validate_draft
from investment.core import digest


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.lib = Library(self.root / 'library', 'work', 'fixture')
        self.today = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
        self.source = dict(title='Synthetic filing', url='https://example.invalid/report', published_on=None,
                           accessed_on=self.today, access='public', origin='independent', locator='Synthetic section')
        self.lib.source('s1', self.source)
        self.input = dict(question='Synthetic research question', as_of=self.today,
                          observations=[dict(source_id='s1', observation='Synthetic observation')],
                          external_model_allowed=True, independent_analysis=True, no_personal_data=True)
        self.config = {r: dict(provider=p, model='test-model', timeout_seconds=5, max_output_tokens=256)
                       for r, p in [('research', 'anthropic'), ('review', 'openai')]}
        self.draft = dict(title='Synthetic hypothesis', hypothesis='Conditional inference', conditions=['Condition'],
                          invalidation=['Countercondition'], missing_evidence=['No counterevidence supplied'],
                          claims=[dict(statement='Observed', stance='context', source_ids=['s1'])])
        self.review = dict(verdict='pass', issues=[], summary='Synthetic review only')
        self.calls = []

    def call(self, config, prompt):
        self.calls.append((config, prompt))
        return dict(value=deepcopy(self.draft if len(self.calls) == 1 else self.review),
                    usage={'input_tokens': 10, 'output_tokens': 10}, cost_usd=None)

    def run_job(self, call=None):
        return Runner(self.lib, self.root / 'runs', self.config, call or self.call).run(self.input)

    def approval(self, job):
        return dict(review_digest=job['review_digest'], reviewer='Synthetic human', reviewed_on=self.today,
                    human_reviewed=True, independent_analysis=True, no_personal_data=True)

    def test_pipeline_waits_for_human_without_thesis_writes(self):
        job = self.run_job()
        self.assertEqual('awaiting_human', job['state'])
        self.assertEqual(2, len(self.calls))
        saved = json.loads((self.root/'runs/work/fixture'/job['id']/'run.json').read_text(encoding='utf-8'))
        self.assertEqual(job, saved)
        with self.lib.connect() as db:
            self.assertEqual([('source',)], db.execute('SELECT DISTINCT kind FROM records').fetchall())
        self.assertIsNone(job['steps'][0]['cost_usd'])

    def test_approval_idempotent_and_separate_note(self):
        job = self.run_job(); approval = self.approval(job)
        self.assertEqual(1, approve(self.lib, job, approval))
        self.assertEqual(1, approve(self.lib, job, approval))
        self.assertEqual(1, len(self.lib.history('agent_note', job['id'])))
        self.assertEqual([], self.lib.history('thesis', job['id']))

    def test_tampering_and_nonhuman_review_rejected(self):
        job = self.run_job(); approval = self.approval(job)
        approval['human_reviewed'] = False
        with self.assertRaises(ValueError): approve(self.lib, job, approval)
        approval['human_reviewed'] = True
        job['draft']['title'] = 'Changed after review'
        with self.assertRaises(ValueError): approve(self.lib, job, approval)

    def test_source_exclusion_blocks_before_call(self):
        self.lib._put('catalog', digest(['source', 's1']), {'stage': 'excluded'})
        with self.assertRaises(ValueError): self.run_job()
        self.assertEqual([], self.calls)

    def test_private_and_telegram_sources_blocked(self):
        for access, origin in [('private', 'independent'), ('paid', 'independent'), ('public', 'telegram')]:
            with self.subTest(access=access, origin=origin):
                with patch.object(self.lib, 'get', return_value=dict(self.source, access=access, origin=origin)):
                    with self.assertRaises(ValueError): prepare(self.lib, self.input)

    def test_permission_and_date_rejected(self):
        self.input['external_model_allowed'] = False
        with self.assertRaises(ValueError): prepare(self.lib, self.input)
        self.input['external_model_allowed'] = True; self.input['as_of'] = '2020-01-01'
        with self.assertRaises(ValueError): prepare(self.lib, self.input)

    def test_unknown_citation_stops_review(self):
        self.draft['claims'][0]['source_ids'] = ['invented']
        job = self.run_job()
        self.assertEqual('failed', job['state']); self.assertEqual(1, len(self.calls))

    def test_source_revocation_between_steps_and_approval(self):
        def revoke(config, prompt):
            result = self.call(config, prompt)
            self.lib._put('catalog', digest(['source', 's1']), {'stage': 'excluded'})
            return result
        job = self.run_job(revoke)
        self.assertEqual('failed', job['state']); self.assertEqual(1, len(self.calls))

    def test_stale_approval_rejected(self):
        job = self.run_job()
        self.lib._put('catalog', digest(['source', 's1']), {'stage': 'excluded'})
        with self.assertRaises(ValueError): approve(self.lib, job, self.approval(job))

    def test_provider_failure_redacted_no_retry(self):
        def fail(config, prompt):
            self.calls.append(1)
            raise RuntimeError('sensitive upstream body')
        job = self.run_job(fail)
        self.assertEqual('failed', job['state']); self.assertEqual(1, len(self.calls))
        self.assertNotIn('sensitive upstream', json.dumps(job))

    def test_model_revision_cannot_be_approved(self):
        self.review = dict(verdict='revise', issues=['Unsupported inference'], summary='Requires revision')
        job = self.run_job()
        self.assertEqual('needs_revision', job['state'])
        with self.assertRaises(ValueError): approve(self.lib, job, self.approval(job))

    def test_payload_contracts(self):
        url, body = request_payload(self.config['review'], 'JSON test')
        self.assertEqual('https://api.openai.com/v1/responses', url)
        self.assertIs(False, body['store']); self.assertNotIn('tools', body)
        url, body = request_payload(self.config['research'], 'JSON test')
        self.assertEqual('https://api.anthropic.com/v1/messages', url)
        self.assertEqual(256, body['max_tokens'])

    def test_response_completion_and_usage(self):
        response = dict(status='completed', output=[dict(type='message', content=[dict(type='output_text', text='{"ok":true}')])])
        self.assertEqual({'ok': True}, decode_response('openai', response)['value'])
        self.assertIsNone(decode_response('openai', response)['usage']['input_tokens'])
        response['status'] = 'incomplete'
        with self.assertRaises(ProviderError): decode_response('openai', response)
        for reason in ('max_tokens', 'tool_use', 'refusal'):
            with self.assertRaises(ProviderError): decode_response('anthropic', dict(stop_reason=reason))
        self.assertEqual({'ok': True}, decode_response('anthropic', dict(stop_reason='end_turn', content=[dict(type='text', text='{"ok":true}')]))['value'])

    def test_deadline_and_credential_no_secret_output(self):
        gate = patch('investment.agent_providers.API_ENABLED', True)
        gate.start(); self.addCleanup(gate.stop)
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'synthetic-only'}):
            with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('worker', 5)):
                with self.assertRaisesRegex(ProviderError, '^deadline_exceeded$'):
                    generate(self.config['review'], 'JSON test')
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaisesRegex(ProviderError, '^credential_missing$'):
                generate(self.config['review'], 'JSON test')

    def test_invalid_limits(self):
        for field, value in [('timeout_seconds', 1000), ('max_output_tokens', True), ('provider', 'other')]:
            with self.assertRaises(ValueError): settings(dict(self.config['review'], **{field: value}))

    def test_worker_error_body_is_not_returned(self):
        gate = patch('investment.agent_providers.API_ENABLED', True)
        gate.start(); self.addCleanup(gate.stop)
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'synthetic-only'}):
            response = subprocess.CompletedProcess([], 0, '{"error":"sensitive unexpected error"}', 'sensitive stderr')
            with patch('subprocess.run', return_value=response):
                with self.assertRaisesRegex(ProviderError, '^provider_worker_failed$'):
                    generate(self.config['review'], 'JSON test')

    def test_refusal_malformed_json_and_inconsistent_review(self):
        response = dict(status='completed', output=[dict(type='message', content=[dict(type='refusal', refusal='no')])])
        with self.assertRaisesRegex(ProviderError, 'provider_refusal'): decode_response('openai', response)
        with self.assertRaises(ProviderError):
            decode_response('anthropic', dict(stop_reason='end_turn', content=[dict(type='text', text='not json')]))
        self.review['issues'] = ['Unresolved']
        self.assertEqual('failed', self.run_job()['state'])


if __name__ == '__main__': unittest.main()
