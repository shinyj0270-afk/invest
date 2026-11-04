"""Contract for the "period-number" statement layout read by `investment/pit_xml.py` (seen in real 기재정정 documents, 효성중공업 FY2022/FY2024).

Layout: the statements sit inside ONE outer wrapper table (title table and account table are nested in it, so they are not outermost tables),
the title table holds one cell per row (name, period lines like `제 8 기 2025.12.31 현재` / `제 8 기 2025.01.01 부터 2025.12.31 까지`, `(단위 : 원)`),
and the account table header is `['', '제 8 기', '제 7 기', '제 6 기']` (first cell empty or `과목`, optional `주석`, two or three period columns, NO `(당)` marks).
Rules: the first column must be the current period and the period numbers must be consecutive and descending; the title's current line (largest
period number) must name the year, and its number must equal the first header number; a wanted account row carries exactly as many amounts as period columns.
The older `(당)/(전)` layout and the outermost-table reading stay unchanged; the nested reading is only used when no outermost statements are found.
"""
import hashlib
import io
import unittest
import zipfile
from investment import pit_xml
from tests.test_pit_xml import doc, EXPECTED, core

WIDE_BS = ['제 8 기 2025.12.31 현재', '제 7 기 2024.12.31 현재', '제 6 기 2023.12.31 현재']
WIDE_FLOW = ['제 8 기 2025.01.01 부터 2025.12.31 까지', '제 7 기 2024.01.01 부터 2024.12.31 까지', '제 6 기 2023.01.01 부터 2023.12.31 까지']
HEAD = ['', '제 8 기', '제 7 기', '제 6 기']
BS_ROWS = [['자산', '', '', ''], ['유동자산', '3,738', '3,036', '2,900'], ['현금및현금성자산', '216', '249', '200'], ['자본총계', '2,489', '2,055', '1,900']]
IS_ROWS = [['매출액', '5,968', '4,894', '4,000'], ['영업이익', '746', '362', '300'], ['당기순이익', '502', '222', '100']]
CF_ROWS = [['영업활동현금흐름', '493', '412', '380'], ['기말 현금및현금성자산', '216', '249', '200']]


def title(name, lines, unit='(단위 : 원)'):
    rows = [name] + lines + ([unit] if unit is not None else [])
    return '<TABLE><COLGROUP><COL/></COLGROUP><TBODY>' + ''.join(f'<TR><TD><P>{text}</P></TD></TR>' for text in rows) + '</TBODY></TABLE>'


def account(head, rows):
    head_html = '<THEAD><TR>' + ''.join(f'<TH><P>{c}</P></TH>' for c in head) + '</TR></THEAD>'
    body = ''.join('<TR>' + ''.join(f'<TD><P>{c}</P></TD>' if c else '<TD> </TD>' for c in row) + '</TR>' for row in rows)
    return '<TABLE>' + head_html + '<TBODY>' + body + '</TBODY></TABLE>'


def stmt(name, lines, head, rows, unit='(단위 : 원)'):
    return title(name, lines, unit) + account(head, rows)


def wrap(*parts, closed=True):
    return '<TABLE><TITLE>2-1. 연결 재무제표</TITLE>' + ''.join(parts) + ('</TABLE>' if closed else '')


def bs(name='연결 재무상태표', lines=WIDE_BS, head=HEAD, rows=BS_ROWS, unit='(단위 : 원)'):
    return stmt(name, lines, head, rows, unit)


def inc(name='연결 손익계산서', lines=WIDE_FLOW, head=HEAD, rows=IS_ROWS, unit='(단위 : 원)'):
    return stmt(name, lines, head, rows, unit)


def cf(name='연결 현금흐름표', lines=WIDE_FLOW, head=HEAD, rows=CF_ROWS, unit='(단위 : 원)'):
    return stmt(name, lines, head, rows, unit)


def parse(*parts, year=2025, closed=True):
    return pit_xml.parse_statements(doc(wrap(*parts, closed=closed)), year=year)


class WideLayoutTests(unittest.TestCase):
    def test_statements_nested_in_a_wrapper_table_with_three_period_columns_are_read_from_the_first_column(self):
        result = parse(bs(), inc(), cf())
        self.assertEqual(core(result['values']), EXPECTED)
        self.assertEqual((result['basis'], result['currency'], result['unit']), ('CFS', 'KRW', 1))
        self.assertEqual((result['period_start'], result['period_end']), ('2025-01-01', '2025-12-31'))
        self.assertEqual(result['statements'], {'balance': 1, 'income': 1, 'cash': 1})

    def test_an_unclosed_wrapper_table_and_a_missing_wrapper_both_work(self):
        self.assertEqual(core(parse(bs(), inc(), cf(), closed=False)['values']), EXPECTED)
        flat = pit_xml.parse_statements(doc(bs(), inc(), cf()), year=2025)
        self.assertEqual(core(flat['values']), EXPECTED)

    def test_two_period_columns_and_an_optional_note_column_work(self):
        two = ['', '제 8 기', '제 7 기']
        rows = lambda r: [row[:3] for row in r]
        self.assertEqual(core(parse(bs(head=two, rows=rows(BS_ROWS), lines=WIDE_BS[:2]), inc(head=two, rows=rows(IS_ROWS), lines=WIDE_FLOW[:2]),
                                    cf(head=two, rows=rows(CF_ROWS), lines=WIDE_FLOW[:2]))['values']), EXPECTED)
        noted = ['과목', '주석', '제 8 기', '제 7 기', '제 6 기']
        with_note = lambda r: [[row[0], '5'] + row[1:] for row in r]
        self.assertEqual(core(parse(bs(head=noted, rows=with_note(BS_ROWS)), inc(head=noted, rows=with_note(IS_ROWS)), cf(head=noted, rows=with_note(CF_ROWS)))['values']), EXPECTED)

    def test_a_comprehensive_income_statement_alone_supplies_revenue_and_a_plain_one_wins_when_both_exist(self):
        only = parse(bs(), inc(name='연결 포괄손익계산서'), cf())
        self.assertEqual(core(only['values']), EXPECTED)
        both = parse(bs(), inc(), inc(name='연결 포괄손익계산서', rows=[['매출액', '1', '1', '1'], ['영업이익', '1', '1', '1']]), cf())
        self.assertEqual(core(both['values']), EXPECTED)

    def test_the_unit_is_scaled(self):
        million = parse(bs(unit='(단위 : 백만원)'), inc(unit='(단위 : 백만원)'), cf(unit='(단위 : 백만원)'))
        self.assertEqual((million['values']['revenue'], million['values']['equity'], million['unit']), (5968_000_000, 2489_000_000, 1_000_000))
        with self.assertRaises(ValueError):
            parse(bs(unit='(단위 : 억원)'), inc(), cf())

    def test_number_notations_and_zero_dashes_follow_the_older_layout(self):
        rows = [['매출액', '(1,000)', '5', '5'], ['영업이익', '-', '5', '5']]
        values = parse(bs(), inc(rows=rows), cf())['values']
        self.assertEqual((values['revenue'], values['operating_profit']), (-1000, 0))
        with self.assertRaises(ValueError):
            parse(bs(), inc(rows=[['매출액', '12a', '5', '5'], ['영업이익', '1', '1', '1']]), cf())

    def test_a_stray_table_inside_a_cell_does_not_disturb_the_rest_of_the_enclosing_statement(self):
        stray = '<TABLE><TR><TD>메모</TD></TR></TABLE>'
        body = account(HEAD, BS_ROWS[:-1]).replace('</TBODY>', '<TR><TD><P>자본총계</P>' + stray + '</TD><TD>2,489</TD><TD>2,055</TD><TD>1,900</TD></TR></TBODY>')
        self.assertEqual(core(parse(title('연결 재무상태표', WIDE_BS) + body, inc(), cf())['values']), EXPECTED)

    def test_copies_must_agree_and_identical_repeats_are_fine(self):
        self.assertEqual(core(parse(bs(), bs(), inc(), cf())['values']), EXPECTED)
        changed = [['자산', '', '', ''], ['자본총계', '9', '9', '9']]
        with self.assertRaises(ValueError):
            parse(bs(), bs(rows=changed), inc(), cf())

    def test_separate_statements_without_the_consolidated_prefix_are_ignored(self):
        with self.assertRaises(pit_xml.NoStatements):
            parse(bs(name='재무상태표'), inc(name='손익계산서'), cf(name='현금흐름표'))
        values = parse(bs(name='재무상태표', rows=[['자본총계', '1', '1', '1']]), bs(), inc(), cf())['values']
        self.assertEqual(values['equity'], 2489)


class WideLayoutRefusalTests(unittest.TestCase):
    def assert_refused(self, *parts, year=2025):
        with self.assertRaises(ValueError) as caught:
            parse(*parts, year=year)
        self.assertNotIsInstance(caught.exception, pit_xml.NoStatements)

    def test_the_first_column_must_be_the_current_period_in_strictly_descending_consecutive_order(self):
        for head in (['', '제 6 기', '제 7 기', '제 8 기'], ['', '제 8 기', '제 7 기', '제 5 기'], ['', '제 8 기', '제 8 기', '제 7 기'],
                     ['', '제 8 기', '제 6 기', '제 7 기'], ['', '제 7 기', '제 6 기', '제 5 기']):
            with self.subTest(head=head):
                self.assert_refused(bs(head=head), inc(), cf())

    def test_the_title_current_line_and_the_header_must_name_the_same_period(self):
        late = ['제 9 기 2025.12.31 현재', '제 8 기 2024.12.31 현재', '제 7 기 2023.12.31 현재']
        self.assert_refused(bs(lines=late), inc(), cf())
        same = ['제 8 기 2025.12.31 현재', '제 8 기 2024.12.31 현재', '제 8 기 2023.12.31 현재']
        self.assert_refused(bs(lines=same), inc(), cf())

    def test_the_current_line_must_be_the_requested_calendar_year(self):
        old = ['제 8 기 2024.12.31 현재', '제 7 기 2023.12.31 현재', '제 6 기 2022.12.31 현재']
        self.assert_refused(bs(lines=old), inc(), cf())
        self.assert_refused(bs(), inc(), cf(), year=2024)
        for line in ('제 8 기 2025.12.30 현재', '제 8 기 2025.06.30 현재'):
            with self.subTest(line=line):
                self.assert_refused(bs(lines=[line] + WIDE_BS[1:]), inc(), cf())
        for start in ('제 8 기 2025.02.01 부터 2025.12.31 까지', '제 8 기 2025.12.31 까지'):
            with self.subTest(start=start):
                self.assert_refused(bs(), inc(lines=[start] + WIDE_FLOW[1:]), cf())

    def test_zero_padded_and_unpadded_dotted_dates_are_both_accepted(self):
        bs_lines = ['제 8 기 2025.12.31 현재', '제 7 기 2024.12.31 현재', '제 6 기 2023.12.31 현재']
        flow = ['제 8 기 2025.1.1 부터 2025.12.31 까지', '제 7 기 2024.1.1 부터 2024.12.31 까지', '제 6 기 2023.1.1 부터 2023.12.31 까지']
        self.assertEqual(core(parse(bs(lines=bs_lines), inc(lines=flow), cf(lines=flow))['values']), EXPECTED)

    def test_a_wanted_row_must_carry_exactly_one_amount_per_period_column(self):
        for row in (['매출액', '5,968', '4,894', ''], ['매출액', '5,968'], ['매출액', '5,968', '4,894', '4,000', '3,000']):
            with self.subTest(row=row):
                self.assert_refused(bs(), inc(rows=[row, ['영업이익', '1', '1', '1']]), cf())

    def test_a_loss_label_with_a_positive_amount_in_any_period_is_refused_and_all_negative_is_read(self):
        self.assert_refused(bs(), inc(rows=[['매출액', '5,968', '4,894', '4,000'], ['영업손실', '(746)', '362', '(300)']]), cf())
        self.assert_refused(bs(), inc(rows=[['매출액', '5,968', '4,894', '4,000'], ['영업손실', '(746)', '(362)', '300']]), cf())
        values = parse(bs(), inc(rows=[['매출액', '5,968', '4,894', '4,000'], ['영업손실', '(746)', '(362)', '(300)']]), cf())['values']
        self.assertEqual(values['operating_profit'], -746)

    def test_a_wanted_row_without_any_amount_is_refused_in_this_layout(self):
        self.assert_refused(bs(rows=[['자산', '', '', ''], ['자본총계', '', '', ''], ['현금및현금성자산', '216', '249', '200']]), inc(), cf())

    def test_an_empty_first_header_cell_does_not_make_the_older_current_prior_columns_acceptable(self):
        old_cols = ['', '제 8(당) 기말', '제 7(전) 기말']
        self.assert_refused(bs(head=old_cols, rows=[row[:3] for row in BS_ROWS]), inc(), cf())

    def test_four_period_columns_are_not_accepted(self):
        head = ['', '제 8 기', '제 7 기', '제 6 기', '제 5 기']
        four = lambda rows: [row + ['1'] for row in rows]
        lines = lambda base: base + [base[0].replace('제 8 기', '제 5 기').replace('2025', '2022')]
        self.assert_refused(bs(head=head, rows=four(BS_ROWS), lines=lines(WIDE_BS)), inc(head=head, rows=four(IS_ROWS), lines=lines(WIDE_FLOW)),
                            cf(head=head, rows=four(CF_ROWS), lines=lines(WIDE_FLOW)))

    def test_a_duplicated_wanted_account_inside_one_statement_is_refused(self):
        self.assert_refused(bs(), inc(rows=IS_ROWS + [['매출액', '1', '1', '1']]), cf())

    def test_a_header_whose_first_cell_is_neither_empty_nor_the_account_heading_is_not_a_statement(self):
        for first in ('항목', '구분', '계정'):
            with self.subTest(first=first), self.assertRaises(pit_xml.NoStatements):
                parse(bs(head=[first] + HEAD[1:]), inc(head=[first] + HEAD[1:]), cf(head=[first] + HEAD[1:]))

    def test_columns_that_are_not_all_period_numbers_are_not_read_as_this_layout(self):
        for head in (['', '제 8 기', '제 7 기', '비고'], ['', '2025', '2024', '2023'], ['', '제 8 기']):
            with self.subTest(head=head):
                with self.assertRaises(ValueError):
                    parse(bs(head=head), inc(head=head), cf(head=head))


class FallbackAndRecordTests(unittest.TestCase):
    def test_the_older_layout_inside_a_wrapper_table_is_read_when_no_outermost_statements_exist(self):
        from tests.test_pit_xml import balance, income, cash
        text = doc(wrap(balance(), income(), cash()))
        self.assertEqual(core(pit_xml.parse_statements(text, year=2025)['values']), EXPECTED)

    def test_outermost_statements_are_used_first_and_the_nested_reading_is_only_a_fallback(self):
        from tests.test_pit_xml import balance
        outer = balance()
        nested_other = wrap(bs(rows=[['자본총계', '1', '1', '1']]), inc(), cf())
        values = pit_xml.parse_statements(doc(outer, nested_other), year=2025)['values']
        self.assertEqual(values, {'equity': 2489, 'cash': 216, 'total_assets': 7227, 'total_liabilities': 4738})       # the nested copy (equity 1) is never read

    def test_a_document_zip_with_the_wide_layout_builds_the_record(self):
        text = doc(wrap(bs(), inc(), cf()))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('20230309000420.xml', text.encode('utf-8'))
        data = buffer.getvalue()
        record = pit_xml.parse_document_zip(data, receipt='20230309000420', year=2025, url='opendart:document.xml')
        self.assertEqual(core(record['values']), EXPECTED)
        self.assertEqual((record['receipt'], record['basis'], record['year'], record['quarter']), ('20230309000420', 'CFS', 2025, 4))
        self.assertEqual(record['period_contract']['source']['sha256'], hashlib.sha256(data).hexdigest())

    def test_a_document_without_any_statement_still_reports_no_usable_document(self):
        with self.assertRaises(ValueError):
            pit_xml.parse_statements(doc('<TABLE><TR><TD>그 밖의 표</TD></TR></TABLE>'), year=2025)


if __name__ == '__main__':unittest.main()
