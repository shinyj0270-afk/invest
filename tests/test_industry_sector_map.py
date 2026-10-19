"""User-confirmed industry sector map: valid file loads, malformed files link nothing."""
import json, sys, tempfile, unittest
from unittest.mock import patch
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from investment.workspace_export import load_sector_map


class SectorMapTest(unittest.TestCase):
    def test_repository_map_is_user_confirmed(self):
        result = load_sector_map()
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['decided_by'], 'user')
        self.assertEqual(result['sectors']['전력기기'], ['전기장비'])
        self.assertNotIn('KRX 금리 민감 업종', result['sectors'])

    def test_malformed_maps_fail_closed(self):
        confirmation = dict(version=1, decided_on='2026-10-19', decided_by='user')
        bad = [{**confirmation, 'sectors': sectors} for sectors in (
            {'반도체': '반도체와반도체장비'}, {'반도체': []}, {'': ['화학']}, {'화학': [None]})]
        bad.append({'version': 1, 'sectors': {'화학': ['화학']}})
        with tempfile.TemporaryDirectory() as folder:
            for i, value in enumerate(bad + ['not json']):
                path = Path(folder)/f'{i}.json'
                path.write_text(value if isinstance(value, str) else json.dumps(value), encoding='utf-8')
                self.assertEqual(load_sector_map(path), dict(status='invalid', sectors={}))
            self.assertEqual(load_sector_map(Path(folder)/'missing.json')['status'], 'invalid')

    def test_confirmation_metadata_fail_closed(self):
        valid = dict(version=1, decided_on='2026-10-19', decided_by='user', sectors={'화학': ['화학']})
        invalid = [('version', value) for value in (None, True, 1.0, '1', 2)]
        invalid += [('decided_by', value) for value in (None, '', 'agent', ['user'])]
        invalid += [('decided_on', value) for value in (None, 20261019, '2026-02-30', '2026-1-9', '20261019', '2026-10-19T00:00:00')]
        for key, value in invalid:
            with self.subTest(key=key, value=value), patch.object(Path, 'read_text', return_value=json.dumps({**valid, key: value})):
                self.assertEqual(load_sector_map(), dict(status='invalid', sectors={}))
        with patch.object(Path, 'read_text', return_value=json.dumps({**valid, 'decided_on': '2024-02-29'})):
            self.assertEqual(load_sector_map()['status'], 'ready')


if __name__ == '__main__':
    unittest.main()
