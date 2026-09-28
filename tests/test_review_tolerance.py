"""Check the user's strict KRW 100m boundary and non-finite inputs."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from infomax_review import amount_difference_accepted

class ToleranceTests(unittest.TestCase):
    def test_below_boundary(self):
        for value in (0, 1_000_000, -1_000_000, 99_999_999, -99_999_999):
            with self.subTest(value=value):
                self.assertTrue(amount_difference_accepted(value))

    def test_boundary_and_above(self):
        for value in (100_000_000, -100_000_000, 100_000_001, -100_000_001):
            with self.subTest(value=value):
                self.assertFalse(amount_difference_accepted(value))

    def test_non_finite(self):
        for value in (float('nan'), float('inf'), float('-inf')):
            with self.subTest(value=value):
                self.assertFalse(amount_difference_accepted(value))

if __name__ == '__main__':
    unittest.main()
