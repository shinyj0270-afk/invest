"""Offline handoff for existing Codex/Claude sessions. Never launches a model."""
from copy import deepcopy
import json
from pathlib import Path
import uuid
import re

from .core import digest
from .research_agents import prepare, current, prompt, stamp, validate_draft, validate_review
from .research_library import fields, text


class SessionRunner:
    def __init__(self, lib, root):
        self.lib, self.root = lib, Path(root)

    def create(self, value):
        prepared = prepare(self.lib, value)
        job = dict(version=1, id=uuid.uuid4().hex, created=stamp(), state='awaiting_session_draft',
                   prepared=prepared, config={'execution': 'existing_sessions', 'paid_api': False},
                   steps=[], draft=None, review=None)
        return job

    def accept(self, job, role, response):
        job = deepcopy(job)
        if job['config'] != {'execution': 'existing_sessions', 'paid_api': False}:
            raise ValueError('Existing-session job required')
        if role not in ('research', 'review', 'revision'): raise ValueError('Unknown role')
        expected = {'research':'awaiting_session_draft','review':'awaiting_session_review','revision':'needs_revision'}[role]
        if job['state'] != expected: raise ValueError('Unexpected stage; preserve existing result')
        current(self.lib, job['prepared'])
        fields(response, ('agent', 'model', 'value'))
        if response['agent'] not in ('Codex', 'Claude'): raise ValueError('Existing Codex/Claude session required')
        text(response['model'], 120)
        if role in ('research', 'revision'):
            if role == 'revision':
                if response['agent'] != job['steps'][0]['agent']: raise ValueError('Revision must use original author')
                job.setdefault('attempts', []).append(dict(draft=deepcopy(job['draft']), review=deepcopy(job['review']),
                                                         review_digest=job.get('review_digest')))
                job['review'] = None
                job.pop('review_digest', None)
            job['draft'] = validate_draft(response['value'], job['prepared']['sources'])
            job['state'] = 'awaiting_session_review'
        else:
            if response['agent'] == job['steps'][0]['agent']:
                raise ValueError('Review must use the other agent')
            job['review'] = validate_review(response['value'])
            job['state'] = 'awaiting_human' if job['review']['verdict'] == 'pass' else 'needs_revision'
            job['review_digest'] = digest({k: job[k] for k in ('prepared', 'config', 'draft', 'review')})
        job['steps'].append(dict(role=role, agent=response['agent'], model=response['model'],
                                 recorded_at=stamp(), state='completed', usage=None, cost_usd=None,
                                 provenance='session_result_supplied_not_independently_authenticated'))
        return job

    def packet(self, job):
        current(self.lib, job['prepared'])
        if job['state'] not in ('awaiting_session_draft', 'awaiting_session_review', 'needs_revision'):
            raise ValueError('No session task pending')
        draft = job['draft'] if job['state'] == 'awaiting_session_review' else None
        correction = ''
        if job['state'] == 'needs_revision':
            correction = '\nRevise the previous draft addressing all review issues. Return a complete new draft with the original draft schema.\nPREVIOUS_JSON:\n' + json.dumps(dict(draft=job['draft'],review=job['review']),ensure_ascii=False)
        return ('Use your existing subscription session only. Do not use an API key, buy credits, '
                'enable paid overage, or spawn another model. If included usage is unavailable, stop. '
                'Read project AGENTS/CLAUDE and current state instructions first. '
                'Return the requested JSON as the value in an envelope with exact keys '
                'agent (Codex or Claude), model (actual model ID, or unknown), value. '
                'Do not approve on behalf of a human.\n\n' + prompt(job['prepared'], draft) + correction)

    def save(self, job, expected_state=None):
        if not re.fullmatch('[a-f0-9]{32}', job['id']): raise ValueError('Invalid run ID')
        folder = self.root / self.lib.profile / self.lib.mode / job['id']
        if expected_state is None:
            folder.mkdir(parents=True, exist_ok=False)
        # Exclusive transition lock prevents competing imports from losing data.
        lock = folder / 'transition.lock'
        handle = lock.open('x', encoding='utf-8')
        try:
            with handle:
                path = folder/'run.json'
                if expected_state is not None:
                    old = json.loads(path.read_text(encoding='utf-8'))
                    if old['state'] != expected_state: raise ValueError('Concurrent transition; reread')
                tmp = folder/'run.tmp'
                tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding='utf-8')
                tmp.replace(path)
        finally:
            lock.unlink()
        return folder
