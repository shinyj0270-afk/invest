import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from company_finish import parse_extra

class ExtraTests(unittest.TestCase):
    def setUp(self):
        self.info = {'000001': {'name': '가상'}}
        self.fields = ['가', '나', '다']
        self.dates = ['2026-06-30', '2026-03-31']
        self.grid = [['시작', '2025-03-31', '종료', '2026-09-23', 'Data 개수', 60,
                      '주기', '분기', '정렬', 'D'], ['가상'], ['일자', *self.fields],
                     ['2026-06-30', 100, 2, 3], ['2026-03-31', 90, 1, 2]]

    def test_valid(self):
        self.assertEqual(parse_extra(self.grid, self.fields, self.info, self.dates)
                         ['000001']['2026-06-30']['가'], 100)

    def test_reject_bad_data(self):
        for r,c,v in [(0,7,'일'), (0,3,'2026-09-28'), (2,1,'다른계정'),
                      (1,0,'다른종목'), (4,0,'2026-06-30'), (3,1,None), (3,1,float('nan'))]:
            grid=copy.deepcopy(self.grid)
            grid[r][c]=v
            with self.subTest(change=(r,c,v)), self.assertRaises(ValueError):
                parse_extra(grid,self.fields,self.info,self.dates)

    def test_incomplete(self):
        with self.assertRaises(ValueError):
            parse_extra(self.grid[:-1],self.fields,self.info,self.dates)

if __name__=='__main__':
    unittest.main()
