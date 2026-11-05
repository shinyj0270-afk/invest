"""Synthetic-only decision journal checks. No real holdings, orders or account data."""
import json
import tempfile
import unittest
from pathlib import Path

from investment.research_library import Library
from investment.decision_journal import record, review, due, due_from_rows, REVIEW_TYPES, ASSESSMENTS
from tests.test_research_library import source


def decision(**changes):
    value = dict(written_on='2026-01-05', code='000001', name='Synthetic Co', market='KOSPI', kind='stock',
                 review_type='buy_review', hypothesis='Synthetic margin recovery hypothesis',
                 invalidation=['Synthetic margin falls two quarters'], source_ids=['s1'], review_on='2026-03-31')
    value.update(changes)
    return value


def outcome(**changes):
    value = dict(decision_id='d1', reviewed_on='2026-04-01', outcome='Synthetic margin recovered',
                 assessment='held', reasoning='Synthetic review reasoning')
    value.update(changes)
    return value


class DecisionJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.lib = Library(Path(self.temp.name), 'work', 'fixture')
        self.lib.source('s1', source())  # accessed_on 2026-01-02

    def tearDown(self):
        self.temp.cleanup()

    def test_labels_cover_required_review_types(self):
        self.assertEqual(set(REVIEW_TYPES), {'watch', 'buy_review', 'sell_review'})
        self.assertEqual(set(ASSESSMENTS), {'held', 'refuted', 'undecidable'})

    def test_record_is_stored_and_immutable(self):
        self.assertEqual(record(self.lib, 'd1', decision()), 1)
        self.assertEqual(self.lib.get('decision', 'd1')['hypothesis'], 'Synthetic margin recovery hypothesis')
        with self.assertRaises(ValueError):
            record(self.lib, 'd1', decision(hypothesis='Rewritten after the fact'))

    def test_required_fields_and_allowlist(self):
        for broken in (dict(review_type='order'), dict(code='12345'), dict(market='NYSE'), dict(invalidation=[]),
                       dict(source_ids=[]), dict(hypothesis=' ')):
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                record(self.lib, 'bad', decision(**broken))
        extra = decision(); extra['quantity'] = 10
        with self.assertRaises(ValueError):
            record(self.lib, 'bad', extra)

    def test_dates_must_be_point_in_time(self):
        with self.assertRaises(ValueError):  # review date must follow the writing date
            record(self.lib, 'bad', decision(review_on='2026-01-05'))
        with self.assertRaises(ValueError):  # source accessed after writing cannot support it
            record(self.lib, 'bad', decision(written_on='2026-01-01', review_on='2026-02-01'))
        with self.assertRaises(ValueError):  # writing date cannot be in the future
            record(self.lib, 'bad', decision(written_on='2999-01-01', review_on='2999-02-01'))
        with self.assertRaises(ValueError):
            record(self.lib, 'bad', decision(source_ids=['missing']))

    def test_score_snapshot_optional_and_dated(self):
        snap = dict(as_of='2026-01-04', model='synthetic quality score', values={'quality': 71.5})
        record(self.lib, 'd1', decision(score_snapshot=snap))
        self.assertEqual(self.lib.get('decision', 'd1')['score_snapshot']['values']['quality'], 71.5)
        for broken in (dict(snap, as_of='2026-01-06'), dict(snap, values={'quality': 'high'}), dict(snap, values={})):
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                record(self.lib, 'bad', decision(score_snapshot=broken))

    def test_review_links_existing_decision_and_dates(self):
        record(self.lib, 'd1', decision())
        with self.assertRaises(ValueError):
            review(self.lib, 'r0', outcome(decision_id='missing'))
        with self.assertRaises(ValueError):
            review(self.lib, 'r0', outcome(reviewed_on='2026-01-04'))
        with self.assertRaises(ValueError):
            review(self.lib, 'r0', outcome(assessment='profit'))
        self.assertEqual(review(self.lib, 'r1', outcome()), 1)
        with self.assertRaises(ValueError):
            review(self.lib, 'r1', outcome(outcome='Rewritten'))

    def test_due_lists_only_unreviewed_past_review_dates(self):
        record(self.lib, 'd1', decision(review_on='2026-02-01'))
        record(self.lib, 'd2', decision(code='000002', review_on='2026-01-20', review_type='sell_review'))
        record(self.lib, 'd3', decision(code='000003', review_on='2026-05-01', review_type='watch'))
        self.assertEqual([r['id'] for r in due(self.lib, '2026-02-01')], ['d2', 'd1'])
        self.assertEqual(due(self.lib, '2026-02-01')[0]['overdue_days'], 12)
        review(self.lib, 'r2', outcome(decision_id='d2', reviewed_on='2026-01-21'))
        self.assertEqual([r['id'] for r in due(self.lib, '2026-02-01')], ['d1'])
        self.assertEqual(due(self.lib, '2026-01-19'), [])

    def test_early_review_does_not_clear_later_due_date(self):
        record(self.lib, 'd1', decision(review_on='2026-02-01'))
        review(self.lib, 'r1', outcome(reviewed_on='2026-01-10'))
        self.assertEqual([r['id'] for r in due(self.lib, '2026-02-02')], ['d1'])

    def test_due_from_rows_ignores_other_kinds(self):
        rows = [('thesis', 't1', json.dumps(dict(review_on='2026-01-01'))),
                ('decision', 'd1', json.dumps(decision()))]
        self.assertEqual([r['id'] for r in due_from_rows(rows, '2026-04-01')], ['d1'])


if __name__ == '__main__':
    unittest.main()
