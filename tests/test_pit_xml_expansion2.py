"""Contract for the second pool expansion (2026-11-05): the five parser/data gaps found in 한화솔루션, 금호석유화학, LG화학, 포스코인터내셔널 and 한국가스공사.

Layouts are synthetic copies of the real structures (receipts in docs/review/result_PIT_pool_expansion2_2026-11-05.md); the hand-read note facts are checked for scale and shape only.
"""
import io
import unittest
import zipfile
from unittest import mock
from investment import pit_xml, pit_xml_accounts
from tests.test_pit_xml import doc, balance, income, cash, EXPECTED, core
from tests.test_pit_xml_accounts import read, bs, inc, cf, BS, IS, CF, drop


def open_head():
    return ['과 목', '주석', '제 8(당) 기말', '제 7(전) 기말', '제 7(전) 기초']


OPEN_LINES = ['제8기 기말 2025년 12월 31일 현재', '제7기 기말 2024년 12월 31일 현재', '제7기 기초 2024년 1월 1일 현재']      # the title lines carry no (당)/(전) mark, the column headers do
OPEN_ROWS = [['자산', '', '', '', ''], ['Ⅰ. 유동자산', '', '3,738', '3,036', '2,900'], ['현금및현금성자산', '5,9,10', '216', '249', '277'],
             ['자산총계', '', '7,227', '6,218', '5,900'], ['부채 총계', '', '4,738', '4,163', '4,000'], ['자본 총계', '', '2,489', '2,055', '1,900']]


def opening_bs(head=None, lines=OPEN_LINES, rows=OPEN_ROWS):
    return balance(lines=lines, head=head or open_head(), rows=rows)


class OpeningColumnTests(unittest.TestCase):
    """한화솔루션 FY2024 / 금호석유화학 FY2023: current close, previous close and previous opening are three instants, not a missing column."""

    def parse(self, bs):
        return pit_xml.parse_statements(doc(bs, income(), cash()), year=2025)

    def test_a_three_instant_balance_sheet_reads_the_current_close(self):
        self.assertEqual(core(self.parse(opening_bs())['values']), EXPECTED)

    def test_the_short_period_notation_without_a_marker_is_read_too(self):
        head = ['과 목', '주석', '제 8 기말', '제 7 기말', '제 7 기초']
        lines = ['제8기말 2025년 12월 31일 현재', '제7기말 2024년 12월 31일 현재', '제7기초 2024년 1월 1일 현재']
        self.assertEqual(core(self.parse(opening_bs(head=head, lines=lines))['values']), EXPECTED)

    def test_the_layout_is_refused_unless_periods_and_dates_are_exactly_right(self):
        cases = {
            'no opening header': ['과 목', '주석', '제 8(당) 기말', '제 7(전) 기말', '제 7(전) 기말'],
            'wrong period numbers': ['과 목', '주석', '제 8(당) 기말', '제 7(전) 기말', '제 6(전) 기초'],
            'marker out of order': ['과 목', '주석', '제 8(당) 기말', '제 7(당) 기말', '제 7(전) 기초'],
        }
        for name, head in cases.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.parse(opening_bs(head=head))
        for name, lines in {'opening date missing': OPEN_LINES[:2], 'opening date wrong': OPEN_LINES[:2] + ['제7기 기초 2024년 7월 1일 현재'],
                            'previous close wrong year': [OPEN_LINES[0], '제7기 기말 2023년 12월 31일 현재', OPEN_LINES[2]]}.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.parse(opening_bs(lines=lines))

    def test_the_income_statement_never_takes_this_layout(self):
        head = ['과 목', '주석', '제 8(당) 기', '제 7(전) 기', '제 7(전) 기초']
        rows = [['Ⅰ. 매출액', '', '5,968', '4,894', '4,000'], ['Ⅵ. 영업이익', '', '746', '362', '300'], ['XIV. 당기순이익', '', '502', '222', '1']]
        with self.assertRaises(ValueError):
            pit_xml.parse_statements(doc(opening_bs(), income(head=head, rows=rows), cash()), year=2025)


SECTOR_ROWS = [['자산', '', '', '', '', ''], ['Ⅰ. 유동자산', '', '', '3,738', '', '3,036'], ['현금및현금성자산', '5,6', '200', '', '230', ''],
               ['Ⅱ. 비유동자산', '', '', '3,489', '', '3,182'], ['Ⅲ. 금융업자산', '', '', '50', '', '40'], ['현금및현금성자산', '27,28', '16', '', '19', ''],
               ['자산총계', '', '', '7,227', '', '6,218'], ['부채 총계', '', '', '4,738', '', '4,163'], ['자본 총계', '', '', '2,489', '', '2,055']]
CLOSING = [['Ⅰ.영업활동으로 인한 현금흐름', '', '', '493', '', '412'], ['Ⅶ.기말 현금및현금성자산', '', '', '216', '', '249']]


class SectorCashTests(unittest.TestCase):
    """한화솔루션 FY2022/2023: the consolidated face lists cash twice, once under 유동자산 and once under 금융업자산; the cash-flow closing cash proves they are parts of one total."""

    def parse(self, bs_rows=SECTOR_ROWS, cf_rows=CLOSING):
        return pit_xml.parse_statements(doc(balance(rows=bs_rows), income(), cash(rows=cf_rows)), year=2025)

    def test_two_sector_cash_lines_are_summed_when_the_closing_cash_agrees(self):
        self.assertEqual(self.parse()['values']['cash'], 216)

    def test_a_positive_operating_loss_is_settled_in_a_document_that_takes_the_sector_cash_path(self):
        rows = [['Ⅰ. 매출', '', '5,968', '4,894'], ['Ⅲ. 매출총이익', '', '100', '90'], ['Ⅳ. 판매비와관리비', '', '1,043', '1,004'], ['Ⅴ. 영업손실', '', '943', '914']]
        parsed = pit_xml.parse_statements(doc(balance(rows=SECTOR_ROWS), income(rows=rows), cash(rows=CLOSING)), year=2025)['values']
        self.assertEqual((parsed['cash'], parsed['operating_profit']), (216, -943))

    def test_a_closing_cash_that_disagrees_or_is_missing_stops_the_parse(self):
        for name, cf_rows in {'unequal': [CLOSING[0], ['Ⅶ.기말 현금및현금성자산', '', '', '217', '', '249']], 'missing': CLOSING[:1]}.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.parse(cf_rows=cf_rows)

    def test_other_duplicates_keep_the_strict_rule(self):
        same_section = [r for r in SECTOR_ROWS if r[0] != 'Ⅲ. 금융업자산']                  # both cash lines now sit under 유동자산 / 비유동자산 context
        with self.assertRaises(ValueError):
            self.parse(bs_rows=same_section)
        three = SECTOR_ROWS + [['현금및현금성자산', '1', '5', '', '5', '']]
        with self.assertRaises(ValueError):
            self.parse(bs_rows=three)

    def test_a_single_cash_line_is_unchanged(self):
        rows = [r for r in SECTOR_ROWS if r[0] not in ('Ⅲ. 금융업자산',) and r[1] != '27,28']
        self.assertEqual(self.parse(bs_rows=rows)['values']['cash'], 200)


LG_ROWS = [['매출액', '5,968', '4,894', '4,000'], ['영업이익', '746', '362', '300'], ['법인세비용차감전순손실', '(1,780,425)', '1', '1'], ['법인세비용', '(15,998)', '1', '1'],
           ['계속영업손실', '(1,796,423)', '1', '1'], ['중단영업손익', '819,360', '1', '1'], ['당기순손실', '(977,063)', '1', '1'], ['계속영업이익', '842,386', '1', '1']]


class ContinuingLossTests(unittest.TestCase):
    """LG화학 FY2025: 계속영업손실 is the identity target; the later attribution row 계속영업이익 must not replace it."""

    def test_the_tax_is_an_expense_printed_as_a_deduction(self):
        result = read(is_rows=LG_ROWS)
        self.assertEqual((result['values']['income_tax_expense'], result['values']['pretax_income'], result['values']['net_income_total'], result['notes']),
                         (15998, -1780425, -977063, {}))

    def test_without_the_loss_row_the_attribution_row_breaks_the_identity(self):
        result = read(is_rows=[r for r in LG_ROWS if r[0] != '계속영업손실'])
        self.assertEqual(result['notes'].get('income_tax_expense'), 'sign_unclear')

    def test_a_loss_label_printed_positive_is_not_used_as_a_target(self):
        rows = [['계속영업손실', '1,796,423', '1', '1'] if r[0] == '계속영업손실' else r for r in LG_ROWS]
        self.assertEqual(read(is_rows=rows)['notes'].get('income_tax_expense'), 'sign_unclear')


    def test_a_positive_loss_label_is_not_trusted_even_when_it_would_fit_the_identity(self):
        rows = [['매출액', '5,968', '4,894', '4,000'], ['영업이익', '746', '362', '300'], ['법인세비용차감전순이익', '100', '1', '1'], ['법인세비용', '(30)', '1', '1'],
                ['계속영업손실', '70', '1', '1']]                                         # no 당기순이익 row: the loss label would be the only identity target
        result = read(is_rows=rows)
        self.assertEqual((result['values']['income_tax_expense'], result['notes']), (-30, {}))       # as shown; believing the label would flip it to +30 (100 - 30 = 70)


class StoredCompanyFactTests(unittest.TestCase):
    """The hand-read note facts (million KRW x 1,000,000) and the LG face-total scope table. Values need the user's review."""
    FACTS = pit_xml_accounts.COMPANY_NOTE_FACTS

    def test_lease_facts_cover_three_companies_and_three_years_in_won(self):
        for code in ('051910', '047050', '036460'):
            years = [2022, 2023, 2024, 2025] if code == '036460' else [2022, 2023, 2024]
            self.assertEqual(sorted(y for c, y in self.FACTS if c == code), years)
            for year in years:
                fact = self.FACTS[(code, year)]
                self.assertTrue({'lease_current', 'lease_noncurrent'} <= set(fact))
                self.assertTrue(all(v % 1_000_000 == 0 for v in fact.values()))
        self.assertEqual(self.FACTS[('051910', 2024)], {'lease_current': 141_096_000_000, 'lease_noncurrent': 773_657_000_000})
        self.assertEqual(self.FACTS[('047050', 2022)], {'lease_current': 66_305_000_000, 'lease_noncurrent': 241_405_000_000})

    def test_gas_corp_borrowings_exclude_the_derivative_liabilities_of_the_face_total(self):
        self.assertEqual(self.FACTS[('036460', 2022)]['borrowings_current'], 25_558_917_000_000)      # face 유동금융부채 is 26,312,749 incl. 753,832 derivatives
        self.assertEqual(self.FACTS[('036460', 2025)]['borrowings_current'], 13_316_323_000_000)      # 8,167,720 + 1,984 + 5,146,619 (million KRW)

    def test_lg_borrowings_that_include_leases_are_listed_for_fy2022_to_fy2025_only(self):
        scope = pit_xml_accounts.COMPANY_BORROWINGS_INCLUDE_LEASE
        self.assertEqual(sorted(scope), [('051910', y) for y in (2022, 2023, 2024, 2025)])
        self.assertEqual(scope[('051910', 2025)], {'current': 11_738_137_000_000, 'noncurrent': 22_073_820_000_000})
        self.assertEqual(scope[('051910', 2022)]['current'], 3_804_367_000_000)


class LeaseInclusiveDebtTests(unittest.TestCase):
    """LG화학: the face borrowings already contain the leases, and pit_metrics adds leases again, so a source-verified total has its lease taken out once (FY2022-2024 only)."""
    KEY = ('000001', 2025)

    def parse(self, shown, rows=BS, facts=None):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('a.xml', doc(bs(rows=rows), inc(rows=IS), cf(rows=CF)).encode('utf-8'))
        note = {self.KEY: facts if facts is not None else {'lease_current': 7, 'lease_noncurrent': 15}}
        with mock.patch.dict(pit_xml_accounts.COMPANY_NOTE_FACTS, note, clear=False),                 mock.patch.dict(pit_xml_accounts.COMPANY_BORROWINGS_INCLUDE_LEASE, {self.KEY: shown}, clear=False):
            return pit_xml.parse_document_zip(buffer.getvalue(), receipt='20260316000940', year=2025, url='u', company='000001')['values']

    def test_a_matching_total_has_the_lease_taken_out_once(self):
        values = self.parse({'current': 130, 'noncurrent': 340})
        self.assertEqual((values['borrowings_current'], values['borrowings_noncurrent'], values['lease_current'], values['lease_noncurrent']), (123, 325, 7, 15))

    def test_a_total_that_differs_from_the_verified_face_amount_stops_the_parse(self):
        with self.assertRaises(ValueError):
            self.parse({'current': 131, 'noncurrent': 340})

    def test_a_missing_lease_stops_the_parse_instead_of_guessing(self):
        with self.assertRaises(ValueError):
            self.parse({'current': 130, 'noncurrent': 340}, rows=drop(BS, '유동리스부채', '비유동리스부채'), facts={'lease_total': 22})

    def test_other_company_years_are_left_alone(self):
        values = pit_xml.parse_statements(doc(bs(rows=BS), inc(rows=IS), cf(rows=CF)), year=2025)['values']
        self.assertEqual((values['borrowings_current'], values['borrowings_noncurrent']), (130, 340))


if __name__ == '__main__':unittest.main()
