"""User-confirmed industry sector map: valid file loads, malformed files link nothing."""
import json, sys, tempfile, unittest
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
        bad = [{'sectors': {'반도체': '반도체와반도체장비'}, 'decided_on': 'x', 'decided_by': 'user'},
               {'sectors': {'반도체': []}, 'decided_on': 'x', 'decided_by': 'user'},
               {'sectors': {'': ['화학']}, 'decided_on': 'x', 'decided_by': 'user'},
               {'sectors': {'화학': ['화학']}}]
        with tempfile.TemporaryDirectory() as folder:
            for i, value in enumerate(bad + ['not json']):
                path = Path(folder)/f'{i}.json'
                path.write_text(value if isinstance(value, str) else json.dumps(value), encoding='utf-8')
                self.assertEqual(load_sector_map(path), dict(status='invalid', sectors={}))
            self.assertEqual(load_sector_map(Path(folder)/'missing.json')['status'], 'invalid')


if __name__ == '__main__':
    unittest.main()
