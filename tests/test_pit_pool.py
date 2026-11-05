"""Contract for `investment/pit_pool.py`: stored documents -> PIT rows -> scores, with a fake store in a temporary folder (no network)."""
import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from investment import pit_pool
from tests.test_pit_xml import doc, balance, income, cash

SESSIONS = ['2026-03-10', '2026-03-11', '2026-03-12']


def zip_bytes(text):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('a.xml', text.encode('utf-8'))
    return buffer.getvalue()


class Store:
    def __init__(self, test):
        self.dir = tempfile.TemporaryDirectory();test.addCleanup(self.dir.cleanup)
        self.root = Path(self.dir.name)
        (self.root / 'artifacts' / 'blobs').mkdir(parents=True);(self.root / 'calendar').mkdir()
        self.lines = []

    def add(self, rcept_no, data, document_id='document-zip'):
        sha = hashlib.sha256(data).hexdigest()
        (self.root / 'artifacts' / 'blobs' / sha).write_bytes(data)
        self.lines.append(json.dumps(dict(document_id=document_id, rcept_no=rcept_no, sha256=sha)))
        (self.root / 'artifacts' / 'manifest.jsonl').write_text('\n'.join(self.lines) + '\n', encoding='utf-8')


def receipt(no='20260309000001', dt='2026-03-09', period='2025-12', correction='none'):
    return dict(rcept_no=no, rcept_dt=dt, report_nm='x', correction=correction, title_period=period)


GOOD = zip_bytes(doc(balance(), income(), cash()))


class LoadingTests(unittest.TestCase):
    def test_load_sha_keeps_only_document_zips_with_a_hash(self):
        store = Store(self);store.add('20260309000001', GOOD);store.add('20260309000002', b'x', document_id='list-page')
        self.assertEqual(set(pit_pool.load_sha(store.root)), {'20260309000001'})

    def test_load_sessions_unions_files_and_sorts_iso_dates(self):
        store = Store(self)
        (store.root / 'calendar' / 'a.json').write_text(json.dumps([{'localDate': '20260311'}, {'localDate': '20260310'}]), encoding='utf-8')
        (store.root / 'calendar' / 'b.json').write_text(json.dumps([{'localDate': '20260310'}, {'localDate': '20260312'}]), encoding='utf-8')
        self.assertEqual(pit_pool.load_sessions(store.root, ['a.json', 'b.json']), SESSIONS)


class CompanyRowsTests(unittest.TestCase):
    def test_a_stored_original_annual_report_becomes_a_row_available_after_the_filing(self):
        store = Store(self);store.add('20260309000001', GOOD)
        result = pit_pool.company_rows(store.root, '298040', [receipt()], pit_pool.load_sha(store.root), SESSIONS)
        self.assertEqual((result['parsed'], result['problems'], result['verify_ok'], len(result['rows'])), (1, [], True, 1))
        self.assertEqual(result['rows'][0]['company'], '298040')

    def test_other_periods_and_unstored_receipts_are_skipped_without_a_problem(self):
        store = Store(self);store.add('20260309000001', GOOD)
        receipts = [receipt(period='2025-06'), receipt(no='20260309000009')]
        result = pit_pool.company_rows(store.root, '298040', receipts, pit_pool.load_sha(store.root), SESSIONS)
        self.assertEqual((result['parsed'], result['problems'], result['rows']), (0, [], []))

    def test_a_correction_is_skipped_when_the_original_of_that_year_is_stored(self):
        store = Store(self);store.add('20260309000001', GOOD);store.add('20260310000002', GOOD)
        receipts = [receipt(), receipt(no='20260310000002', dt='2026-03-10', correction='기재정정')]
        result = pit_pool.company_rows(store.root, '298040', receipts, pit_pool.load_sha(store.root), SESSIONS)
        self.assertEqual((result['parsed'], len(result['rows'])), (1, 1))
        self.assertEqual(result['rows'][0]['rcept_no'], '20260309000001')

    def test_a_year_without_a_stored_original_starts_from_its_earliest_stored_correction(self):
        store = Store(self);store.add('20260311000002', GOOD);store.add('20260312000003', GOOD)
        receipts = [receipt(no='20260309000001'),                                                       # the original exists in the list but is not stored
                    receipt(no='20260312000003', dt='2026-03-12', correction='기재정정'),
                    receipt(no='20260311000002', dt='2026-03-11', correction='기재정정'),
                    receipt(no='20260310000009', dt='2026-03-10', correction='첨부추가')]                 # not stored: never used
        result = pit_pool.company_rows(store.root, '298040', receipts, pit_pool.load_sha(store.root), SESSIONS)
        self.assertEqual((result['parsed'], result['problems'], len(result['rows'])), (1, [], 1))
        self.assertEqual(result['rows'][0]['rcept_no'], '20260311000002')

    def test_an_unreadable_document_is_reported_and_the_others_still_load(self):
        store = Store(self);store.add('20260309000001', b'not a zip');store.add('20260309000002', GOOD)
        receipts = [receipt(), receipt(no='20260309000002')]
        result = pit_pool.company_rows(store.root, '298040', receipts, pit_pool.load_sha(store.root), SESSIONS)
        self.assertEqual([(p['rcept_no'], p['year']) for p in result['problems']], [('20260309000001', 2025)])
        self.assertEqual((result['parsed'], len(result['rows'])), (1, 1))


class MissingBlobTests(unittest.TestCase):
    def test_a_manifest_entry_whose_blob_is_gone_is_a_problem_not_a_crash(self):
        store = Store(self);store.add('20260309000001', GOOD)
        for blob in (store.root / 'artifacts' / 'blobs').iterdir():blob.unlink()
        result = pit_pool.company_rows(store.root, '298040', [receipt()], pit_pool.load_sha(store.root), SESSIONS)
        self.assertEqual((result['parsed'], len(result['problems'])), (0, 1))


class PoolScoresTests(unittest.TestCase):
    def test_scores_carry_names_and_the_details_are_per_code(self):
        store = Store(self);store.add('20260309000001', GOOD)
        scores, details = pit_pool.pool_scores(store.root, {'298040': ('효성중공업', [receipt()])}, SESSIONS, '2026-03-12', minimum=1)
        self.assertEqual([(s['code'], s['name']) for s in scores], [('298040', '효성중공업')])
        self.assertEqual(list(details), ['298040']);self.assertEqual(details['298040']['parsed'], 1)

    def test_a_company_whose_inventory_shows_a_newer_report_is_a_parse_failure_not_stale(self):
        store = Store(self);store.add('20260309000001', GOOD)
        newer = receipt(no='20270309000009', dt='2027-03-09', period='2026-12')
        scores, _ = pit_pool.pool_scores(store.root, {'298040': ('효성중공업', [receipt(), newer])}, SESSIONS, '2027-06-30', minimum=1)
        self.assertEqual((scores[0]['stale'], scores[0]['parse_failed'], scores[0]['reasons']['S_pit_QGCB']), (True, True, ['parse_failed']))
        scores, _ = pit_pool.pool_scores(store.root, {'298040': ('효성중공업', [receipt()])}, SESSIONS, '2027-06-30', minimum=1)
        self.assertEqual((scores[0]['stale'], scores[0]['parse_failed'], scores[0]['reasons']['S_pit_QGCB']), (True, False, ['stale_period']))

    def test_an_empty_pool_is_refused(self):
        store = Store(self);store.add('20260309000001', GOOD)
        with self.assertRaises(ValueError):
            pit_pool.pool_scores(store.root, {}, SESSIONS, '2026-03-12')


if __name__ == '__main__':unittest.main()
