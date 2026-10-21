import copy
import json
import tempfile
import unittest
from pathlib import Path

from investment.research_inbox import prepare, finish, search, read, write, canonical, reopen, status


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        write(self.root/'config/local.json', {'profile': 'home', 'research_drop_inbox': 'drop'})
        write(self.root/'.local/telegram-research/channels.json', {'channels': [{'key': 'c1', 'expected_id': -1001}]})
        self.receipt = self.root/'.local/telegram-research/live/c1/receipt-1.json'
        self.value = {'schema': 'telegram-live-metadata-1', 'channel_key': 'c1', 'chat_id': -1001,
                      'items': [{'published_on': '2026-01-02', 'reference': 'https://t.me/c/1/1',
                                 'content_digest': 'a'*64, 'external_urls': ['https://example.invalid/a?utm_source=x']}]}
        write(self.receipt, self.value)

    def result(self, packet):
        source = read(Path(packet['packet']))['items'][0]['source']
        return {'id': source['id'], 'outcome': 'read', 'reading_basis': 'full_text', 'title': 'Synthetic note',
                'summary': 'Demand claim reported; unverified.', 'observations': ['Article reports demand.'],
                'interpretation': 'Possible supply pressure.', 'counterpoints': ['Not a confirmed shipment.'],
                'open_questions': ['Check company filing.'], 'tags': ['semiconductors'], 'companies': [],
                'source_urls': [source['url']]}

    def test_complete_search_and_skip_processed_with_duplicate_provenance(self):
        duplicate = copy.deepcopy(self.value)
        duplicate['items'][0]['reference'] = 'https://t.me/c/1/2'
        write(self.receipt.with_name('receipt-2.json'), duplicate)
        packet = prepare(self.root)
        self.assertEqual(packet['selected'], 1)
        self.assertEqual(len(read(Path(packet['packet']))['items'][0]['source']['provenance']), 2)
        result = self.result(packet)
        self.assertEqual(finish(self.root, packet['batch_id'], [result])['stored'], 1)
        self.assertEqual(status(self.root)['counts']['read'], 1)
        self.assertEqual(prepare(self.root)['attention'], 0)
        self.assertEqual(finish(self.root, packet['batch_id'], [result])['stored'], 0)
        self.assertEqual(prepare(self.root)['selected'], 0)
        self.assertFalse(search(self.root, 'supply')[0]['human_reviewed'])
        self.assertEqual(finish(self.root, packet['batch_id'], [result])['stored'], 0)

    def test_wrong_profile_before_io(self):
        write(self.root/'config/local.json', {'profile': 'work'})
        with self.assertRaises(ValueError):
            prepare(self.root)
        self.assertFalse((self.root/'.local/research-inbox').exists())

    def test_explicit_research_revision_preserves_prior_notes(self):
        packet = prepare(self.root)
        first = self.result(packet)
        finish(self.root, packet['batch_id'], [first])
        reopen(self.root, first['id'], 'New evidence needs comparison')
        packet = prepare(self.root)
        second = self.result(packet)
        second['summary'] = 'Updated interpretation with new evidence.'
        finish(self.root, packet['batch_id'], [second])
        notes = search(self.root)
        self.assertEqual(len(notes), 2)
        self.assertEqual(sum(n['is_current'] for n in notes), 1)

    def test_source_change_refuses_stale_finish(self):
        packet = prepare(self.root)
        self.value['items'][0]['content_digest'] = 'b'*64
        write(self.receipt, self.value)
        with self.assertRaisesRegex(ValueError, 'Source changed'):
            finish(self.root, packet['batch_id'], [self.result(packet)])
        self.assertEqual(search(self.root), [])

    def test_missing_or_duplicate_results_never_mark_read(self):
        packet = prepare(self.root)
        for results in ([], [self.result(packet)]*2):
            with self.assertRaises(ValueError):
                finish(self.root, packet['batch_id'], results)
        self.assertEqual(prepare(self.root)['selected'], 1)

    def test_metadata_only_cannot_be_fabricated_into_article(self):
        self.value['items'][0]['external_urls'] = []
        write(self.receipt, self.value)
        packet = prepare(self.root)
        result = self.result(packet)
        result['source_urls'] = []
        with self.assertRaises(ValueError):
            finish(self.root, packet['batch_id'], [result])
        result.update(outcome='metadata_only', reading_basis='metadata', summary='', observations=[], interpretation='')
        self.assertEqual(finish(self.root, packet['batch_id'], [result])['stored'], 1)
        self.assertEqual(status(self.root)['counts']['metadata_only'], 1)
        self.assertEqual(prepare(self.root)['attention'], 1)

    def test_drop_hash_change_and_file_preservation(self):
        drop = self.root/'drop'
        drop.mkdir()
        file = drop/'note.txt'
        file.write_text('Synthetic document')
        packet = prepare(self.root)
        row = next(r for r in read(Path(packet['packet']))['items'] if r['source']['kind'] == 'file')
        result = self.result(packet)
        result.update(id=row['source']['id'], source_urls=[])
        file.write_text('Changed document')
        with self.assertRaises(ValueError):
            finish(self.root, packet['batch_id'], [self.result(packet), result])
        self.assertEqual(file.read_text(), 'Changed document')

    def test_sensitive_urls_remain_exceptions_and_cannot_be_read(self):
        self.value['items'][0]['external_urls'] = ['https://localhost/private?token=x']
        write(self.receipt, self.value)
        packet = prepare(self.root)
        source = read(Path(packet['packet']))['items'][0]['source']
        self.assertIsNotNone(source['problem'])
        self.assertIsNone(source['url'])
        self.assertNotIn('token=x', Path(packet['packet']).read_text())
        with self.assertRaises(ValueError):
            canonical('https://example.invalid/a?session=secret')

    def test_corrupt_ledger_is_preserved(self):
        prepare(self.root)
        path = self.root/'.local/research-inbox/index.json'
        path.write_text('{bad')
        with self.assertRaises(ValueError):
            prepare(self.root)
        self.assertEqual(path.read_text(), '{bad')


if __name__ == '__main__':
    unittest.main()
