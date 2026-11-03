import hashlib
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from investment import trial_log
from investment.pit_artifacts import ArtifactStore

NO = '20260310000001'
T1 = '2026-11-04T09:00:00+09:00'
T2 = '2026-11-05T09:00:00+09:00'


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ArtifactStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name);self.store = ArtifactStore(self.root)

    def test_first_observation_stores_the_bytes_by_hash_and_records_provenance(self):
        e = self.store.put(NO, 'cfs-main', b'<html>v1</html>', observed_at=T1, source_url='https://example.invalid/v')
        self.assertEqual((e['status'], e['sha256'], e['size'], e['rcept_no'], e['document_id']), ('first', sha(b'<html>v1</html>'), 15, NO, 'cfs-main'))
        self.assertEqual(self.store.read(e), b'<html>v1</html>')
        self.assertEqual(len(self.store.entries()), 1)

    def test_same_bytes_again_is_a_reobservation_and_changed_bytes_are_a_new_version_never_an_overwrite(self):
        a = self.store.put(NO, 'cfs-main', b'v1', observed_at=T1, source_url='u')
        again = self.store.put(NO, 'cfs-main', b'v1', observed_at=T2, source_url='u');self.assertEqual(again['status'], 'same')
        b = self.store.put(NO, 'cfs-main', b'v2', observed_at=T2, source_url='u')
        self.assertEqual((b['status'], b['changed_from']), ('changed', sha(b'v1')))
        self.assertEqual(self.store.read(a), b'v1');self.assertEqual(self.store.read(b), b'v2')            # the old bytes are still there
        self.assertEqual([e['status'] for e in self.store.versions(NO, 'cfs-main')], ['first', 'same', 'changed'])

    def test_an_expected_hash_mismatch_is_preserved_not_raised_and_not_trusted(self):
        e = self.store.put(NO, 'cfs-main', b'other', observed_at=T1, source_url='u', expected_sha256=sha(b'expected'))
        self.assertEqual((e['status'], e['expected_sha256']), ('hash_mismatch', sha(b'expected')))
        self.assertEqual(self.store.read(e), b'other')

    def test_a_failed_download_is_recorded_without_a_blob(self):
        e = self.store.record_failure(NO, 'cfs-main', reason='timeout', observed_at=T1)
        self.assertEqual((e['status'], e['reason'], e['sha256']), ('failed', 'timeout', None))
        with self.assertRaises(ValueError):self.store.read(e)

    def test_verify_detects_a_tampered_or_missing_blob(self):
        e = self.store.put(NO, 'cfs-main', b'v1', observed_at=T1, source_url='u');self.assertEqual(self.store.verify(), [])
        blob = self.root / 'blobs' / e['sha256'];blob.write_bytes(b'tampered')
        self.assertEqual([p['problem'] for p in self.store.verify()], ['blob_hash_mismatch'])
        blob.unlink();self.assertEqual([p['problem'] for p in self.store.verify()], ['blob_missing'])

    def test_invalid_identifiers_and_empty_data_are_rejected(self):
        for no, doc, data in (('123', 'a', b'x'), (NO, '../x', b'x'), (NO, '', b'x'), (NO, 'a/b', b'x'), (NO, 'a', b''), (NO, 'a', 'text')):
            with self.subTest(no=no, doc=doc), self.assertRaises(ValueError):self.store.put(no, doc, data, observed_at=T1, source_url='u')
        with self.assertRaises(ValueError):self.store.put(NO, 'a', b'x', observed_at='yesterday', source_url='u')

    def test_an_unterminated_manifest_is_refused_and_left_untouched(self):
        self.store.put(NO, 'a', b'x', observed_at=T1, source_url='u');path = self.root / 'manifest.jsonl'
        path.write_text(path.read_text(encoding='utf-8').rstrip('\n'), encoding='utf-8', newline='');before = path.read_bytes()
        with self.assertRaises(ValueError):self.store.put(NO, 'a', b'y', observed_at=T2, source_url='u')
        self.assertEqual(path.read_bytes(), before)

    def test_concurrent_writers_lose_no_rows_and_sequence_numbers_are_unique(self):
        def work(i):
            self.store.put(NO, f'doc{i}', f'data{i}'.encode(), observed_at=T1, source_url='u')
        threads = [threading.Thread(target=work, args=(i,)) for i in range(8)]
        [t.start() for t in threads];[t.join() for t in threads]
        self.assertEqual(sorted(e['seq'] for e in self.store.entries()), list(range(1, 9)))
        self.assertEqual(self.store.verify(), [])

    def test_a_stale_lock_times_out_and_writes_nothing(self):
        (self.root).mkdir(parents=True, exist_ok=True);(self.root / 'manifest.lock').write_text('stale')
        with patch.object(trial_log, 'LOCK_WAIT_SECONDS', 0.1), self.assertRaisesRegex(ValueError, '잠금'):
            self.store.put(NO, 'a', b'x', observed_at=T1, source_url='u')
        self.assertFalse((self.root / 'manifest.jsonl').exists())

    def test_the_manifest_is_valid_json_lines_with_all_fields(self):
        self.store.put(NO, 'a', b'x', observed_at=T1, source_url='u')
        row = json.loads((self.root / 'manifest.jsonl').read_text(encoding='utf-8').splitlines()[0])
        self.assertTrue({'seq', 'rcept_no', 'document_id', 'sha256', 'size', 'observed_at', 'source_url', 'status', 'expected_sha256', 'changed_from', 'reason'} <= set(row))

    def test_reading_a_tampered_blob_raises_and_an_existing_blob_is_not_rewritten(self):
        e = self.store.put(NO, 'a', b'v1', observed_at=T1, source_url='u');blob = self.root / 'blobs' / e['sha256']
        before = blob.stat().st_mtime_ns;self.store.put(NO, 'a', b'v1', observed_at=T2, source_url='u')
        self.assertEqual(blob.stat().st_mtime_ns, before)
        blob.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, '해시'):self.store.read(e)

    def test_a_manifest_with_a_sequence_gap_is_rejected(self):
        self.store.put(NO, 'a', b'x', observed_at=T1, source_url='u');self.store.put(NO, 'b', b'y', observed_at=T1, source_url='u')
        path = self.root / 'manifest.jsonl';lines = path.read_text(encoding='utf-8').splitlines()
        path.write_text(lines[1] + '\n', encoding='utf-8')                                  # first row removed: seq now starts at 2
        with self.assertRaisesRegex(ValueError, '순번'):self.store.entries()

    def test_versions_are_scoped_by_receipt_and_by_document(self):
        self.assertEqual(self.store.put(NO, 'a', b'x', observed_at=T1, source_url='u')['status'], 'first')
        self.assertEqual(self.store.put('20260311000002', 'a', b'x', observed_at=T1, source_url='u')['status'], 'first')     # same bytes, other receipt
        self.assertEqual(self.store.put(NO, 'b', b'y', observed_at=T1, source_url='u')['status'], 'first')                    # other document, same receipt
        self.assertEqual(self.store.put(NO, 'a', b'x', observed_at=T2, source_url='u')['status'], 'same')

    def test_a_changed_version_stays_unresolved_until_a_human_pins_an_observed_hash(self):
        a = self.store.put(NO, 'a', b'v1', observed_at=T1, source_url='u');self.assertFalse(self.store.state(NO, 'a')['unresolved'])
        self.store.put(NO, 'a', b'v2', observed_at=T2, source_url='u');self.assertTrue(self.store.state(NO, 'a')['unresolved'])
        self.store.put(NO, 'a', b'v2', observed_at=T2, source_url='u');self.assertTrue(self.store.state(NO, 'a')['unresolved'])   # repetition does not clear it
        with self.assertRaises(ValueError):self.store.resolve(NO, 'a', accepted_sha256=sha(b'never-seen'), observed_at=T2, reason='x')
        with self.assertRaises(ValueError):self.store.resolve(NO, 'a', accepted_sha256=a['sha256'], observed_at=T2, reason=' ')
        self.store.resolve(NO, 'a', accepted_sha256=a['sha256'], observed_at=T2, reason='원문 대조 후 v1 수용')
        st = self.store.state(NO, 'a');self.assertEqual((st['unresolved'], st['pinned_sha256']), (False, a['sha256']))
        self.store.put(NO, 'a', b'v3', observed_at=T2, source_url='u');self.assertTrue(self.store.state(NO, 'a')['unresolved'])   # a newer change reopens it

    def test_a_hash_mismatch_leaves_the_document_unresolved(self):
        self.store.put(NO, 'a', b'x', observed_at=T1, source_url='u', expected_sha256=sha(b'other'))
        self.assertTrue(self.store.state(NO, 'a')['unresolved'])
        self.store.put(NO, 'a', b'x', observed_at=T2, source_url='u');self.assertTrue(self.store.state(NO, 'a')['unresolved'])

    def test_a_corrupt_existing_blob_is_never_trusted_or_overwritten(self):
        e = self.store.put(NO, 'a', b'good', observed_at=T1, source_url='u');blob = self.root / 'blobs' / e['sha256'];blob.write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, '손상'):self.store.put('20260311000002', 'a', b'good', observed_at=T2, source_url='u')
        self.assertEqual(blob.read_bytes(), b'corrupt');self.assertEqual(len(self.store.entries()), 1)

    def test_manifest_digests_must_be_canonical_so_a_path_cannot_escape_the_blob_directory(self):
        self.store.put(NO, 'a', b'x', observed_at=T1, source_url='u');path = self.root / 'manifest.jsonl'
        row = json.loads(path.read_text(encoding='utf-8').splitlines()[0]);row['sha256'] = '../../outside'
        path.write_text(json.dumps(row) + '\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '해시'):self.store.entries()
        with self.assertRaisesRegex(ValueError, '해시'):self.store.read(dict(sha256='../../outside'))
        with self.assertRaises(ValueError):self.store.put(NO, 'b', b'y', observed_at=T1, source_url='u', expected_sha256='ABC')

    def test_concurrent_writers_of_identical_bytes_and_of_competing_versions_stay_consistent(self):
        failures = []
        def same(i):
            try:self.store.put(f'20260310{i:06d}', 'doc', b'identical-content', observed_at=T1, source_url='u')
            except Exception as exc:failures.append(repr(exc))
        threads = [threading.Thread(target=same, args=(i,)) for i in range(8)];[t.start() for t in threads];[t.join() for t in threads]
        self.assertEqual(failures, [])
        self.assertEqual(self.store.verify(), []);self.assertEqual(len(list((self.root / 'blobs').glob('.*'))), 0)          # no temporary files left
        def competing(i):
            self.store.put(NO, 'race', f'v{i}'.encode(), observed_at=T1, source_url='u')
        threads = [threading.Thread(target=competing, args=(i,)) for i in range(6)];[t.start() for t in threads];[t.join() for t in threads]
        statuses = [e['status'] for e in self.store.versions(NO, 'race')]
        self.assertEqual(statuses.count('first'), 1);self.assertEqual(statuses.count('changed'), 5)                         # classification is serialized

    def test_a_reader_never_sees_a_torn_manifest_while_writers_append(self):
        stop = [];errors = []
        def writer():
            try:
                for i in range(30):
                    self.store.put(NO, f'doc{i}', f'd{i}'.encode(), observed_at=T1, source_url='u')
            except Exception as exc:errors.append('writer: ' + str(exc))
            finally:stop.append(1)
        def reader():
            deadline = time.monotonic() + 30
            while not stop and time.monotonic() < deadline:
                try:self.store.entries()
                except ValueError as exc:errors.append(str(exc))
                time.sleep(0.002)
        t1, t2 = threading.Thread(target=writer), threading.Thread(target=reader);t2.start();t1.start();t1.join();t2.join()
        self.assertEqual(errors, []);self.assertEqual(len(self.store.entries()), 30)

    def test_after_a_pin_other_bytes_seen_again_reopen_the_document_and_the_classification_ignores_resolution_rows(self):
        a = self.store.put(NO, 'a', b'v1', observed_at=T1, source_url='u');self.store.put(NO, 'a', b'v2', observed_at=T1, source_url='u')
        self.store.resolve(NO, 'a', accepted_sha256=a['sha256'], observed_at=T2, reason='v1 수용');self.assertFalse(self.store.state(NO, 'a')['unresolved'])
        again = self.store.put(NO, 'a', b'v2', observed_at=T2, source_url='u')
        self.assertEqual(again['status'], 'same');self.assertTrue(self.store.state(NO, 'a')['unresolved'])                 # v2 is not the accepted v1
        back = self.store.put(NO, 'a', b'v1', observed_at=T2, source_url='u')
        self.assertEqual((back['status'], back['changed_from']), ('changed', sha(b'v2')))                                   # compared with the last observation, not the pin row
        self.assertFalse(self.store.state(NO, 'a')['pinned_sha256'] is None)

    def test_fetching_the_accepted_version_again_is_not_unresolved_but_any_other_bytes_are(self):
        a = self.store.put(NO, 'a', b'A', observed_at=T1, source_url='u');self.store.put(NO, 'a', b'B', observed_at=T1, source_url='u')
        self.store.resolve(NO, 'a', accepted_sha256=a['sha256'], observed_at=T2, reason='A 수용')
        self.store.put(NO, 'a', b'A', observed_at=T2, source_url='u');self.assertFalse(self.store.state(NO, 'a')['unresolved'])
        self.store.put(NO, 'a', b'B', observed_at=T2, source_url='u');self.assertTrue(self.store.state(NO, 'a')['unresolved'])
        self.store.put(NO, 'a', b'A', observed_at=T2, source_url='u');self.assertFalse(self.store.state(NO, 'a')['unresolved'])
        self.store.put(NO, 'a', b'C', observed_at=T2, source_url='u');self.assertTrue(self.store.state(NO, 'a')['unresolved'])


if __name__ == '__main__':unittest.main()
