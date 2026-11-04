"""Layout variants found in real annual reports of LS ELECTRIC, SK이노베이션 and 두산에너빌리티 (stored documents, 2026-11-04).

A  `-` placeholder cells: in the older layout (label, note, detail, subtotal, detail, subtotal) a zero detail cell can show `-` next to the subtotal, so a row has MORE non-empty cells than
   period columns. When removing the `-` cells makes the count equal the number of columns the row is read from the rest (original five fields and new fields alike); when the count already equals the
   number of columns nothing is removed (`-` is then a real zero), and when it still does not match the row is refused as before.
B  Tables whose TITLE names a half-year or quarter (`제 26 기 반기말 2024.06.30 현재`, `1분기말`) are not annual statements: they are skipped, they never fail the document and they are never read.
   A document with only such tables has no statements (`NoStatements`).
G  Two XML members of one document can carry the same original value rounded differently (SK이노베이션 FY2024: 315,488,339 vs 315,488,338 thousand won). Original fields of two members agree when they
   differ by at most ONE statement unit (the larger unit of the two members); the first member's value is kept. A bigger difference is still `문서 계정 값 불일치`.
C  Column heads that carry only period numbers with the 말 suffix (`제 8기말`, `제 7기`; no `(당)`/`(전)`): read like the period-number layout (consecutive, descending, equal to the title's current number).
   Whether the cells of a row are POSITIONAL (one cell per column) or GROUPED (detail + subtotal cells) is decided per table by its most common row width: width <= 1 + note + columns means positional,
   anything wider means grouped (non-empty cells must number exactly the columns; a blank current cell is then NOT a zero).
"""
import io
import unittest
import zipfile
from investment import pit_xml
from tests.test_pit_xml import doc, balance, income, cash, BS_ROWS, IS_ROWS, CF_ROWS, EXPECTED, core

N_BS = ['제 8 기 2025년 12월 31일 현재', '제 7 기 2024년 12월 31일 현재']
N_FLOW = ['제 8 기 2025년 1월 1일부터 2025년 12월 31일까지', '제 7 기 2024년 1월 1일부터 2024년 12월 31일까지']
N_BS_HEAD = ['과 목', '주석', '제 8기말', '제 7기말']
N_FLOW_HEAD = ['과 목', '주석', '제 8기', '제 7기']
HALF_LINES = ['제 26 기 반기말 2025년 6월 30일 현재', '제 25 기말 2024년 12월 31일 현재']
Q_LINES = ['제 9 기 1분기말 2025년 3월 31일 현재', '제 8 기말 2024년 12월 31일 현재']


def parse(*parts, year=2025):
    return pit_xml.parse_statements(doc(*parts), year=year)


class PlaceholderCellTests(unittest.TestCase):
    def test_a_dash_detail_cell_is_dropped_when_that_makes_the_count_fit(self):
        rows = [['Ⅰ. 매출액', '7', '-', '5,968', '', '4,894'], ['Ⅵ. 영업이익', '', '-', '746', '-', '362']]
        result = parse(balance(), income(rows=rows), cash())
        self.assertEqual(result['values']['revenue'], 5968);self.assertEqual(result['values']['operating_profit'], 746)

    def test_new_fields_use_the_same_rule(self):
        rows = IS_ROWS + [['금융비용', '', '-', '300', '', '280']]
        result = parse(balance(), income(rows=rows), cash())
        self.assertEqual((result['values']['finance_costs'], result['notes']), (300, {}))

    def test_nothing_is_dropped_when_the_count_already_fits_or_the_dash_does_not_help(self):
        result = parse(balance(), income(rows=[['Ⅰ. 매출액', '7', '-', '4,894'], ['Ⅵ. 영업이익', '', '746', '362']]), cash())
        self.assertEqual(result['values']['revenue'], 0)                                      # two cells: the current amount IS the dash (zero)
        with self.assertRaises(ValueError):
            parse(balance(), income(rows=[['Ⅰ. 매출액', '7', '-', '5,968', '', '4,894', '3,000'], ['Ⅵ. 영업이익', '', '746', '362']]), cash())
        soft = parse(balance(), income(rows=IS_ROWS + [['금융비용', '', '-', '300', '', '280', '250']]), cash())
        self.assertNotIn('finance_costs', soft['values']);self.assertEqual(soft['notes'], {'finance_costs': 'amount_count'})


class HalfYearTitleTests(unittest.TestCase):
    def test_a_half_year_or_quarter_titled_table_is_skipped_wherever_it_sits(self):
        half = balance(lines=HALF_LINES, rows=[['자산총계', '', '', '9,999', '', '8,888'], ['자본 총계', '', '', '7,777', '', '6,666']])
        quarter = balance(lines=Q_LINES, rows=[['자본 총계', '', '', '5,555', '', '4,444']])
        for parts in ((half, balance(), income(), cash()), (balance(), income(), cash(), half), (quarter, balance(), half, income(), cash())):
            result = parse(*parts)
            self.assertEqual(core(result['values']), EXPECTED)
            self.assertEqual(result['statements'], {'balance': 1, 'income': 1, 'cash': 1})

    def test_a_document_with_only_such_tables_has_no_statements(self):
        with self.assertRaises(pit_xml.NoStatements):
            parse(balance(lines=HALF_LINES), income(lines=['제 26 기 반기 2025년 1월 1일부터 2025년 6월 30일까지', '제 25 기 반기 2024년 1월 1일부터 2024년 6월 30일까지']))

    def test_annual_titles_are_not_mistaken_for_them(self):
        self.assertEqual(core(parse(balance(), income(), cash())['values']), EXPECTED)


class PeriodNumberHeadWithGroupedCellsTests(unittest.TestCase):
    def statements(self, bs_head=N_BS_HEAD, bs_lines=N_BS, flow_head=N_FLOW_HEAD, bs_rows=BS_ROWS, is_rows=IS_ROWS, cf_rows=CF_ROWS):
        return doc(balance(lines=bs_lines, head=bs_head, rows=bs_rows), income(lines=N_FLOW, head=flow_head, rows=is_rows), cash(lines=N_FLOW, head=flow_head, rows=cf_rows))

    def test_the_end_of_period_suffix_and_missing_current_marks_are_accepted(self):
        result = pit_xml.parse_statements(self.statements(), year=2025)
        self.assertEqual(core(result['values']), EXPECTED)

    def test_the_period_numbers_must_still_be_consecutive_descending_and_equal_to_the_title(self):
        for bad_head in (['과 목', '주석', '제 9기말', '제 8기말'], ['과 목', '주석', '제 8기말', '제 6기말'], ['과 목', '주석', '제 7기말', '제 8기말']):
            with self.subTest(head=bad_head), self.assertRaises(ValueError):
                pit_xml.parse_statements(self.statements(bs_head=bad_head), year=2025)

    def test_grouped_rows_follow_the_exact_count_rule_for_the_new_fields(self):
        grouped_is = [['Ⅰ. 매출액', '7', '', '5,968', '', '4,894'], ['Ⅵ. 영업이익', '', '', '746', '', '362'], ['금융비용', '', '', '300', '', '280']]
        result = pit_xml.parse_statements(self.statements(is_rows=grouped_is, bs_rows=BS_ROWS[:2] + [['단기금융상품', '5', '40', '', '30', '']] + BS_ROWS[2:]), year=2025)
        self.assertEqual((result['values']['finance_costs'], result['values']['short_term_financial_instruments']), (300, 40))
        blank_current = [grouped_is[0], grouped_is[1], ['금융비용', '', '', '', '', '280']]
        grouped = pit_xml.parse_statements(self.statements(is_rows=blank_current), year=2025)
        self.assertNotIn('finance_costs', grouped['values']);self.assertEqual(grouped['notes'], {'finance_costs': 'amount_count'})   # a blank current cell is NOT a zero here

    def test_positional_tables_keep_their_blank_is_zero_reading(self):
        from tests.test_pit_xml_wide import bs, inc, cf
        from tests.test_pit_xml_accounts import BS, IS, CF
        rows = [r if r[0] != '금융비용' else ['금융비용', '', '280', '250'] for r in IS]
        text = doc(bs(rows=BS), inc(rows=rows), cf(rows=CF))
        self.assertEqual(pit_xml.parse_statements(text, year=2025)['values']['finance_costs'], 0)

    def test_a_dash_placeholder_and_a_numbered_head_work_together(self):
        rows = [['Ⅰ. 매출액', '7', '-', '5,968', '', '4,894'], ['Ⅵ. 영업이익', '', '', '746', '', '362']]
        result = pit_xml.parse_statements(self.statements(is_rows=rows), year=2025)
        self.assertEqual((result['values']['revenue'], result['values']['operating_profit']), (5968, 746))


def zip_of(*texts):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for i, text in enumerate(texts):
            archive.writestr(f'm{i}.xml', text.encode('utf-8'))
    return buffer.getvalue()


class MemberRoundingTests(unittest.TestCase):
    def record(self, first, second, unit='(단위 : 원)'):
        def text(op):
            rows = [['Ⅰ. 매출액', '7', '5,968', '4,894'], ['Ⅵ. 영업이익', '', str(op), '362']]
            return doc(balance(unit=unit), income(unit=unit, rows=rows), cash(unit=unit))
        return pit_xml.parse_document_zip(zip_of(text(first), text(second)), receipt='20260310000001', year=2025, url='u')

    def test_a_difference_of_one_unit_is_rounding_and_the_first_member_wins(self):
        self.assertEqual(self.record(746, 747)['values']['operating_profit'], 746)
        self.assertEqual(self.record(747, 746)['values']['operating_profit'], 747)
        scaled = self.record(746, 747, unit='(단위 : 백만원)')
        self.assertEqual(scaled['values']['operating_profit'], 746_000_000)

    def test_two_units_or_more_still_disagree(self):
        for second in (748, 744):
            with self.subTest(second=second), self.assertRaises(ValueError):
                self.record(746, second)
        with self.assertRaises(ValueError):
            self.record(746, 748, unit='(단위 : 백만원)')

    def test_identical_values_are_unchanged(self):
        self.assertEqual(self.record(746, 746)['values']['operating_profit'], 746)


class SoftMemberRoundingTests(unittest.TestCase):
    def record(self, first, second, unit='(단위 : 원)'):
        def text(pretax):
            rows = [['Ⅰ. 매출액', '7', '5,968', '4,894'], ['Ⅵ. 영업이익', '', '746', '362'], ['법인세비용차감전순이익', '', str(pretax), '1']]
            return doc(balance(unit=unit), income(unit=unit, rows=rows), cash(unit=unit))
        return pit_xml.parse_document_zip(zip_of(text(first), text(second)), receipt='20260310000001', year=2025, url='u')

    def test_a_new_field_that_differs_by_one_unit_between_members_keeps_the_first_value(self):
        for first, second in ((1000, 1001), (1001, 1000)):
            with self.subTest(first=first, second=second):
                result = self.record(first, second)
                self.assertEqual(result['values']['pretax_income'], first)

    def test_two_units_or_more_stay_a_conflict_and_equal_values_are_unchanged(self):
        result = self.record(1000, 1002)
        self.assertNotIn('pretax_income', result['values'])                                  # a conflict drops the field (the record carries no notes)
        self.assertEqual(self.record(1000, 1000)['values']['pretax_income'], 1000)


if __name__ == '__main__':unittest.main()
