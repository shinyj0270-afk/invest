"""Bounded provider adapters. No SDK login, custom endpoints or tool execution."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

# User policy: no additional API charges. No runtime/environment opt-in.
API_ENABLED = False


class ProviderError(ValueError):
    """Only fixed, non-sensitive error codes may cross this boundary."""


def settings(value):
    if not isinstance(value, dict) or set(value) != {'provider', 'model', 'timeout_seconds', 'max_output_tokens'}:
        raise ValueError('Invalid provider settings')
    if value['provider'] not in ('openai', 'anthropic'):
        raise ValueError('Unknown provider')
    if not isinstance(value['model'], str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,120}', value['model']):
        raise ValueError('Explicit model ID required')
    for name, low, high in [('timeout_seconds', 5, 120), ('max_output_tokens', 256, 8192)]:
        if type(value[name]) is not int or not low <= value[name] <= high:
            raise ValueError('Provider limit outside supported range')
    return dict(value)


def credential_name(provider):
    return {'openai': 'OPENAI_API_KEY', 'anthropic': 'ANTHROPIC_API_KEY'}[provider]


def request_payload(config, prompt):
    common = dict(model=config['model'])
    if config['provider'] == 'openai':
        common.update(input=prompt, max_output_tokens=config['max_output_tokens'], store=False,
                      text={'format': {'type': 'json_object'}})
        return 'https://api.openai.com/v1/responses', common
    common.update(messages=[{'role': 'user', 'content': prompt}], max_tokens=config['max_output_tokens'])
    return 'https://api.anthropic.com/v1/messages', common


def decode_response(provider, response):
    try:
        if provider == 'openai':
            if response['status'] != 'completed': raise ProviderError('incomplete_response')
            blocks = [b for item in response['output'] if item.get('type') == 'message' for b in item['content']]
            if any(b.get('type') == 'refusal' for b in blocks): raise ProviderError('provider_refusal')
            result = ''.join(b['text'] for b in blocks if b.get('type') == 'output_text')
        else:
            if response['stop_reason'] != 'end_turn': raise ProviderError('incomplete_response')
            result = ''.join(b['text'] for b in response['content'] if b.get('type') == 'text')
        result = json.loads(result)
        if not isinstance(result, dict): raise ProviderError('invalid_json_response')
        usage = response.get('usage', {})
        counts = {k: usage.get(k) for k in ('input_tokens', 'output_tokens')}
        if any(v is not None and (type(v) is not int or v < 0) for v in counts.values()):
            raise ProviderError('invalid_usage')
        return {'value': result, 'usage': counts, 'cost_usd': None}
    except (KeyError, TypeError, json.JSONDecodeError):
        raise ProviderError('invalid_provider_response') from None


def generate(config, prompt):
    if not API_ENABLED: raise ProviderError('api_disabled_by_project_policy')
    config = settings(config)
    if not os.environ.get(credential_name(config['provider']), '').strip():
        raise ProviderError('credential_missing')
    if len(prompt.encode('utf-8')) > 100_000: raise ProviderError('input_too_large')
    # A separate process provides a hard wall-clock limit, including DNS/TLS/read.
    # Credentials stay in the environment, never command arguments or saved jobs.
    try:
        run = subprocess.run([sys.executable, '-B', '-m', 'investment.agent_providers'],
                             input=json.dumps({'config': config, 'prompt': prompt}),
                             capture_output=True, text=True, encoding='utf-8',
                             cwd=Path(__file__).resolve().parents[1],
                             timeout=config['timeout_seconds'] + 2,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired:
        raise ProviderError('deadline_exceeded') from None
    if run.returncode: raise ProviderError('provider_worker_failed')
    try: result = json.loads(run.stdout)
    except (ValueError, TypeError): raise ProviderError('invalid_worker_response') from None
    if result.get('error'):
        code = result['error']
        if code not in {'authentication_failed', 'rate_limited', 'provider_unavailable', 'request_rejected',
                        'transport_failed', 'response_too_large', 'invalid_provider_response',
                        'incomplete_response', 'provider_refusal', 'invalid_json_response', 'invalid_usage'}:
            code = 'provider_worker_failed'
        raise ProviderError(code)
    return result


def worker():
    if not API_ENABLED: raise ProviderError('api_disabled_by_project_policy')
    import requests
    config, prompt = (lambda x: (settings(x['config']), x['prompt']))(json.load(sys.stdin))
    endpoint, payload = request_payload(config, prompt)
    secret = os.environ[credential_name(config['provider'])]
    headers = {'Content-Type': 'application/json'}
    if config['provider'] == 'openai': headers['Authorization'] = 'Bearer ' + secret
    else: headers.update({'x-api-key': secret, 'anthropic-version': '2023-06-01'})
    try:
        with requests.Session() as session:
            session.trust_env = False
            with session.post(endpoint, json=payload, headers=headers, timeout=(5, config['timeout_seconds']),
                              allow_redirects=False, stream=True) as response:
                if response.status_code != 200:
                    code = ('authentication_failed' if response.status_code in (401, 403) else
                            'rate_limited' if response.status_code == 429 else
                            'provider_unavailable' if response.status_code >= 500 else 'request_rejected')
                    raise ProviderError(code)
                body = bytearray()
                for chunk in response.iter_content(16384):
                    body.extend(chunk)
                    if len(body) > 1_000_000: raise ProviderError('response_too_large')
        return decode_response(config['provider'], json.loads(body))
    except requests.RequestException:
        raise ProviderError('transport_failed') from None
    except (ValueError, UnicodeError) as exc:
        if isinstance(exc, ProviderError): raise
        raise ProviderError('invalid_provider_response') from None


if __name__ == '__main__':
    try: answer = worker()
    except ProviderError as exc: answer = {'error': str(exc)}
    except Exception: answer = {'error': 'provider_worker_failed'}
    print(json.dumps(answer, ensure_ascii=True))
