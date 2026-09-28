import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from infomax_review import parse_marketcap_history

class MarketCapHistoryTests(unittest.TestCase):
    def setUp(self):
        self.info = {'005930': {'name': '샘플'}}
        self.dates = ['2026-09-22', '2026-09-23']
        self.grid = [
            ['시작', '2026-09-01', '종료', '2026-09-23', 'Data 개수', 2,
             '주기', '일', '정렬', 'D', '영업일', 0, '시세산출', '종가'],
            ['샘플', None], ['일자', '시가총액'],
            ['2026-09-23', 250000000], ['2026-09-22', 200000000]]

    def test_valid_won_values(self):
        self.assertEqual(parse_marketcap_history(self.grid, self.info, self.dates),
                         {'005930': {'2026-09-23': 250000000, '2026-09-22': 200000000}})

    def test_reject_bad_observations(self):
        for r, c, value in [(0, 3, '2026-09-28'), (0, 7, '분기'), (2, 1, '현재가'),
                            (1, 0, '다른종목'), (4, 0, '2026-09-23'), (3, 1, None),
                            (3, 1, -1), (3, 1, float('inf'))]:
            grid = copy.deepcopy(self.grid)
            grid[r][c] = value
            with self.subTest(change=(r, c, value)), self.assertRaises(ValueError):
                parse_marketcap_history(grid, self.info, self.dates)

    def test_reject_incomplete_dates(self):
        with self.assertRaises(ValueError):
            parse_marketcap_history(self.grid[:-1], self.info, self.dates)

if __name__ == '__main__':
    unittest.main()
