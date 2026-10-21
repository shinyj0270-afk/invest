import json
import tempfile
import unittest
from pathlib import Path

from investment.telegram_watch import watch, receiver_lock
from tests.test_telegram_listen import channel_post


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.channel = dict(key='c1', expected_name='Synthetic channel', expected_id=-1001234567890)

    def test_cycles_dedupe_counts_privacy_and_lock_release(self):
        pages = [[channel_post()], [channel_post()]]
        reports, sleeps = [], []
        result = watch(self.root, 'home', 'TOKEN_SENTINEL', self.channel, cycles=2,
                       fetch=lambda *a: pages.pop(0), report=reports.append, sleep=sleeps.append)
        self.assertEqual(result, {'cycles': 2, 'accepted': 1})
        self.assertEqual(sleeps, [60])
        self.assertEqual(reports[1]['duplicate'], 1)
        self.assertFalse((self.root/'.local/telegram-research/receiver.lock').exists())
        for file in self.root.rglob('*.json'):
            self.assertNotIn('TOKEN_SENTINEL', file.read_text())
            self.assertNotIn('SYNTHETIC_BODY', file.read_text())

    def test_wrong_profile_has_no_io(self):
        with self.assertRaises(ValueError):
            watch(self.root, 'work', 'x', self.channel, cycles=1)
        self.assertFalse((self.root/'.local').exists())

    def test_existing_lock_preserved(self):
        with receiver_lock(self.root):
            with self.assertRaises(FileExistsError):
                watch(self.root, 'home', 'x', self.channel, cycles=1)
            self.assertTrue((self.root/'.local/telegram-research/receiver.lock').exists())

    def test_network_failure_stops_without_retry(self):
        calls = []
        def fail(*args):
            calls.append(1)
            raise OSError('network')
        with self.assertRaises(OSError):
            watch(self.root, 'home', 'x', self.channel, fetch=fail, cycles=2)
        self.assertEqual(len(calls), 1)
        self.assertFalse((self.root/'.local/telegram-research/state/c1.json').exists())
        self.assertFalse((self.root/'.local/telegram-research/receiver.lock').exists())

    def test_bad_key_and_interval_fail_before_io(self):
        for kwargs in ({'interval': 0}, {'cycles': 0}):
            with self.assertRaises(ValueError):
                watch(self.root, 'home', 'x', self.channel, **kwargs)
        with self.assertRaises(ValueError):
            watch(self.root, 'home', 'x', dict(self.channel, key='../wrong'))
        self.assertFalse((self.root/'.local').exists())


if __name__ == '__main__':
    unittest.main()
