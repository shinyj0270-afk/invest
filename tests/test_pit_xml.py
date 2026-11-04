"""Contract for `investment/pit_xml.py`: read consolidated annual statements out of a stored DART `document.xml` (not well-formed XML).

Layout facts come from a real specimen (효성중공업 FY2025): a TITLE table (first row = one cell holding the statement name, often with spaces
between characters; later rows hold the period lines and a "(단위 : 원)" cell) is directly followed by an ACCOUNT table whose header row is
`과목 | 주석 | 당기 | 전기`, while body rows carry extra empty cells (sub-item amounts and subtotals sit in different columns).
"""
import hashlib
import io
import os
import unittest
import zipfile
from pathlib import Path
from investment import pit_xml
from investment.pit_values import map_record


def cell(text, attrs=''):
    return f'<TD {attrs}>{text}</TD>'


def title_table(title, lines, unit='(단위 : 원)', company='효성중공업 주식회사와 그 종속기업'):
    rows = [f'<TR><TD COLSPAN="2" ALIGN="CENTER">{title}</TD></TR>'] + [f'<TR><TD COLSPAN="2">{line}</TD></TR>' for line in lines]
    rows.append(f'<TR><TD>{company}</TD><TD>{unit}</TD></TR>' if unit is not None else f'<TR><TD>{company}</TD><TD></TD></TR>')
    return '<TABLE WIDTH="876" BORDER="0"><COLGROUP><COL WIDTH="600"/><COL WIDTH="276"/></COLGROUP><TBODY>' + ''.join(rows) + '</TBODY></TABLE>'


def account_table(header, rows):
    body = ''.join('<TR>' + ''.join(cell(c, 'ALIGN="RIGHT"') for c in row) + '</TR>' for row in [header] + rows)
    return '<TABLE WIDTH="876"><TBODY>' + body + '</TBODY></TABLE>'


BS_LINES = ['제8(당)기 2025년 12월 31일 현재', '제7(전)기 2024년 12월 31일 현재']
FLOW_LINES = ['제8(당)기 2025년 1월 1일부터 2025년 12월 31일까지', '제7(전)기 2024년 1월 1일부터 2024년 12월 31일까지']
BS_ROWS = [['자산', '', '', '', '', ''], ['Ⅰ. 유동자산', '', '', '3,738', '', '3,036'], ['현금및현금성자산', '5,9,10', '216', '', '249', ''],
           ['순확정급여자산', '25', '27', '', '-', ''], ['자산총계', '', '', '7,227', '', '6,218'],
           ['부채 총계', '', '', '4,738', '', '4,163'], ['자본금', '29', '46', '', '46', ''],
           ['자본 총계', '', '', '2,489', '', '2,055'], ['부채와자본총계', '', '', '7,227', '', '6,218']]
IS_ROWS = [['Ⅰ. 매출액', '7,8,22', '5,968', '4,894'], ['Ⅱ. 매출원가', '32', '4,715', '4,103'], ['Ⅵ. 영업이익', '', '746', '362'],
           ['Ⅸ. 금융수익', '9,22,36', '474', '528'], ['XIV. 당기순이익', '', '502', '222']]
CF_ROWS = [['Ⅰ.영업활동으로 인한 현금흐름', '', '', '493', '', '412'], ['영업으로부터 창출된 현금흐름', '38', '662', '', '481', ''],
           ['Ⅵ.기초 현금및현금성자산', '', '', '249', '', '277'], ['Ⅶ.기말 현금및현금성자산', '', '', '216', '', '249']]
BS_HEAD = ['과 목', '주석', '제 8(당) 기말', '제 7(전) 기말']
FLOW_HEAD = ['과 목', '주석', '제 8(당) 기', '제 7(전) 기']


def balance(title='연 결 재 무 상 태 표', lines=BS_LINES, unit='(단위 : 원)', head=BS_HEAD, rows=BS_ROWS):
    return title_table(title, lines, unit) + account_table(head, rows)


def income(title='연 결 손 익 계 산 서', lines=FLOW_LINES, unit='(단위 : 원)', head=FLOW_HEAD, rows=IS_ROWS):
    return title_table(title, lines, unit) + account_table(head, rows)


def cash(title='연 결 현 금 흐 름 표', lines=FLOW_LINES, unit='(단위 : 원)', head=FLOW_HEAD, rows=CF_ROWS):
    return title_table(title, lines, unit) + account_table(head, rows)


def doc(*parts, prefix='<DOCUMENT><BODY>', suffix='</BODY></DOCUMENT>'):
    return prefix + '<P>감사의견</P>' + ''.join(parts) + suffix


FULL = doc(balance(), income(), cash())
EXPECTED = dict(revenue=5968, operating_profit=746, ocf=493, equity=2489, cash=216)


def core(values):
    """The five original fields only: later account additions (see test_pit_xml_accounts) are checked there."""
    return {key: value for key, value in values.items() if key in EXPECTED}


class StatementReadingTests(unittest.TestCase):
    def test_the_four_values_are_read_from_the_current_column_of_consolidated_statements(self):
        result = pit_xml.parse_statements(FULL, year=2025)
        self.assertEqual(core(result['values']), EXPECTED)
        self.assertEqual((result['basis'], result['currency'], result['unit']), ('CFS', 'KRW', 1))
        self.assertEqual((result['period_start'], result['period_end']), ('2025-01-01', '2025-12-31'))

    def test_a_million_or_thousand_won_unit_is_scaled_and_other_units_are_refused(self):
        million = doc(balance(unit='(단위 : 백만원)'), income(unit='(단위: 백만원)'), cash(unit='(단위 : 백만원)'))
        self.assertEqual(pit_xml.parse_statements(million, year=2025)['values']['revenue'], 5968 * 1_000_000)
        thousand = doc(balance(unit='(단위 : 천원)'), income(unit='(단위 : 천원)'), cash(unit='(단위 : 천원)'))
        self.assertEqual(pit_xml.parse_statements(thousand, year=2025)['values']['equity'], 2489 * 1000)
        for bad in ('(단위 : 억원)', '(단위 : USD)', '(단위 : 천달러)', None):
            with self.subTest(unit=bad), self.assertRaises(ValueError):
                pit_xml.parse_statements(doc(balance(unit=bad), income(), cash()), year=2025)

    def test_mixed_units_across_statements_are_each_applied_to_their_own_statement(self):
        mixed = doc(balance(unit='(단위 : 백만원)'), income(), cash())
        values = pit_xml.parse_statements(mixed, year=2025)['values']
        self.assertEqual((values['equity'], values['cash'], values['revenue']), (2489_000_000, 216_000_000, 5968))

    def test_number_notations(self):
        rows = [['Ⅰ. 매출액', '', '(1,000)', '5'], ['Ⅵ. 영업이익', '', '-', '5'], ['XIV. 당기순이익', '', '△2,500', '5']]
        text = doc(balance(), income(rows=rows), cash())
        values = pit_xml.parse_statements(text, year=2025)['values']
        self.assertEqual((values['revenue'], values['operating_profit']), (-1000, 0))
        rows = [['Ⅰ. 매출액', '', '-7', '5'], ['Ⅵ. 영업이익', '', '▲8', '5']]
        values = pit_xml.parse_statements(doc(balance(), income(rows=rows), cash()), year=2025)['values']
        self.assertEqual((values['revenue'], values['operating_profit']), (-7, -8))
        for bad in ('12a', '1,2,3x', '１２', '1.5e3', '0x10', '--5', '()', '(5'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pit_xml.parse_statements(doc(balance(), income(rows=[['Ⅰ. 매출액', '', bad, '5'], ['Ⅵ. 영업이익', '', '1', '1']]), cash()), year=2025)

    def test_the_note_column_is_never_read_as_an_amount_and_a_table_without_note_column_works(self):
        rows = [['Ⅰ. 매출액', '7,8,22', '', '5,968', '4,894'], ['Ⅵ. 영업이익', '', '', '746', '362']]
        text = doc(balance(), income(rows=rows), cash())
        self.assertEqual(pit_xml.parse_statements(text, year=2025)['values']['revenue'], 5968)
        head = ['과 목', '제 8(당) 기', '제 7(전) 기']
        plain = doc(balance(), income(head=head, rows=[['Ⅰ. 매출액', '5,968', '4,894'], ['Ⅵ. 영업이익', '746', '362']]), cash())
        values = pit_xml.parse_statements(plain, year=2025)['values']
        self.assertEqual((values['revenue'], values['operating_profit']), (5968, 746))

    def test_an_amount_row_must_hold_exactly_two_amounts_for_a_wanted_account(self):
        for row in (['Ⅰ. 매출액', '', '5,968', '', ''], ['Ⅰ. 매출액', '', '5,968', '4,894', '3,000']):
            with self.subTest(row=row), self.assertRaises(ValueError):
                pit_xml.parse_statements(doc(balance(), income(rows=[row, ['Ⅵ. 영업이익', '', '1', '1']]), cash()), year=2025)
        # an unwanted row with a strange shape or a non-numeric cell does not matter
        odd = [['Ⅰ. 매출액', '', '5,968', '4,894'], ['Ⅵ. 영업이익', '', '1', '1'], ['기본주당이익', '', 'n/a', '1', '2', '3']]
        self.assertEqual(pit_xml.parse_statements(doc(balance(), income(rows=odd), cash()), year=2025)['values']['revenue'], 5968)

    def test_only_consolidated_titles_directly_followed_by_an_account_table_count(self):
        separate = doc(balance(title='재 무 상 태 표'), income(title='손 익 계 산 서'), cash(title='현 금 흐 름 표'))
        with self.assertRaises(pit_xml.NoStatements):
            pit_xml.parse_statements(separate, year=2025)
        toc = '<TABLE><TR><TD>ㆍ연 결 재 무 상 태 표</TD><TD>......</TD></TR></TABLE><P>연결재무상태표의 현금및현금성자산과의 차액</P>'
        self.assertNotIn('equity', pit_xml.parse_statements(doc(toc, income(), cash()), year=2025)['values'])       # a TOC/prose mention is no balance sheet title
        with self.assertRaises(pit_xml.NoStatements):
            pit_xml.parse_statements(doc(toc), year=2025)
        no_follower = doc(title_table('연 결 재 무 상 태 표', BS_LINES), '<P>text</P>', balance_rows_not_a_table_marker(), income(), cash())
        result = pit_xml.parse_statements(no_follower, year=2025)
        self.assertNotIn('equity', result['values'])

    def test_input_that_is_not_well_formed_xml_is_still_read(self):
        messy = FULL.replace('감사의견', 'HYOSUNG T&D INDIA & 감사의견 <b>').replace('</TBODY>', '', 1).replace('</TR>', '', 2)
        messy = messy.replace('<TABLE', '<table', 1).replace('<TD ALIGN', '<td align', 3)
        result = pit_xml.parse_statements(messy, year=2025)
        self.assertEqual(result['values']['equity'], 2489)
        unclosed = '<DOCUMENT>' + balance().replace('</TD></TR>', '<TR>', 0) + income() + cash()
        self.assertEqual(pit_xml.parse_statements(unclosed, year=2025)['values']['revenue'], 5968)

    def test_a_row_or_cell_start_tag_closes_the_previous_unclosed_one(self):
        compact = ('<TABLE><TR><TD>연 결 손 익 계 산 서<TR><TD>제8(당)기 2025년 1월 1일부터 2025년 12월 31일까지<TR><TD>제7(전)기 2024년 1월 1일부터 2024년 12월 31일까지'
                   '<TR><TD>회사<TD>(단위 : 원)</TABLE>'
                   '<TABLE><TR><TD>과 목<TD>주석<TD>제 8(당) 기<TD>제 7(전) 기<TR><TD>Ⅰ. 매출액<TD>7<TD>5,968<TD>4,894<TR><TD>Ⅵ. 영업이익<TD><TD>746<TD>362</TABLE>')
        values = pit_xml.parse_statements(doc(compact), year=2025)['values']
        self.assertEqual(values, dict(revenue=5968, operating_profit=746))

    def test_account_names_ignore_spaces_and_numeral_prefixes_and_known_aliases_match(self):
        rows = [['Ⅰ. 수 익 (매출액)', '', '5', '4'], ['XIII. 영업 이익', '', '6', '3']]
        values = pit_xml.parse_statements(doc(balance(), income(rows=rows), cash(rows=[['Ⅰ.영업활동으로인한 순현금흐름', '', '9', '8']])), year=2025)['values']
        self.assertEqual((values['revenue'], values['operating_profit'], values['ocf']), (5, 6, 9))
        for label, key in (('영업수익', 'revenue'), ('매출', 'revenue'), ('영업이익(손실)', 'operating_profit'), ('영업활동현금흐름', 'ocf'),
                           ('영업활동으로 인한 현금흐름', 'ocf'), ('영업활동 순현금흐름', 'ocf')):
            with self.subTest(label=label):
                if key == 'ocf':
                    text = doc(balance(), income(), cash(rows=[[label, '', '9', '8']]))
                else:
                    text = doc(balance(), income(rows=[[label, '', '5', '4']] + [r for r in IS_ROWS if r[0] not in ('Ⅰ. 매출액', 'Ⅵ. 영업이익')] + ([['Ⅵ. 영업이익', '', '6', '3']] if key == 'revenue' else [['Ⅰ. 매출액', '', '7', '4']])), cash())
                self.assertIn(key, pit_xml.parse_statements(text, year=2025)['values'])

    def test_look_alike_accounts_are_not_taken(self):
        income_rows = [['Ⅱ. 매출원가', '', '1', '1'], ['Ⅲ. 매출총이익', '', '2', '2'], ['Ⅸ. 금융수익', '', '3', '3'], ['Ⅶ. 기타수익', '', '4', '4'],
                       ['영업이익률', '', '5', '5'], ['Ⅳ. 판매비와관리비', '', '6', '6']]
        bs_rows = [['자본금', '', '1', '1'], ['부채와자본총계', '', '2', '2'], ['자산총액', '', '3', '3'], ['장기금융자산', '', '4', '4'], ['단기현금및현금성자산', '', '5', '5']]
        cf_rows = [['Ⅵ.기초 현금및현금성자산', '', '1', '1'], ['Ⅶ.기말 현금및현금성자산', '', '2', '2'], ['Ⅱ.투자활동으로 인한 현금흐름', '', '3', '3']]
        with self.assertRaises(ValueError):
            pit_xml.parse_statements(doc(balance(rows=bs_rows), income(rows=income_rows), cash(rows=cf_rows)), year=2025)   # nothing usable at all
        text = doc(balance(rows=bs_rows), income(rows=income_rows + [['Ⅰ. 매출액', '', '9', '9']]), cash(rows=cf_rows))
        self.assertEqual(pit_xml.parse_statements(text, year=2025)['values'], dict(revenue=9))

    def test_cash_comes_from_the_balance_sheet_only(self):
        values = pit_xml.parse_statements(doc(income(), cash()), year=2025)['values']
        self.assertNotIn('cash', values);self.assertEqual(values['ocf'], 493)

    def test_two_matching_rows_in_one_statement_are_refused(self):
        rows = IS_ROWS + [['Ⅵ. 영업이익', '', '9', '9']]
        with self.assertRaises(ValueError):
            pit_xml.parse_statements(doc(balance(), income(rows=rows), cash()), year=2025)
        rows = BS_ROWS + [['자본총계', '', '9', '9', '9', '9']]
        with self.assertRaises(ValueError):
            pit_xml.parse_statements(doc(balance(rows=rows), income(), cash()), year=2025)

    def test_a_comprehensive_income_statement_is_used_only_when_no_income_statement_exists(self):
        only = doc(balance(), income(title='연 결 포 괄 손 익 계 산 서'), cash())
        self.assertEqual(pit_xml.parse_statements(only, year=2025)['values']['revenue'], 5968)
        other = [['Ⅰ. 당기순이익', '', '502', '222'], ['Ⅵ. 영업이익', '', '1', '1'], ['Ⅰ. 매출액', '', '2', '2']]
        both = doc(balance(), income(), income(title='연 결 포 괄 손 익 계 산 서', rows=other), cash())
        self.assertEqual(pit_xml.parse_statements(both, year=2025)['values']['revenue'], 5968)
        self.assertEqual(pit_xml.parse_statements(both, year=2025)['values']['operating_profit'], 746)

    def test_repeated_copies_of_a_statement_must_agree(self):
        same = doc(balance(), income(), cash(), '<P>주석</P>', balance(), income(), cash())
        self.assertEqual(core(pit_xml.parse_statements(same, year=2025)['values']), EXPECTED)
        other_rows = [row[:] for row in IS_ROWS];other_rows[0][2] = '5,969'
        with self.assertRaises(ValueError):
            pit_xml.parse_statements(doc(balance(), income(), cash(), income(rows=other_rows)), year=2025)

    def test_the_period_lines_must_match_the_requested_calendar_year(self):
        for text in (doc(balance(lines=['제8(당)기 2024년 12월 31일 현재', '제7(전)기 2023년 12월 31일 현재']), income(), cash()),
                     doc(balance(), income(lines=['제8(당)기 2025년 1월 1일부터 2025년 6월 30일까지', '제7(전)기 2024년 1월 1일부터 2024년 6월 30일까지']), cash()),
                     doc(balance(lines=['제8(당)기 2025년 3월 31일 현재', '제7(전)기 2024년 12월 31일 현재']), income(), cash()),
                     doc(balance(), income(lines=['제8(당)기 2025년 4월 1일부터 2026년 3월 31일까지', '제7(전)기 2024년 4월 1일부터 2025년 3월 31일까지']), cash()),
                     doc(balance(lines=[]), income(), cash())):
            with self.subTest(), self.assertRaises(ValueError):
                pit_xml.parse_statements(text, year=2025)
        with self.assertRaises(ValueError):
            pit_xml.parse_statements(FULL, year=2024)
        for bad in (True, '2025', 2025.0, 1899, 2200):
            with self.subTest(year=bad), self.assertRaises(ValueError):
                pit_xml.parse_statements(FULL, year=bad)

    def test_the_period_is_read_from_the_current_period_line_not_the_prior_one(self):
        swapped = ['제7(전)기 2024년 12월 31일 현재', '제8(당)기 2025년 12월 31일 현재']          # order of lines does not matter, the (당) line does
        self.assertEqual(pit_xml.parse_statements(doc(balance(lines=swapped), income(), cash()), year=2025)['values']['equity'], 2489)
        only_prior = ['제7(전)기 2024년 12월 31일 현재', '2025년 12월 31일']
        with self.assertRaises(ValueError):
            pit_xml.parse_statements(doc(balance(lines=only_prior), income(), cash()), year=2025)

    def test_the_column_header_must_show_one_current_and_one_prior_amount_column(self):
        for head in (['과 목', '주석', '제 8(당) 기말'], ['과 목', '주석', '제 7(전) 기말', '제 8(당) 기말'], ['과 목', '주석', '제 8(당) 기말', '제 7(전) 기말', '제 6(전전) 기말'],
                     ['과 목', '주석', '2025', '2024']):
            with self.subTest(head=head), self.assertRaises(ValueError):
                pit_xml.parse_statements(doc(balance(head=head), income(), cash()), year=2025)

    def test_a_title_followed_by_a_table_without_the_account_header_is_ignored(self):
        with self.assertRaises(pit_xml.NoStatements):
            pit_xml.parse_statements(doc(balance(head=['항 목', '주석', '제 8(당) 기말', '제 7(전) 기말'])), year=2025)

    def test_missing_statements_leave_their_fields_out_and_nothing_found_is_a_clear_error(self):
        values = pit_xml.parse_statements(doc(balance(), income()), year=2025)['values']
        self.assertEqual(core(values), dict(revenue=5968, operating_profit=746, equity=2489, cash=216))
        self.assertNotIn('balance_debt', values)
        with self.assertRaises(pit_xml.NoStatements):
            pit_xml.parse_statements('<DOCUMENT><P>감사보고서</P></DOCUMENT>', year=2025)
        self.assertTrue(issubclass(pit_xml.NoStatements, ValueError))

    def test_inputs_of_the_wrong_type_are_refused(self):
        for bad in (None, b'<TABLE>', 5, ''):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                pit_xml.parse_statements(bad, year=2025)

    def test_the_result_does_not_depend_on_the_order_or_the_surroundings(self):
        shuffled = doc(cash(), '<P>x & y</P>', income(), balance())
        self.assertEqual(core(pit_xml.parse_statements(shuffled, year=2025)['values']), EXPECTED)

    def test_a_table_nested_inside_a_cell_does_not_hide_or_replace_the_outer_statement(self):
        nested = '<TABLE><TR><TD><TABLE><TR><TD>안쪽</TD></TR></TABLE></TD></TR></TABLE>'
        self.assertEqual(core(pit_xml.parse_statements(doc(nested, balance(), income(), cash()), year=2025)['values']), EXPECTED)


class SurvivorTests(unittest.TestCase):
    def test_a_wanted_label_on_a_heading_row_without_amounts_is_skipped(self):
        rows = [['Ⅰ. 매출액', '', '', ''], ['Ⅵ. 영업이익', '', '746', '362']]
        self.assertEqual(pit_xml.parse_statements(doc(balance(), income(rows=rows), cash()), year=2025)['values'].get('revenue'), None)

    def test_a_flow_statement_must_start_on_january_first(self):
        lines = ['제8(당)기 2025년 7월 1일부터 2025년 12월 31일까지', '제7(전)기 2024년 7월 1일부터 2024년 12월 31일까지']
        with self.assertRaises(ValueError):
            pit_xml.parse_statements(doc(balance(), income(lines=lines), cash()), year=2025)

    def test_the_year_in_a_date_must_not_be_the_tail_of_a_longer_number(self):
        with self.assertRaises(ValueError):
            pit_xml.parse_statements(doc(balance(lines=['제8(당)기 12025년 12월 31일 현재', '제7(전)기 2024년 12월 31일 현재']), income(), cash()), year=2025)

    def test_a_title_row_with_more_than_one_cell_is_not_a_title(self):
        two = balance().replace('<TD COLSPAN="2" ALIGN="CENTER">연 결 재 무 상 태 표</TD>', '<TD>연 결 재 무 상 태 표</TD><TD>x</TD>', 1)
        self.assertNotIn('equity', pit_xml.parse_statements(doc(two, income(), cash()), year=2025)['values'])

    def test_only_one_numeral_prefix_is_stripped(self):
        rows = [['Ⅰ.Ⅱ. 매출액', '', '9', '9'], ['Ⅵ. 영업이익', '', '1', '1']]
        self.assertNotIn('revenue', pit_xml.parse_statements(doc(balance(), income(rows=rows), cash()), year=2025)['values'])

    def test_a_table_inside_an_amount_cell_does_not_split_the_row(self):
        rows = [['Ⅰ. 매출액', '', '5,968<TABLE><TR><TD></TD></TR></TABLE>', '4,894'], ['Ⅵ. 영업이익', '', '746', '362']]
        body = ''.join('<TR>' + ''.join(f'<TD>{c}</TD>' for c in row) + '</TR>' for row in [FLOW_HEAD] + rows)
        text = doc(balance(), title_table('연 결 손 익 계 산 서', FLOW_LINES) + '<TABLE>' + body + '</TABLE>', cash())
        self.assertEqual(pit_xml.parse_statements(text, year=2025)['values']['revenue'], 5968)

    def test_member_count_and_total_size_limits_apply_even_when_a_member_is_usable(self):
        good = doc(balance(), income(), cash())
        many = {f'm{i}.xml': '<DOCUMENT/>' for i in range(pit_xml.MAX_MEMBERS)}
        many['good.xml'] = good
        with self.assertRaises(ValueError):
            pit_xml.parse_document_zip(make_zip(many), receipt='20260311004208', year=2025, url='u')
        original = pit_xml.MAX_MEMBER_BYTES
        try:
            pit_xml.MAX_MEMBER_BYTES = len(good.encode('utf-8')) + 10
            sizes = {'a.xml': good, 'b.xml': good, 'c.xml': good}
            with self.assertRaises(ValueError):
                pit_xml.parse_document_zip(make_zip(sizes), receipt='20260311004208', year=2025, url='u')
        finally:
            pit_xml.MAX_MEMBER_BYTES = original


class OperatingLossTests(unittest.TestCase):
    def values(self, row):
        rows = [['Ⅰ. 매출', '', '5,968', '4,894'], row]
        return pit_xml.parse_statements(doc(balance(), income(rows=rows), cash()), year=2025)['values']

    def test_an_operating_loss_row_shown_as_a_negative_amount_is_the_operating_profit(self):
        self.assertEqual(self.values(['IV. 영업손실', '3', '(943)', '(914)'])['operating_profit'], -943)
        self.assertEqual(self.values(['영업 손실', '', '(5)', '(1)'])['operating_profit'], -5)
        self.assertEqual(self.values(['영업손실', '', '-', '-'])['operating_profit'], 0)

    def test_an_operating_loss_row_with_a_positive_amount_is_ambiguous_and_refused(self):
        for row in (['IV. 영업손실', '', '943', '(914)'], ['IV. 영업손실', '', '(943)', '914'], ['영업손실', '', '1', '1']):
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.values(row)

    def test_an_operating_profit_and_an_operating_loss_row_together_are_refused(self):
        rows = [['Ⅰ. 매출', '', '5', '4'], ['Ⅵ. 영업이익', '', '6', '3'], ['IV. 영업손실', '', '(1)', '(1)']]
        with self.assertRaises(ValueError):
            pit_xml.parse_statements(doc(balance(), income(rows=rows), cash()), year=2025)


class PeriodNotationTests(unittest.TestCase):
    """Real filings differ: zero-padded months/days and no (당) marker on the flow statements (Lotte Chemical FY2024)."""
    PADDED = ['제 49 기 2024년 01월 01일부터 2024년 12월 31일까지', '제 48 기 2023년 01월 01일부터 2023년 12월 31일까지']
    BS = ['제 49(당) 기말 2024년 12월 31일 현재', '제 48(전) 기말 2023년 12월 31일 현재']

    def parse(self, flow_lines, bs_lines=None, year=2024):
        text = doc(balance(lines=bs_lines or self.BS), income(lines=flow_lines), cash(lines=flow_lines))
        return pit_xml.parse_statements(text, year=year)

    def test_zero_padded_dates_and_period_numbers_without_a_current_marker_are_read(self):
        self.assertEqual(core(self.parse(self.PADDED)['values']), EXPECTED)

    def test_the_line_with_the_larger_period_number_is_the_current_one_whatever_the_order(self):
        self.assertEqual(core(self.parse(list(reversed(self.PADDED)))['values']), EXPECTED)

    def test_without_markers_the_current_period_must_be_decidable(self):
        same = ['제 49 기 2024년 01월 01일부터 2024년 12월 31일까지', '제 49 기 2023년 01월 01일부터 2023년 12월 31일까지']
        one = [self.PADDED[0]]
        no_number = ['2024년 01월 01일부터 2024년 12월 31일까지', '2023년 01월 01일부터 2023년 12월 31일까지']
        for lines in (same, one, no_number, []):
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                self.parse(lines)

    def test_the_bigger_number_line_must_still_be_the_requested_year_and_a_full_calendar_year(self):
        wrong_year = ['제 50 기 2025년 01월 01일부터 2025년 12월 31일까지', '제 49 기 2024년 01월 01일부터 2024년 12월 31일까지']
        with self.assertRaises(ValueError):
            self.parse(wrong_year)
        for lines in (['제 49 기 2024년 07월 01일부터 2024년 12월 31일까지', '제 48 기 2023년 07월 01일부터 2023년 12월 31일까지'],
                      ['제 49 기 2024년 11월 01일부터 2024년 12월 31일까지', '제 48 기 2023년 11월 01일부터 2023년 12월 31일까지'],
                      ['제 49 기 2024년 01월 11일부터 2024년 12월 31일까지', '제 48 기 2023년 01월 11일부터 2023년 12월 31일까지'],
                      ['제 49 기 2024년 01월 01일부터 2024년 12월 30일까지', '제 48 기 2023년 01월 01일부터 2023년 12월 30일까지']):
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                self.parse(lines)

    def test_a_prior_marker_on_the_older_line_alone_still_lets_the_period_numbers_decide(self):
        lines = ['제 49 기 2024년 01월 01일부터 2024년 12월 31일까지', '제 48(전) 기 2023년 01월 01일부터 2023년 12월 31일까지']
        self.assertEqual(core(self.parse(lines)['values']), EXPECTED)

    def test_a_current_marker_still_wins_over_period_numbers(self):
        marked = ['제 48 기 2023년 01월 01일부터 2023년 12월 31일까지', '제 49(당) 기 2024년 01월 01일부터 2024년 12월 31일까지']
        self.assertEqual(core(self.parse(marked)['values']), EXPECTED)
        wrong = ['제 49 기 2024년 01월 01일부터 2024년 12월 31일까지', '제 48(당) 기 2023년 01월 01일부터 2023년 12월 31일까지']
        with self.assertRaises(ValueError):
            self.parse(wrong)

    def test_zero_padded_balance_sheet_dates_are_read_and_a_tail_of_a_longer_number_is_not(self):
        padded_bs = ['제 49(당) 기말 2024년 12월 31일 현재', '제 48(전) 기말 2023년 12월 31일 현재']
        self.assertEqual(core(self.parse(self.PADDED, bs_lines=padded_bs)['values']), EXPECTED)
        with self.assertRaises(ValueError):
            self.parse(self.PADDED, bs_lines=['제 49(당) 기말 12024년 12월 31일 현재', '제 48(전) 기말 2023년 12월 31일 현재'])


def balance_rows_not_a_table_marker():
    return ''


class RecordTests(unittest.TestCase):
    URL = 'https://opendart.fss.or.kr/api/document.xml?rcept_no=20260311004208'

    def test_the_record_has_the_shape_pit_values_accepts(self):
        digest = hashlib.sha256(b'zip').hexdigest()
        record = pit_xml.build_record(FULL, receipt='20260311004208', year=2025, url=self.URL, sha256=digest)
        self.assertEqual(core(record['values']), EXPECTED)
        self.assertEqual((record['basis'], record['quarter'], record['year'], record['currency'], record['unit']), ('CFS', 4, 2025, 'KRW', 'KRW'))
        self.assertEqual((record['period_start'], record['period_end'], record['receipt'], record['url']), ('2025-01-01', '2025-12-31', '20260311004208', self.URL))
        self.assertEqual(record['parser_version'], pit_xml.PARSER_VERSION)
        receipt, provenance = map_record(record, company='298040', rcept_dt='2026-03-11')
        self.assertEqual({k: receipt['values'][k] for k in ('revenue', 'op', 'ocf', 'equity', 'cash')}, {k: float(v) for k, v in dict(revenue=5968, op=746, ocf=493, equity=2489, cash=216).items()})
        self.assertEqual((provenance['contract_sha256'], provenance['mapping_version'], provenance['include_debt']), (digest, 'pit-values-1', False))

    def test_bad_receipts_and_digests_are_refused(self):
        digest = hashlib.sha256(b'zip').hexdigest()
        for kwargs in (dict(receipt='2026031100420', sha256=digest), dict(receipt='20260311004208', sha256='abc'), dict(receipt='20261311004208', sha256=digest),
                       dict(receipt=20260311004208, sha256=digest)):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                pit_xml.build_record(FULL, year=2025, url=self.URL, **kwargs)


def make_zip(members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data if isinstance(data, bytes) else data.encode('utf-8'))
    return buffer.getvalue()


class ZipTests(unittest.TestCase):
    URL = RecordTests.URL

    def run_zip(self, members, **kwargs):
        return pit_xml.parse_document_zip(make_zip(members), receipt='20260311004208', year=2025, url=self.URL, **kwargs)

    def test_a_main_report_and_an_attachment_that_agree_give_one_record_with_the_zip_digest(self):
        data = make_zip({'20260311004208.xml': doc(balance(), income(), cash()), '20260311004208_00761.xml': doc(balance(), income(), cash()),
                         '20260311004208_00760.xml': '<DOCUMENT><P>감사보고서</P></DOCUMENT>'})
        record = pit_xml.parse_document_zip(data, receipt='20260311004208', year=2025, url=self.URL)
        self.assertEqual(core(record['values']), EXPECTED)
        _, provenance = map_record(record, company='298040', rcept_dt='2026-03-11')
        self.assertEqual(provenance['contract_sha256'], hashlib.sha256(data).hexdigest())

    def test_members_that_hold_no_statements_or_cannot_be_decoded_are_skipped_but_nothing_usable_is_an_error(self):
        record = self.run_zip({'a.xml': b'\xff\xfe\x00bad', 'b.xml': doc(balance(), income(), cash()), 'c.txt': 'ignored'})
        self.assertEqual(core(record['values']), EXPECTED)
        with self.assertRaises(ValueError):
            self.run_zip({'a.xml': '<DOCUMENT/>', 'b.xml': b'\xff\xfe\x00bad'})

    def test_members_that_disagree_or_are_individually_broken_are_refused(self):
        other_rows = [row[:] for row in IS_ROWS];other_rows[0][2] = '5,975'      # more than one unit away: a one-unit difference is rounding (tests/test_pit_xml_layouts.py)
        with self.assertRaises(ValueError):
            self.run_zip({'a.xml': doc(balance(), income(), cash()), 'b.xml': doc(balance(), income(rows=other_rows), cash())})
        with self.assertRaises(ValueError):
            self.run_zip({'a.xml': doc(balance(), income(), cash()), 'b.xml': doc(balance(unit='(단위 : 억원)'), income(), cash())})   # a broken member is not silently skipped

    def test_a_member_that_only_adds_fields_the_other_lacks_is_merged_not_a_conflict(self):
        record = self.run_zip({'a.xml': doc(balance(), income()), 'b.xml': doc(cash())})
        self.assertEqual(core(record['values']), EXPECTED)

    def test_cp949_members_are_decoded(self):
        record = self.run_zip({'a.xml': doc(balance(), income(), cash()).encode('cp949', errors='replace')})
        self.assertEqual(core(record['values']), EXPECTED)

    def test_not_a_zip_a_bad_member_count_or_an_oversized_member_is_refused(self):
        with self.assertRaises(ValueError):
            pit_xml.parse_document_zip(b'not a zip', receipt='20260311004208', year=2025, url=self.URL)
        with self.assertRaises(ValueError):
            pit_xml.parse_document_zip(b'', receipt='20260311004208', year=2025, url=self.URL)
        many = {f'm{i}.xml': '<DOCUMENT/>' for i in range(pit_xml.MAX_MEMBERS + 1)}
        with self.assertRaises(ValueError):
            self.run_zip(many)
        original = pit_xml.MAX_MEMBER_BYTES
        try:
            pit_xml.MAX_MEMBER_BYTES = 1000
            with self.assertRaises(ValueError):
                self.run_zip({'a.xml': doc(balance(), income(), cash()) + ' ' * 5000})
        finally:
            pit_xml.MAX_MEMBER_BYTES = original

    def test_member_names_are_never_used_as_paths(self):
        record = self.run_zip({'../../evil.xml': doc(balance(), income(), cash())})
        self.assertEqual(core(record['values']), EXPECTED)


SPECIMEN_ROOT = os.environ.get('PIT_SPECIMEN_ROOT')


@unittest.skipUnless(SPECIMEN_ROOT and (Path(SPECIMEN_ROOT) / 'artifacts/manifest.jsonl').exists(), 'real specimen is local only (set PIT_SPECIMEN_ROOT)')
class SpecimenTests(unittest.TestCase):
    def test_the_stored_hyosung_heavy_industries_report_gives_the_known_consolidated_figures(self):
        import json
        root = Path(SPECIMEN_ROOT) / 'artifacts'
        rows = [json.loads(line) for line in (root / 'manifest.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        row = [r for r in rows if r['document_id'] == 'document-zip' and r['rcept_no'] == '20260311004208'][-1]
        data = (root / 'blobs' / row['sha256']).read_bytes()
        record = pit_xml.parse_document_zip(data, receipt='20260311004208', year=2025, url='local-specimen')
        self.assertEqual(record['values'], dict(revenue=5968511616609, operating_profit=746968417289, ocf=493009624019, equity=2489720957283, cash=216772513676))


if __name__ == '__main__':
    unittest.main()
