"""Synthetic exports only: locality, date boundaries, privacy and change detection."""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from investment.telegram_export import prepare, prepare_file, local_file
from investment.research_library import Library
from investment.telegram_research import channels, batch
from tests.test_research_library import registry


def message(mid=1, when='2026-01-01T15:00:00+00:00'):
    return dict(id=mid, type='message', date='ambiguous local display',
                date_unixtime=str(int(datetime.fromisoformat(when).timestamp())),
                text='SYNTHETIC_PRIVATE_BODY', from_id='SYNTHETIC_SENDER',
                text_entities=[dict(type='text_link', text='label', href='https://example.invalid/article')])


def document():
    return dict(name='Synthetic channel', id=12345, type='private_channel', messages=[message()])


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.channel = dict(key='c1', expected_name='Synthetic channel', expected_id=12345)

    def prepare(self, value=None, **kw):
        return prepare(value or document(), self.channel, '2026-01-02', '2026-01-03', '2026-01-04', profile='home', **kw)

    def test_metadata_only_and_kst_boundary(self):
        output = self.prepare()
        self.assertEqual(output['items'][0]['published_on'], '2026-01-02')
        self.assertEqual(output['items'][0]['reference'], 'https://t.me/c/12345/1')
        self.assertEqual(output['completeness'], 'unverified')
        self.assertNotIn('SYNTHETIC_PRIVATE_BODY', json.dumps(output))
        self.assertNotIn('SYNTHETIC_SENDER', json.dumps(output))

    def test_work_gate_precedes_open(self):
        with patch('investment.telegram_export.read_json', side_effect=AssertionError('opened')):
            for profile in ('work', 'unknown'):
                with self.assertRaisesRegex(ValueError, 'home'):
                    prepare_file('.', profile, '.local/missing.json', self.channel, '2026-01-02', '2026-01-03', '2026-01-04', '.local/output.json')

    def test_media_download_setting_does_not_imply_edit(self):
        value = document()
        value['messages'][0]['photo'] = 'photos/synthetic.jpg'
        first = self.prepare(value)
        value['messages'][0]['photo'] = '(File not included. Change data exporting settings to download.)'
        second = self.prepare(value, previous=first)
        self.assertEqual(second['comparison']['changed_ids'], [])
        self.assertEqual(second['comparison']['unchanged'], 1)

    def test_wrong_chat_types_and_identity_rejected(self):
        for kind in ('personal_chat', 'private_group', 'public_supergroup', None):
            value = document(); value['type'] = kind
            with self.assertRaises(ValueError): self.prepare(value)
        for key, replacement in (('name', 'Other channel'), ('id', 999), ('id', True)):
            value = document(); value[key] = replacement
            with self.assertRaises(ValueError): self.prepare(value)

    def test_first_id_binding_is_explicitly_pending(self):
        self.channel['expected_id'] = None
        self.assertEqual(self.prepare()['identity_status'], 'name_only_review_required')

    def test_period_filter_service_and_duplicates(self):
        value = document()
        value['messages'] += [copy.deepcopy(value['messages'][0]), message(2, '2026-01-01T14:59:59+00:00'), dict(type='service', id=3)]
        output = self.prepare(value)
        self.assertEqual(output['counts'], dict(input=4, prepared=1, service=1, outside_window=1, exact_duplicates=1))

    def test_conflicting_duplicate_fails(self):
        value = document(); other = message(); other['text'] = 'Different synthetic text'
        value['messages'].append(other)
        with self.assertRaisesRegex(ValueError, 'Conflicting'): self.prepare(value)

    def test_repeat_changed_and_absent_do_not_infer_deletion(self):
        value = document(); value['messages'].append(message(2))
        prior = self.prepare(value)
        self.assertEqual(self.prepare(value, previous=prior)['comparison']['unchanged'], 2)
        value['messages'] = [message(1), message(3)]
        value['messages'][0]['text'] = 'Changed synthetic text'
        result = self.prepare(value, previous=prior)
        self.assertEqual(result['comparison']['changed_ids'], [1])
        self.assertEqual(result['comparison']['absent_ids'], [2])
        self.assertEqual(result['comparison']['new'], 1)
        self.assertEqual(result['missing'], 'unknown')

    def test_previous_other_channel_or_window_rejected(self):
        for field, value in (('chat_id', 9), ('channel_key', 'other')):
            prior = self.prepare(); prior[field] = value
            with self.assertRaises(ValueError): self.prepare(previous=prior)
        prior = self.prepare(); prior['window']['start'] = '2026-01-01'
        with self.assertRaises(ValueError): self.prepare(previous=prior)

    def test_no_timestamp_guess_and_future_edit(self):
        for value in (None, True, 'bad', '-1', 1.5):
            doc = document(); doc['messages'][0]['date_unixtime'] = value
            with self.assertRaises(ValueError): self.prepare(doc)
        doc = document(); doc['messages'][0]['edited_unixtime'] = str(int(datetime(2026, 2, 1, tzinfo=timezone.utc).timestamp()))
        with self.assertRaises(ValueError): self.prepare(doc)

    def test_sensitive_and_private_invite_links_excluded(self):
        value = document()
        value['messages'][0]['text_entities'] += [dict(type='link', text=s) for s in ('https://t.me/+PRIVATE_INVITE', 'https://example.invalid/?token=PRIVATE_TOKEN', 'http://example.invalid/a', 'https://127.0.0.1/a')]
        output = self.prepare(value)
        self.assertEqual(output['items'][0]['external_urls'], ['https://example.invalid/article'])
        self.assertNotIn('PRIVATE_INVITE', json.dumps(output))
        self.assertNotIn('PRIVATE_TOKEN', json.dumps(output))

    def test_file_preservation_and_path_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / '.local').mkdir()
            raw = json.dumps(document())
            (root / '.local/input.json').write_text(raw, encoding='utf-8')
            args = (root, 'home', '.local/input.json', self.channel, '2026-01-02', '2026-01-03', '2026-01-04', '.local/output.json')
            prepare_file(*args)
            with self.assertRaisesRegex(ValueError, 'exists'): prepare_file(*args)
            self.assertEqual((root / '.local/input.json').read_text(encoding='utf-8'), raw)
            for path in ('shared.json', '.local/../../escape.json'):
                with self.assertRaises(ValueError): local_file(root, path)

    def test_batches_reuse_existing_registry_and_dedup(self):
        value = document(); value['messages'] = [message(i) for i in range(1, 1002)]
        prepared = self.prepare(value)
        self.assertEqual([len(b['entries']) for b in prepared['batches']], [1000, 1])
        with tempfile.TemporaryDirectory() as folder:
            lib = Library(folder, 'home', 'fixture')
            channels(lib, registry())
            reports = [batch(lib, 'c1', b) for b in prepared['batches']]
            self.assertEqual(sum(r['inserted'] for r in reports), 1001)
            repeated = [batch(lib, 'c1', b) for b in prepared['batches']]
            self.assertEqual(sum(r['duplicates'] for r in repeated), 1001)


if __name__ == '__main__':
    unittest.main()
