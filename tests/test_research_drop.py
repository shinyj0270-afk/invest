"""Research drop folder: list unprocessed files, record user decisions, never move or delete files."""
import hashlib, json, sys, tempfile, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from investment.research_drop import status, record


class ResearchDropTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        (self.root/'config').mkdir()
        self.inbox = self.root/'drop'
        self.config(dict(profile='work', research_drop_inbox='drop'))

    def tearDown(self): self.temp.cleanup()

    def config(self, value):
        (self.root/'config/local.json').write_text(json.dumps(value), encoding='utf-8')

    def put(self, name, body):
        self.inbox.mkdir(exist_ok=True); path = self.inbox/name; path.write_bytes(body.encode('utf-8')); return hashlib.sha256(body.encode('utf-8')).hexdigest()

    def test_status_creates_folder_and_lists_only_stable_top_level_files(self):
        result = status(self.root)
        self.assertTrue(self.inbox.is_dir()); self.assertEqual(result['pending'], [])
        sha = self.put('idea.md', '# idea')
        for name in ('half.crdownload', 'half.part', 'x.tmp', 'link.lnk', '.hidden', '~$draft.docx'): self.put(name, name)
        (self.inbox/'sub').mkdir(); (self.inbox/'sub'/'deep.md').write_text('x', encoding='utf-8')
        result = status(self.root)
        self.assertEqual([(p['name'], p['sha256']) for p in result['pending']], [('idea.md', sha)])
        self.assertEqual(result['profile'], 'work'); self.assertEqual(result['folder'], str(self.inbox.resolve()))

    def test_record_keeps_file_and_hides_same_content_after_rename(self):
        sha = self.put('idea.md', '# idea'); before = (self.inbox/'idea.md').read_bytes()
        record(self.root, sha, 'library', note='산업 가설로 등록', decided_on='2026-10-19')
        self.assertEqual((self.inbox/'idea.md').read_bytes(), before)
        self.assertEqual(status(self.root)['pending'], [])
        (self.inbox/'idea.md').rename(self.inbox/'renamed.md')
        result = status(self.root)
        self.assertEqual(result['pending'], []); self.assertEqual(result['decided'], 1)
        ledger = json.loads((self.root/'.local/research-drop/work/ledger.json').read_text(encoding='utf-8'))
        self.assertEqual(ledger['files'][sha]['decision'], 'library'); self.assertEqual(ledger['files'][sha]['name'], 'idea.md')
        # Changed content is a new item even with the same file name.
        self.put('renamed.md', '# idea v2'); self.assertEqual(len(status(self.root)['pending']), 1)

    def test_invalid_records_and_profiles_are_rejected(self):
        sha = self.put('idea.md', '# idea')
        for args in ((sha, 'publish'), ('0'*64, 'library'), (sha, 'library', '2026-02-30')):
            with self.assertRaises(ValueError): record(self.root, *args[:2], decided_on=args[2] if len(args) > 2 else '2026-10-19')
        self.assertFalse((self.root/'.local/research-drop/work/ledger.json').exists())
        self.config(dict(profile='unknown', research_drop_inbox='drop'))
        with self.assertRaises(ValueError): status(self.root)

    def test_large_files_are_listed_without_reading(self):
        self.put('big.pdf', 'x'); (self.inbox/'big.pdf').write_bytes(b'x'*(50*1024*1024+1))
        item = status(self.root)['pending'][0]
        self.assertEqual(item['name'], 'big.pdf'); self.assertIsNone(item['sha256']); self.assertEqual(item['status'], 'too_large')


if __name__ == '__main__':
    unittest.main()
