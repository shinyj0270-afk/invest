"""Synthetic Telegram Bot API receiver tests: locked identity, no raw bodies, no network."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from investment.telegram_listen import discover, discover_checked, link_entities, poll, poll_file, reference_link


def channel_post(update_id=1, message_id=10, chat_id=-1001234567890, title='Synthetic channel',
                  text='see SYNTHETIC_BODY', date=1735732800, entities=None, edit=False, edit_date=None):
    post = dict(message_id=message_id, date=date, chat=dict(id=chat_id, title=title, type='channel'),
                text=text, entities=entities or [])
    if edit_date:
        post['edit_date'] = edit_date
    key = 'edited_channel_post' if edit else 'channel_post'
    return {'update_id': update_id, key: post}


def fake_fetch(pages):
    calls = []

    def fetch(token, method, params):
        calls.append(dict(token=token, method=method, params=dict(params)))
        return pages.pop(0)
    fetch.calls = calls
    return fetch


class LinkExtractionTests(unittest.TestCase):
    def test_utf16_offset_and_telegram_domain_excluded(self):
        text = '😀 see https://example.invalid/a and https://t.me/c/1/2'
        entities = [
            dict(type='url', offset=7, length=25),
            dict(type='url', offset=37, length=18),
        ]
        self.assertEqual(link_entities(text, entities), ['https://example.invalid/a'])

    def test_non_http_and_malformed_entities_ignored(self):
        self.assertEqual(link_entities('x', [dict(type='url', offset=0, length=1)]), [])
        self.assertEqual(link_entities('x', [dict(type='bold', offset=0, length=1)]), [])
        self.assertEqual(link_entities('x', 'not-a-list'), [])


class ReferenceLinkTests(unittest.TestCase):
    def test_strips_minus100_prefix(self):
        self.assertEqual(reference_link(-1001234567890, 5), 'https://t.me/c/1234567890/5')


class DiscoverTests(unittest.TestCase):
    def test_home_gate_precedes_fetch(self):
        def boom(token, method, params):
            raise AssertionError('fetch called despite wrong profile')
        for profile in ('work', 'unknown'):
            with self.assertRaisesRegex(ValueError, 'home'):
                discover_checked(profile, 'tok', fetch=boom)

    def test_lists_unique_chats_without_token_or_text(self):
        fetch = fake_fetch([[channel_post(chat_id=-100111, title='A'), channel_post(update_id=2, chat_id=-100111, title='A'),
                              channel_post(update_id=3, chat_id=-100222, title='B')]])
        result = discover_checked('home', 'SECRET_TOKEN', fetch=fetch)
        self.assertEqual([c['chat_id'] for c in result['channels']], [-100222, -100111])
        dumped = json.dumps(result)
        self.assertNotIn('SECRET_TOKEN', dumped)
        self.assertNotIn('SYNTHETIC_BODY', dumped)


class PollTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / 'state.json'
        self.out = Path(self.tmp.name) / 'out'
        self.channel = dict(key='c1', expected_name='Synthetic channel', expected_id=-1001234567890)
        self.now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def test_requires_locked_numeric_expected_id(self):
        bad = dict(key='c1', expected_name='X', expected_id=None)
        with self.assertRaises(ValueError):
            poll('tok', bad, self.state, self.out, fetch=fake_fetch([[]]), now=self.now)

    def test_accepts_locked_chat_rejects_others(self):
        fetch = fake_fetch([[channel_post(chat_id=-999), channel_post(update_id=2)]])
        receipt = poll('tok', self.channel, self.state, self.out, fetch=fetch, now=self.now)
        self.assertEqual(receipt['counts'], dict(received=2, accepted=1, rejected_wrong_chat=1, rejected_malformed=0, duplicate=0))
        self.assertEqual(len(receipt['items']), 1)
        self.assertEqual(receipt['items'][0]['reference'], 'https://t.me/c/1234567890/10')

    def test_no_raw_text_or_sender_in_receipt_file(self):
        fetch = fake_fetch([[channel_post()]])
        poll('tok', self.channel, self.state, self.out, fetch=fetch, now=self.now)
        files = list(self.out.glob('receipt-*.json'))
        self.assertEqual(len(files), 1)
        raw = files[0].read_text(encoding='utf-8')
        self.assertNotIn('SYNTHETIC_BODY', raw)
        self.assertNotIn('tok', raw)

    def test_offset_persists_and_dedupes_next_poll(self):
        fetch1 = fake_fetch([[channel_post(update_id=5, message_id=10)]])
        poll('tok', self.channel, self.state, self.out, fetch=fetch1, now=self.now)
        state = json.loads(self.state.read_text(encoding='utf-8'))
        self.assertEqual(state['last_update_id'], 5)
        fetch2 = fake_fetch([[]])
        poll('tok', self.channel, self.state, self.out, fetch=fetch2, now=self.now)
        self.assertEqual(fetch2.calls[0]['params']['offset'], 6)

    def test_duplicate_message_id_in_same_batch_not_double_counted(self):
        fetch = fake_fetch([[channel_post(update_id=1, message_id=10), channel_post(update_id=2, message_id=10)]])
        receipt = poll('tok', self.channel, self.state, self.out, fetch=fetch, now=self.now)
        self.assertEqual(receipt['counts']['accepted'], 1)
        self.assertEqual(receipt['counts']['duplicate'], 1)

    def test_edit_updates_even_if_message_id_seen_before(self):
        fetch1 = fake_fetch([[channel_post(update_id=1, message_id=10)]])
        poll('tok', self.channel, self.state, self.out, fetch=fetch1, now=self.now)
        fetch2 = fake_fetch([[channel_post(update_id=2, message_id=10, edit=True, edit_date=1735732900, text='changed')]])
        receipt = poll('tok', self.channel, self.state, self.out, fetch=fetch2, now=self.now)
        self.assertEqual(receipt['counts']['accepted'], 1)
        self.assertTrue(receipt['items'][0]['is_edit'])

    def test_title_mismatch_raises_and_preserves_state(self):
        fetch = fake_fetch([[channel_post(title='Different channel')]])
        with self.assertRaises(ValueError):
            poll('tok', self.channel, self.state, self.out, fetch=fetch, now=self.now)
        self.assertFalse(self.state.exists())
        self.assertFalse(self.out.exists())

    def test_malformed_updates_rejected_without_crashing(self):
        fetch = fake_fetch([[{'update_id': 1}, {'update_id': 2, 'channel_post': {'chat': {'id': -1001234567890}}}]])
        receipt = poll('tok', self.channel, self.state, self.out, fetch=fetch, now=self.now)
        self.assertEqual(receipt['counts']['rejected_malformed'], 2)
        self.assertEqual(receipt['items'], [])

    def test_no_file_written_when_nothing_accepted(self):
        fetch = fake_fetch([[channel_post(chat_id=-999)]])
        poll('tok', self.channel, self.state, self.out, fetch=fetch, now=self.now)
        self.assertFalse(self.out.exists())
        self.assertTrue(self.state.exists())

    def test_home_gate_precedes_fetch_in_poll_file(self):
        root = Path(self.tmp.name)
        channels_payload = {'channels': [self.channel]}
        (root / '.local').mkdir()
        channels_path = root / '.local/channels.json'
        channels_path.write_text(json.dumps(channels_payload), encoding='utf-8')

        def boom(token, method, params):
            raise AssertionError('fetch called despite wrong profile')
        for profile in ('work', 'unknown'):
            with self.assertRaisesRegex(ValueError, 'home'):
                poll_file(root, profile, 'tok', self.channel, '.local/state.json', '.local/out', fetch=boom, now=self.now)


if __name__ == '__main__':
    unittest.main()
