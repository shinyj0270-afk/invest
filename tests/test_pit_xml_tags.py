"""Contract for `investment/pit_xml_tags.py`: read a few accounts from the XBRL tags (`ACODE`/`ACONTEXT`) that recent DART documents carry on their value cells.

Why: some accounts (total lease liabilities, depreciation+amortisation) are only in the notes, and the notes of recent annual reports (seen from FY2025, partly FY2024) are tagged.
Real documents show that the unit attribute `ADECIMAL` is NOT reliable (a note table in thousand won tagged `ADECIMAL="0"`), so the unit is read from the `(단위 : …)` caption in front of
the table instead; the sign is taken from the displayed number and flipped when `ANEGATED="Y"` (a displayed `(19,050)` with `ANEGATED="Y"` is the positive fact 19,050).

`read_tagged(text, *, year) -> (values, notes)`; never raises for data problems. `read_tagged_detail` returns `(values, notes, units)` with the scale factor of each kept value.
In `pit_xml.parse_statements` a tag value and a statement row of one field also agree within half of the TAG unit (the statement value is kept), otherwise `conflict`.
Fields (concept, period type): lease_total ifrs-full_LeaseLiabilities (e) | lease_current ifrs-full_CurrentLeaseLiabilities (e) | lease_noncurrent ifrs-full_NoncurrentLeaseLiabilities (e) |
  short_term_financial_instruments ifrs-full_ShorttermDepositsNotClassifiedAsCashEquivalents (e) | da_total ifrs-full_DepreciationAndAmortisationExpense (d).
Only the context `CFY{year}{e|d}FY_ifrs-full_ConsolidatedAndSeparateFinancialStatementsAxis_ifrs-full_ConsolidatedMember` counts (current year, consolidated, NO further axis); `e` = instant at year end,
`d` = duration of the year, and the period type must match the concept. Prior-year, other-year, separate and dimensioned facts are ignored without a note.
Unit: the closest `(단위 : 원|천원|백만원)` caption, looked for ONLY in (1) the cell's own table before the cell (no distance limit: real tagged cells sit far inside big tables), (2) the text between the
previous table and this table, at most 2500 raw characters before this table's start, (3) the previous table when that table carries no `ACODE` tags (a statement title table). The caption of a previous table that holds tagged values is never inherited, otherwise a
captionless table would silently get a wrong unit. None or another unit -> the field is omitted with note `unit_unknown`. Several facts of one field must agree after scaling (`conflict`), where "agree" allows the rounding of the coarser table: |a - b| <= half of the larger unit factor, and the value of the SMALLER unit is kept; an unreadable number is `bad_number`; a negative value is `negative` (all five fields are >= 0).
In `pit_xml.parse_statements` the tag values are merged into `result['values']`: an absent field is added, an equal one is kept, a different one (statement row vs tag) is dropped with note `conflict`.
Tags alone never make a document: without statements `NoStatements` is still raised.
"""
import unittest
from investment import pit_xml, pit_xml_tags
from tests.test_pit_xml import doc, EXPECTED
from tests.test_pit_xml_accounts import BS, IS, CF, FULL
from tests.test_pit_xml_wide import bs, inc, cf

CONS = 'ifrs-full_ConsolidatedAndSeparateFinancialStatementsAxis_ifrs-full_ConsolidatedMember'
LEASE, CUR, NONCUR = 'ifrs-full_LeaseLiabilities', 'ifrs-full_CurrentLeaseLiabilities', 'ifrs-full_NoncurrentLeaseLiabilities'
DEPOSIT, DA = 'ifrs-full_ShorttermDepositsNotClassifiedAsCashEquivalents', 'ifrs-full_DepreciationAndAmortisationExpense'


def ctx(kind='e', year=2025, prefix='CFY', member=CONS):
    return f'{prefix}{year}{kind}FY_{member}'


def fact(code, value, context=None, neg='N', dec='0', kind='e'):
    context = context if context is not None else ctx(kind)
    return f'<TE ACODE="{code}" ACONTEXT="{context}" ADECIMAL="{dec}" ANEGATED="{neg}" ALIGN="RIGHT"><P>{value}</P></TE>'


def table(caption, *facts, gap=''):
    cells = ''.join(f'<TR><TD>항목</TD>{f}</TR>' for f in facts)
    head = f'<P>설명 문단입니다. {caption}</P>' if caption else '<P>설명 문단입니다.</P>'
    return head + gap + f'<TABLE><TBODY>{cells}</TBODY></TABLE>'


def read(*parts, year=2025):
    return pit_xml_tags.read_tagged('<DOCUMENT>' + ''.join(parts) + '</DOCUMENT>', year=year)


class ReadingTests(unittest.TestCase):
    def test_each_concept_is_read_and_scaled_by_the_caption_unit(self):
        for caption, factor in (('(단위 : 원)', 1), ('(단위 : 천원)', 1000), ('(단위: 백만원)', 1_000_000)):
            with self.subTest(caption=caption):
                values, notes = read(table(caption, fact(LEASE, '48,549'), fact(CUR, '7'), fact(NONCUR, '15'), fact(DEPOSIT, '50')),
                                     table(caption, fact(DA, '(20)', kind='d', neg='Y')))
                self.assertEqual(values, dict(lease_total=48549 * factor, lease_current=7 * factor, lease_noncurrent=15 * factor,
                                              short_term_financial_instruments=50 * factor, da_total=20 * factor))
                self.assertEqual(notes, {})

    def test_the_caption_wins_over_a_wrong_unit_attribute_and_a_missing_caption_omits_the_field(self):
        values, notes = read(table('(단위 : 천원)', fact(LEASE, '5', dec='0')))
        self.assertEqual((values, notes), ({'lease_total': 5000}, {}))
        values, notes = read(table('', fact(LEASE, '5', dec='-6')))
        self.assertEqual((values, notes), ({}, {'lease_total': 'unit_unknown'}))
        for caption in ('(단위 : 억원)', '(단위 : USD)', '(단위 : 천달러)'):
            self.assertEqual(read(table(caption, fact(LEASE, '5')))[1], {'lease_total': 'unit_unknown'})

    def test_the_closest_caption_before_the_cell_is_used_even_from_a_previous_table(self):
        first = table('(단위 : 백만원)', fact(LEASE, '1'))
        second = table('(단위 : 원)', fact(CUR, '2'))
        values, _ = read(first, second)
        self.assertEqual(values, {'lease_total': 1_000_000, 'lease_current': 2})
        title = '<TABLE><TBODY><TR><TD>연결 재무상태표</TD></TR><TR><TD>(단위 : 백만원)</TD></TR></TBODY></TABLE>'
        accounts = f'<TABLE><TBODY><TR><TD>리스부채</TD>{fact(LEASE, "3")}</TR></TBODY></TABLE>'
        self.assertEqual(read(title, accounts)[0], {'lease_total': 3_000_000})

    def test_a_captionless_table_does_not_inherit_the_unit_of_a_previous_table_with_tagged_values(self):
        values, notes = read(table('(단위 : 백만원)', fact(LEASE, '1')), table('', fact(CUR, '2')))
        self.assertEqual((values, notes), ({'lease_total': 1_000_000}, {'lease_current': 'unit_unknown'}))

    def test_a_caption_inside_the_cells_own_table_before_the_cell_counts_and_one_after_it_does_not(self):
        inside = f'<P>설명</P><TABLE><TBODY><TR><TD>(단위 : 천원)</TD></TR><TR><TD>항목</TD>{fact(LEASE, "5")}</TR></TBODY></TABLE>'
        self.assertEqual(read(inside), ({'lease_total': 5000}, {}))
        after = f'<P>설명</P><TABLE><TBODY><TR><TD>항목</TD>{fact(LEASE, "5")}</TR><TR><TD>(단위 : 천원)</TD></TR></TBODY></TABLE>'
        self.assertEqual(read(after), ({}, {'lease_total': 'unit_unknown'}))

    def test_a_previous_table_without_tags_supplies_its_caption_only_to_the_next_table(self):
        title = '<TABLE><TBODY><TR><TD>제목</TD></TR><TR><TD>(단위 : 천원)</TD></TR></TBODY></TABLE>'
        accounts = f'<TABLE><TBODY><TR><TD>항목</TD>{fact(LEASE, "5")}</TR></TBODY></TABLE>'
        later = f'<P>중간 문단</P><TABLE><TBODY><TR><TD>항목</TD>{fact(CUR, "6")}</TR></TBODY></TABLE>'
        values, notes = read(title, accounts, later)
        self.assertEqual((values, notes), ({'lease_total': 5000}, {'lease_current': 'unit_unknown'}))

    def test_the_caption_of_a_previous_table_is_not_inherited_even_when_it_sits_inside_that_tagged_table(self):
        first = f'<P>설명</P><TABLE><TBODY><TR><TD>(단위 : 천원)</TD></TR><TR><TD>항목</TD>{fact(LEASE, "5")}</TR></TBODY></TABLE>'
        second = f'<TABLE><TBODY><TR><TD>항목</TD>{fact(CUR, "6")}</TR></TBODY></TABLE>'
        self.assertEqual(read(first, second), ({'lease_total': 5000}, {'lease_current': 'unit_unknown'}))

    def test_spaces_inside_the_unit_are_ignored_and_the_closest_of_two_captions_wins(self):
        self.assertEqual(read(table('(단위 : 백만 원)', fact(LEASE, '1')))[0], {'lease_total': 1_000_000})
        two = f'<P>(단위 : 원)</P><P>그리고 (단위 : 천원)</P><TABLE><TBODY><TR><TD>항목</TD>{fact(LEASE, "5")}</TR></TBODY></TABLE>'
        self.assertEqual(read(two)[0], {'lease_total': 5000})

    def test_a_wrapper_table_holding_a_tagged_inner_table_counts_as_tagged_for_the_next_table(self):
        wrapper = (f'<TABLE><TBODY><TR><TD>(단위 : 천원)</TD></TR><TR><TD><TABLE><TBODY><TR><TD>항목</TD>{fact(LEASE, "5")}</TR></TBODY></TABLE></TD></TR></TBODY></TABLE>')
        later = f'<TABLE><TBODY><TR><TD>항목</TD>{fact(CUR, "6")}</TR></TBODY></TABLE>'
        # the inner cell does not inherit the wrapper's caption either (by design), and the wrapper's caption is not passed on to the next table because the wrapper holds a tagged value
        self.assertEqual(read(wrapper, later), ({}, {'lease_total': 'unit_unknown', 'lease_current': 'unit_unknown'}))

    def test_a_tagged_cell_outside_any_table_uses_a_caption_at_most_2500_characters_before_it(self):
        self.assertEqual(read('<P>(단위 : 천원)</P>' + fact(LEASE, '5'))[0], {'lease_total': 5000})
        self.assertEqual(read('<P>(단위 : 천원)</P><P>' + 'x' * 3000 + '</P>' + fact(LEASE, '5')), ({}, {'lease_total': 'unit_unknown'}))
        self.assertEqual(read(fact(LEASE, '5')), ({}, {'lease_total': 'unit_unknown'}))

    def test_a_caption_further_than_2500_characters_away_does_not_count(self):
        near = table('(단위 : 원)', fact(LEASE, '5'), gap='<P>' + 'x' * 2000 + '</P>')
        self.assertEqual(read(near)[0], {'lease_total': 5})
        far = table('(단위 : 원)', fact(LEASE, '5'), gap='<P>' + 'x' * 3000 + '</P>')
        self.assertEqual(read(far), ({}, {'lease_total': 'unit_unknown'}))

    def test_the_sign_follows_the_displayed_number_and_anegated(self):
        self.assertEqual(read(table('(단위 : 원)', fact(DA, '(19,050)', kind='d', neg='Y')))[0], {'da_total': 19050})
        self.assertEqual(read(table('(단위 : 원)', fact(DA, '19,050', kind='d', neg='N')))[0], {'da_total': 19050})
        for shown, neg in (('(19,050)', 'N'), ('19,050', 'Y'), ('-19,050', 'N')):
            with self.subTest(shown=shown, neg=neg):
                self.assertEqual(read(table('(단위 : 원)', fact(DA, shown, kind='d', neg=neg))), ({}, {'da_total': 'negative'}))

    def test_zero_dash_and_bad_numbers(self):
        self.assertEqual(read(table('(단위 : 원)', fact(LEASE, '0')))[0], {'lease_total': 0})
        self.assertEqual(read(table('(단위 : 원)', fact(LEASE, '-')))[0], {'lease_total': 0})
        for bad in ('12a', '1.5', '', '()', '1,2,3x'):
            with self.subTest(bad=bad):
                self.assertEqual(read(table('(단위 : 원)', fact(LEASE, bad))), ({}, {'lease_total': 'bad_number'}))

    def test_only_the_consolidated_current_year_context_without_other_axes_with_the_matching_period_type_counts(self):
        ignored = [fact(LEASE, '9', context=ctx('e', 2024, 'PFY')), fact(LEASE, '9', context=ctx('e', 2024)), fact(LEASE, '9', context=ctx('e', 2023, 'BPFY')),
                   fact(LEASE, '9', context=ctx('e', member='ifrs-full_ConsolidatedAndSeparateFinancialStatementsAxis_ifrs-full_SeparateMember')),
                   fact(LEASE, '9', context=ctx('e') + '_ifrs-full_MaturityAxis_ifrs-full_NotLaterThanOneYearMember'),
                   fact(LEASE, '9', context=ctx('d')), fact(DA, '9', context=ctx('e')), fact(LEASE, '9', context='')]
        self.assertEqual(read(table('(단위 : 원)', *ignored)), ({}, {}))
        self.assertEqual(read(table('(단위 : 원)', *ignored, fact(LEASE, '5')))[0], {'lease_total': 5})
        self.assertEqual(read(table('(단위 : 원)', fact(LEASE, '5')), year=2024), ({}, {}))

    def test_unrelated_concepts_and_untagged_cells_are_ignored(self):
        other = fact('ifrs-full_Assets', '9') + '<TE>7</TE>' + fact('ifrs-full_LeaseLiabilitiesX', '9') + fact('dart_LeaseLiabilities', '9')
        self.assertEqual(read(table('(단위 : 원)', other)), ({}, {}))
        self.assertEqual(pit_xml_tags.read_tagged('', year=2025), ({}, {}))

    def test_repeated_facts_must_agree_after_scaling(self):
        same = read(table('(단위 : 천원)', fact(LEASE, '5')), table('(단위 : 원)', fact(LEASE, '5,000')))
        self.assertEqual(same, ({'lease_total': 5000}, {}))
        diff = read(table('(단위 : 원)', fact(LEASE, '5')), table('(단위 : 원)', fact(LEASE, '6')))
        self.assertEqual(diff, ({}, {'lease_total': 'conflict'}))
        three = read(table('(단위 : 원)', fact(LEASE, '5'), fact(LEASE, '6'), fact(LEASE, '5')))
        self.assertEqual(three, ({}, {'lease_total': 'conflict'}))

    def test_a_problem_in_one_field_leaves_the_others(self):
        values, notes = read(table('(단위 : 원)', fact(LEASE, '12a'), fact(CUR, '7'), fact(NONCUR, '(3)')))
        self.assertEqual((values, notes), ({'lease_current': 7}, {'lease_total': 'bad_number', 'lease_noncurrent': 'negative'}))

    def test_the_first_problem_of_a_field_is_kept(self):
        values, notes = read(table('(단위 : 원)', fact(LEASE, '5'), fact(LEASE, '6'), fact(LEASE, '12a')))
        self.assertEqual(notes, {'lease_total': 'conflict'})


class MergeTests(unittest.TestCase):
    def parse(self, *tag_tables, bs_rows=BS):
        return pit_xml.parse_statements(doc(bs(rows=bs_rows), inc(rows=IS), cf(rows=CF), *tag_tables), year=2025)

    def test_tag_values_are_added_to_the_statement_values(self):
        rows = [r for r in BS if r[0] not in ('유동리스부채', '비유동리스부채', '단기금융상품')]
        result = self.parse(table('(단위 : 원)', fact(LEASE, '22'), fact(CUR, '7'), fact(NONCUR, '15'), fact(DEPOSIT, '50')),
                            table('(단위 : 원)', fact(DA, '(228)', kind='d', neg='Y')), bs_rows=rows)
        expected = {**FULL, 'lease_total': 22, 'da_total': 228}
        self.assertEqual(result['values'], expected);self.assertEqual(result['notes'], {})

    def test_equal_statement_and_tag_values_are_kept_and_different_ones_are_dropped(self):
        same = self.parse(table('(단위 : 원)', fact(CUR, '7'), fact(DEPOSIT, '50')))
        self.assertEqual(same['values'], FULL);self.assertEqual(same['notes'], {})
        diff = self.parse(table('(단위 : 원)', fact(CUR, '8'), fact(NONCUR, '15'), fact(DEPOSIT, '51')))
        self.assertNotIn('lease_current', diff['values']);self.assertNotIn('short_term_financial_instruments', diff['values'])
        self.assertEqual(diff['values']['lease_noncurrent'], 15)
        self.assertEqual(diff['notes'], {'lease_current': 'conflict', 'short_term_financial_instruments': 'conflict'})

    def test_tag_problems_are_reported_and_never_block_the_statement_values(self):
        result = self.parse(table('', fact(LEASE, '22')), table('(단위 : 원)', fact(DA, '12a', kind='d')))
        self.assertEqual({k: v for k, v in result['values'].items() if k in EXPECTED}, EXPECTED)
        self.assertNotIn('lease_total', result['values']);self.assertNotIn('da_total', result['values'])
        self.assertEqual(result['notes'], {'lease_total': 'unit_unknown', 'da_total': 'bad_number'})

    def test_a_note_the_statement_reading_already_made_is_not_replaced_by_a_tag_problem(self):
        rows = BS[:4] + [['단기금융상품', '51', '1', '1']] + BS[4:]            # a second 단기금융상품 row inside 유동자산: the statement reading drops the field as `duplicate`
        result = self.parse(table('', fact(DEPOSIT, '12a')), bs_rows=rows)
        self.assertNotIn('short_term_financial_instruments', result['values'])
        self.assertEqual(result['notes'], {'short_term_financial_instruments': 'duplicate'})

    def test_a_document_without_tags_is_unchanged(self):
        result = self.parse()
        self.assertEqual(result['values'], FULL);self.assertEqual(result['notes'], {})

    def test_tags_alone_do_not_make_a_document(self):
        with self.assertRaises(pit_xml.NoStatements):
            pit_xml.parse_statements(doc(table('(단위 : 원)', fact(LEASE, '22'))), year=2025)


class RoundingTests(unittest.TestCase):
    def test_the_same_amount_in_a_won_table_and_a_thousand_won_table_agrees_and_the_finer_value_is_kept(self):
        won = table('(단위 : 원)', fact(DEPOSIT, '311,797,002,761'))
        thousand = table('(단위 : 천원)', fact(DEPOSIT, '311,797,003'))
        for parts in ((won, thousand), (thousand, won)):
            values, notes = read(*parts)
            self.assertEqual((values, notes), ({'short_term_financial_instruments': 311_797_002_761}, {}))

    def test_the_tolerance_is_half_of_the_larger_unit_and_inclusive(self):
        fine = table('(단위 : 원)', fact(LEASE, '5,500'))
        self.assertEqual(read(fine, table('(단위 : 천원)', fact(LEASE, '5')))[1], {})              # |5500 - 5000| = 500
        self.assertEqual(read(table('(단위 : 원)', fact(LEASE, '5,501')), table('(단위 : 천원)', fact(LEASE, '5')))[1], {'lease_total': 'conflict'})
        self.assertEqual(read(table('(단위 : 원)', fact(LEASE, '1')), table('(단위 : 원)', fact(LEASE, '2')))[1], {'lease_total': 'conflict'})
        self.assertEqual(read(table('(단위 : 천원)', fact(LEASE, '5')), table('(단위 : 백만원)', fact(LEASE, '0')))[1], {})   # 5000 vs 0: within 500000

    def test_the_detail_function_reports_the_unit_of_the_kept_value(self):
        values, notes, units = pit_xml_tags.read_tagged_detail('<DOCUMENT>' + table('(단위 : 천원)', fact(LEASE, '5')) + table('(단위 : 원)', fact(LEASE, '5,000')) + table('(단위 : 백만원)', fact(CUR, '2')) + '</DOCUMENT>', year=2025)
        self.assertEqual((values, notes, units), ({'lease_total': 5000, 'lease_current': 2_000_000}, {}, {'lease_total': 1, 'lease_current': 1_000_000}))
        self.assertEqual(pit_xml_tags.read_tagged('<DOCUMENT>' + table('(단위 : 천원)', fact(LEASE, '5')) + '</DOCUMENT>', year=2025), ({'lease_total': 5000}, {}))

    def test_the_statement_and_tag_tolerance_is_inclusive_at_exactly_half_of_the_tag_unit(self):
        rows = [r if r[0] != '유동리스부채' else ['유동리스부채', '500', '1', '1'] for r in BS]
        edge = pit_xml.parse_statements(doc(bs(rows=rows), inc(rows=IS), cf(rows=CF), table('(단위 : 천원)', fact(CUR, '0'))), year=2025)
        self.assertEqual(edge['values']['lease_current'], 500);self.assertEqual(edge['notes'], {})
        beyond = [r if r[0] != '유동리스부채' else ['유동리스부채', '501', '1', '1'] for r in BS]
        over = pit_xml.parse_statements(doc(bs(rows=beyond), inc(rows=IS), cf(rows=CF), table('(단위 : 천원)', fact(CUR, '0'))), year=2025)
        self.assertNotIn('lease_current', over['values']);self.assertEqual(over['notes'], {'lease_current': 'conflict'})

    def test_a_statement_row_and_a_rounded_tag_agree_and_the_statement_value_is_kept(self):
        rows = [r if r[0] != '단기금융상품' else ['단기금융상품', '311,797,002,761', '1', '1'] for r in BS]
        merged = pit_xml.parse_statements(doc(bs(rows=rows), inc(rows=IS), cf(rows=CF), table('(단위 : 천원)', fact(DEPOSIT, '311,797,003'))), year=2025)
        self.assertEqual(merged['values']['short_term_financial_instruments'], 311_797_002_761);self.assertEqual(merged['notes'], {})
        off = pit_xml.parse_statements(doc(bs(rows=rows), inc(rows=IS), cf(rows=CF), table('(단위 : 천원)', fact(DEPOSIT, '311,798,000'))), year=2025)
        self.assertNotIn('short_term_financial_instruments', off['values']);self.assertEqual(off['notes'], {'short_term_financial_instruments': 'conflict'})
        lease = pit_xml.parse_statements(doc(bs(rows=BS), inc(rows=IS), cf(rows=CF), table('(단위 : 천원)', fact(CUR, '0'))), year=2025)       # statement 7 won vs tag 0: within 500
        self.assertEqual(lease['values']['lease_current'], 7);self.assertEqual(lease['notes'], {})


if __name__ == '__main__':unittest.main()
