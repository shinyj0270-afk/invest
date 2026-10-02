import unittest
from investment.financial_update_policy import decide_update


def bundle(value, quarter=2):
    return {'companies':{'028260':{'reports':[dict(basis='CFS',year=2026,
        quarter=quarter,values={'revenue':value})]}}}


class FinancialUpdatePolicyTests(unittest.TestCase):
    def test_exact_threshold_and_both_directions(self):
        for value in (107,93):
            self.assertEqual(decide_update(bundle(100),bundle(value))['action'],'update')

    def test_small_revision_waits_against_applied_baseline(self):
        self.assertEqual(decide_update(bundle(100),bundle(106.99))['action'],'defer')
        self.assertEqual(decide_update(bundle(100),bundle(107.01))['action'],'update')

    def test_new_quarter_is_unconditional(self):
        self.assertEqual(decide_update(bundle(100),bundle(101,3))['action'],'update')

    def test_initial_data(self):
        self.assertEqual(decide_update(None,bundle(100))['action'],'update')

    def test_losses_use_absolute_baseline(self):
        self.assertEqual(decide_update(bundle(-100),bundle(-107))['action'],'update')
        self.assertEqual(decide_update(bundle(-100),bundle(-106))['action'],'defer')

    def test_zero_and_sign_change(self):
        self.assertEqual(decide_update(bundle(0),bundle(1))['action'],'update')
        self.assertEqual(decide_update(bundle(-1),bundle(1))['action'],'update')

    def test_unchanged(self):
        self.assertEqual(decide_update(bundle(100),bundle(100))['action'],'unchanged')

    def test_missing_account_requires_review(self):
        observed=bundle(100);observed['companies']['028260']['reports'][0]['values']={}
        self.assertEqual(decide_update(bundle(100),observed)['action'],'review')

    def test_empty_observation(self):
        self.assertEqual(decide_update(bundle(100),{})['action'],'review')
