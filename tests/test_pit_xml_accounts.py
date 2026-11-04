"""Contract for the "A-stage" accounts read by `investment/pit_xml.py` (design: docs/review/design_financial_concepts_NICE_2026-11-04.md, section 6/7).

New fields (all KRW, current-period column, scaled by the statement unit). Everything here is SOFT: an anomaly in one of these fields never raises and never
blocks the five original fields, the field is simply left out and a reason is recorded in `result['notes']` (key = field, or `borrowings` / `lease` for a family).
A missing row means the field is absent (never 0). Labels are compared like the original aliases (whitespace removed, one leading numeral prefix removed) and
ALSO with one trailing note reference such as `(주14,31,35)` removed.

balance (section aware; sections are opened by the rows 유동자산, 비유동자산, 유동부채, 비유동부채 and closed by 부채총계, 자본, 자본총계, 자산총계, 부채, 자산):
  total_assets 자산총계 | total_liabilities 부채총계 | short_term_financial_instruments 단기금융상품 (only inside 유동자산)
  borrowings_current / borrowings_noncurrent = sum of the matching rows of the 유동부채 / 비유동부채 section:
    any section: 차입금, 사채, 전환사채, 신주인수권부사채, 차입금및사채, 사채및차입금, 교환사채
    current only: 단기차입금, 유동성장기차입금, 유동성사채, 단기사채, 유동성전환사채, 유동성신주인수권부사채, 유동성장기사채, 당좌차월
    non-current only: 장기차입금, 장기사채, 비유동차입금, 비유동사채
  lease_current / lease_noncurrent: any section 리스부채 | current only 유동리스부채, 유동성리스부채 | non-current only 비유동리스부채, 비유동성리스부채, 장기리스부채
  A family (borrowings / lease) is left out, with a note, when: a matching row sits in an unknown section (`section_unknown`) or in the wrong section (`section_mismatch`),
  the same label repeats inside one section (`duplicate`), a row has some but not all amounts (`amount_count`), an amount is unreadable (`bad_number`) or negative
  (`negative`), or a row in a liability section mentions 차입금/사채/리스부채/당좌차월 but is not in the lists above (`unclassified`). Rows without any amount are headings.
balance, liquid financial assets: current_financial_assets = sum of the rows 당기손익-공정가치금융자산, 당기손익-공정가치측정금융자산, 기타포괄손익-공정가치금융자산, 기타포괄손익-공정가치측정금융자산,
  유동금융자산, 단기투자자산, 단기매매금융자산 that sit INSIDE the 유동자산 section (the same labels in 비유동자산 are ignored without a note; `기타금융자산` is never counted because it mixes in
  non-liquid items). Anomalies follow the other summed fields: a label repeated inside the section `duplicate`, partial amounts `amount_count`, unreadable `bad_number`, negative `negative`,
  a row outside any asset section `section_unknown` (or `section_mismatch` inside a liability section). No row -> the field is absent (no note).
income: finance_costs 금융비용|금융원가 | pretax_income 법인세비용차감전순이익, 법인세차감전순이익, 법인세비용차감전계속영업이익, 법인세비용차감전계속사업이익 (each also with `(손실)`);
  loss labels 법인세비용차감전순손실, 법인세차감전순손실 | income_tax_expense 법인세비용, 법인세비용(수익), 법인세비용(환입); 법인세수익 is `unsupported_label` |
  net_income_total 당기순이익, 당기순이익(손실), 당기순손익, 연결당기순이익, 연결당기순이익(손실); loss label 당기순손실 | interest_expense 이자비용 (also from cash)
  Loss labels are accepted only with an amount <= 0, a positive amount is `sign_unclear`.
cash: depreciation 감가상각비, 유형자산감가상각비 | amortization 무형자산상각비 | rou_depreciation 사용권자산상각비 | interest_expense 이자비용 |
  capex_tangible 유형자산의취득 | capex_intangible 무형자산의취득 | dividends_paid 배당금의지급, 배당금지급.
  capex_* and dividends_paid are outflows: the stored value is the absolute value (companies show them as (negative) or as positive numbers).
  depreciation, amortization, rou_depreciation, interest_expense must be >= 0 (`negative` otherwise).
Amount cells: in the period-number layout the columns are positional, so the CURRENT amount is the first cell after the label/note column; later cells may be blank
(real documents leave a zero prior year blank), a blank current cell with a filled later cell, or more cells than period columns, is `amount_count`; a row whose cells are
all blank is a heading. In the older (당)/(전) layout the amounts are the non-empty cells and their number must equal the column count.
Per field: a label repeated inside one statement is `duplicate`; an unreadable amount is `bad_number`; a wanted row with some but not all amounts is `amount_count`;
two copies of the same statement (or two XML members, or income+cash for interest_expense) that disagree leave the field out with `conflict`.
"""
import io
import unittest
import zipfile
from investment import pit_xml
from tests.test_pit_xml import doc, EXPECTED, balance, income, cash
from tests.test_pit_xml_wide import bs, inc, cf, wrap, parse, HEAD, WIDE_BS, WIDE_FLOW

BS = [['자산', '', '', ''], ['유동자산', '3,738', '3,036', '2,900'], ['현금및현금성자산', '216', '249', '200'], ['단기금융상품', '50', '40', '30'],
      ['비유동자산', '3,489', '3,182', '3,000'], ['자산총계', '7,227', '6,218', '5,900'],
      ['부채', '', '', ''], ['유동부채', '3,561', '3,092', '3,000'], ['단기차입금', '100', '110', '120'], ['유동성장기차입금', '20', '25', '30'],
      ['유동성사채', '10', '5', '0'], ['유동리스부채', '7', '6', '5'],
      ['비유동부채', '1,176', '1,070', '1,000'], ['장기차입금', '300', '310', '320'], ['사채', '40', '30', '20'], ['비유동리스부채', '15', '14', '13'],
      ['부채총계', '4,738', '4,163', '4,000'], ['자본', '', '', ''], ['자본총계', '2,489', '2,055', '1,900']]
IS = [['매출액', '5,968', '4,894', '4,000'], ['영업이익', '746', '362', '300'], ['금융비용', '300', '280', '250'], ['법인세비용차감전순이익', '625', '223', '200'],
      ['법인세비용', '123', '1', '50'], ['당기순이익', '502', '222', '150']]
CF = [['영업활동현금흐름', '493', '412', '380'], ['이자비용', '53', '60', '50'], ['감가상각비', '200', '190', '180'], ['무형자산상각비', '20', '19', '18'],
      ['사용권자산상각비', '8', '7', '6'], ['유형자산의 취득', '(163)', '(84)', '(70)'], ['무형자산의 취득', '(15)', '(14)', '(13)'], ['배당금의 지급', '(46)', '(23)', '(20)']]
EXTRA = dict(total_assets=7227, total_liabilities=4738, short_term_financial_instruments=50, borrowings_current=130, borrowings_noncurrent=340,
             lease_current=7, lease_noncurrent=15, finance_costs=300, pretax_income=625, income_tax_expense=123, net_income_total=502,
             interest_expense=53, depreciation=200, amortization=20, rou_depreciation=8, capex_tangible=163, capex_intangible=15, dividends_paid=46)
FULL = {**EXPECTED, **EXTRA}


def read(bs_rows=BS, is_rows=IS, cf_rows=CF, extra=(), year=2025):
    return parse(bs(rows=bs_rows), inc(rows=is_rows), cf(rows=cf_rows), *extra, year=year)


def swap(rows, label, new):
    return [([new] + row[1:]) if row[0] == label else row for row in rows]


def drop(rows, *labels):
    return [row for row in rows if row[0] not in labels]


class ReadingTests(unittest.TestCase):
    def test_all_new_fields_are_read_from_the_first_column_of_the_period_number_layout(self):
        result = read()
        self.assertEqual(result['values'], FULL)
        self.assertEqual(result['notes'], {})

    def test_the_older_layout_with_note_column_and_empty_cells_reads_them_too(self):
        rows_bs = [['자산', '', '', '', '', ''], ['Ⅰ. 유동자산', '', '', '3,738', '', '3,036'], ['현금및현금성자산', '5,9', '216', '', '249', ''],
                   ['단기금융상품', '5', '50', '', '40', ''], ['자산총계', '', '', '7,227', '', '6,218'], ['Ⅱ. 유동부채', '', '', '3,561', '', '3,092'],
                   ['단기차입금', '18', '100', '', '110', ''], ['부채 총계', '', '', '4,738', '', '4,163'], ['자본', '', '', '', '', ''],
                   ['자본 총계', '', '', '2,489', '', '2,055']]
        rows_is = [['Ⅰ. 매출액', '7', '5,968', '4,894'], ['Ⅵ. 영업이익', '', '746', '362'], ['금융비용', '', '300', '280'], ['당기순이익', '', '502', '222']]
        rows_cf = [['Ⅰ.영업활동으로 인한 현금흐름', '', '', '493', '', '412'], ['유형자산의 취득', '9', '(163)', '', '(84)', '']]
        result = pit_xml.parse_statements(doc(balance(rows=rows_bs), income(rows=rows_is), cash(rows=rows_cf)), year=2025)
        self.assertEqual(result['values'], {**EXPECTED, 'total_assets': 7227, 'total_liabilities': 4738, 'short_term_financial_instruments': 50,
                                            'borrowings_current': 100, 'finance_costs': 300, 'net_income_total': 502, 'capex_tangible': 163})

    def test_the_statement_unit_scales_every_new_field(self):
        result = parse(bs(rows=BS, unit='(단위 : 백만원)'), inc(rows=IS, unit='(단위 : 백만원)'), cf(rows=CF, unit='(단위 : 백만원)'))
        self.assertEqual(result['values'], {k: v * 1_000_000 for k, v in FULL.items()})

    def test_trailing_note_references_are_removed_and_numeral_prefixes_too(self):
        rows = [[f'{r[0]} (주14,31,35)' if r[0] in ('단기차입금', '장기차입금', '자본총계', '비유동리스부채') else r[0]] + r[1:] for r in BS]
        rows = [['Ⅱ. 유동부채'] + r[1:] if r[0] == '유동부채' else r for r in rows]
        result = read(bs_rows=rows)
        self.assertEqual(result['values'], FULL)

    def test_missing_rows_leave_the_fields_absent_and_zero_and_dash_are_kept_as_zero(self):
        result = read(bs_rows=drop(BS, '단기금융상품', '유동리스부채', '비유동리스부채'), cf_rows=drop(CF, '이자비용', '감가상각비'))
        for key in ('short_term_financial_instruments', 'lease_current', 'lease_noncurrent', 'interest_expense', 'depreciation'):
            self.assertNotIn(key, result['values'])
        self.assertEqual(result['notes'], {})
        rows = [['단기차입금', '0', '1', '1'] if r[0] == '단기차입금' else ['유동성장기차입금', '-', '1', '1'] if r[0] == '유동성장기차입금' else r for r in BS]
        zero = read(bs_rows=rows, is_rows=[row if row[0] != '금융비용' else ['금융비용', '-', '1', '1'] for row in IS])
        self.assertEqual((zero['values']['finance_costs'], zero['values']['borrowings_current']), (0, 10))
        self.assertEqual(zero['notes'], {})

    def test_a_balance_sheet_without_any_new_account_still_parses(self):
        result = parse(bs(), inc(), cf())
        self.assertEqual(result['values'], {**EXPECTED, 'net_income_total': 502})       # the shared income fixture has a 당기순이익 row
        self.assertEqual(result['notes'], {})


class SectionTests(unittest.TestCase):
    def test_a_bare_borrowing_label_takes_the_section_it_sits_in(self):
        rows = [['유동자산', '1', '1', '1'], ['현금및현금성자산', '216', '1', '1'], ['자산총계', '1', '1', '1'], ['유동부채', '1', '1', '1'], ['차입금및사채', '5,274', '4,120', '1'],
                ['유동성리스부채', '61', '49', '1'], ['기타금융부채', '1,224', '142', '1'], ['비유동부채', '1', '1', '1'], ['차입금및사채', '5,131', '5,707', '1'],
                ['리스부채', '196', '136', '1'], ['부채총계', '1', '1', '1'], ['자본', '', '', ''], ['자본총계', '2,489', '2,055', '1']]
        v = read(bs_rows=rows)['values']
        self.assertEqual((v['borrowings_current'], v['borrowings_noncurrent'], v['lease_current'], v['lease_noncurrent']), (5274, 5131, 61, 196))

    def test_a_current_only_label_in_the_non_current_section_or_the_reverse_drops_the_family(self):
        for label, moved in (('단기차입금', 'noncurrent'), ('장기차입금', 'current')):
            rows = [r for r in BS if r[0] != label]
            at = next(i for i, r in enumerate(rows) if r[0] == ('비유동부채' if moved == 'noncurrent' else '유동부채'))
            rows = rows[:at + 1] + [[label, '9', '9', '9']] + rows[at + 1:]
            with self.subTest(label=label):
                result = read(bs_rows=rows)
                self.assertNotIn('borrowings_current', result['values']);self.assertNotIn('borrowings_noncurrent', result['values'])
                self.assertEqual(result['notes'].get('borrowings'), 'section_mismatch')
                self.assertEqual(result['values']['lease_current'], 7)

    def test_a_matching_row_outside_any_liability_section_drops_the_family(self):
        rows = drop(BS, '유동부채', '비유동부채')
        result = read(bs_rows=rows)
        self.assertNotIn('borrowings_current', result['values'])
        self.assertEqual((result['notes'].get('borrowings'), result['notes'].get('lease')), ('section_unknown', 'section_unknown'))

    def test_the_section_is_closed_by_the_total_liability_row_so_a_later_matching_row_has_no_section(self):
        result = read(bs_rows=BS + [['사채', '9', '9', '9']])
        self.assertNotIn('borrowings_noncurrent', result['values'])
        self.assertEqual(result['notes'].get('borrowings'), 'section_unknown')
        self.assertEqual(result['values']['lease_noncurrent'], 15)

    def test_short_term_financial_instruments_count_only_inside_current_assets(self):
        rows = [r for r in BS if r[0] != '단기금융상품']
        at = next(i for i, r in enumerate(rows) if r[0] == '비유동자산')
        result = read(bs_rows=rows[:at + 1] + [['단기금융상품', '5', '5', '5']] + rows[at + 1:])
        self.assertNotIn('short_term_financial_instruments', result['values'])
        self.assertEqual(result['notes'].get('short_term_financial_instruments'), 'section_mismatch')

    def test_an_unlisted_borrowing_like_liability_row_drops_the_family(self):
        for label, family, other in (('운영차입금', 'borrowings', 'lease'), ('사채할인발행차금', 'borrowings', 'lease'),
                                     ('리스부채상환예정액', 'lease', 'borrowings'), ('당좌차월약정', 'borrowings', 'lease')):
            rows = BS[:10] + [[label, '1', '1', '1']] + BS[10:]
            with self.subTest(label=label):
                result = read(bs_rows=rows)
                self.assertEqual(result['notes'], {family: 'unclassified'})
                self.assertNotIn(family + '_current', result['values']);self.assertNotIn(family + '_noncurrent', result['values'])
                self.assertIn(other + '_current', result['values'])

    def test_repeated_labels_partial_amounts_bad_and_negative_numbers_drop_only_their_family(self):
        cases = {'duplicate': BS[:9] + [['단기차입금', '1', '1', '1']] + BS[9:], 'amount_count': BS[:8] + [['단기차입금', '', '110', '120']] + BS[9:],
                 'bad_number': BS[:8] + [['단기차입금', '12a', '110', '120']] + BS[9:], 'negative': BS[:8] + [['단기차입금', '(100)', '110', '120']] + BS[9:]}
        for reason, rows in cases.items():
            with self.subTest(reason=reason):
                result = read(bs_rows=rows)
                self.assertEqual(result['notes'].get('borrowings'), reason)
                self.assertNotIn('borrowings_current', result['values']);self.assertNotIn('borrowings_noncurrent', result['values'])
                self.assertEqual(result['values']['lease_current'], 7);self.assertEqual(result['values']['equity'], 2489)

    def test_total_rows_repeated_drop_only_that_total(self):
        result = read(bs_rows=BS + [['자산총계', '1', '1', '1']])
        self.assertNotIn('total_assets', result['values']);self.assertEqual(result['notes'].get('total_assets'), 'duplicate')
        self.assertEqual(result['values']['total_liabilities'], 4738)


class IncomeTests(unittest.TestCase):
    def test_alias_labels_are_read(self):
        rows = [['매출액', '5,968', '1', '1'], ['영업이익', '746', '1', '1'], ['금융원가', '300', '1', '1'], ['법인세차감전순이익(손실)', '625', '1', '1'],
                ['법인세비용(수익)', '123', '1', '1'], ['당기순이익(손실)', '502', '1', '1']]
        v = read(is_rows=rows)['values']
        self.assertEqual((v['finance_costs'], v['pretax_income'], v['income_tax_expense'], v['net_income_total']), (300, 625, 123, 502))
        for pretax in ('법인세비용차감전계속영업이익', '법인세비용차감전계속사업이익(손실)', '법인세차감전순이익'):
            self.assertEqual(read(is_rows=swap(IS, '법인세비용차감전순이익', pretax))['values']['pretax_income'], 625)
        for tax in ('법인세비용(환입)',):
            self.assertEqual(read(is_rows=swap(IS, '법인세비용', tax))['values']['income_tax_expense'], 123)
        for net in ('당기순손익', '연결당기순이익', '연결당기순이익(손실)'):
            self.assertEqual(read(is_rows=swap(IS, '당기순이익', net))['values']['net_income_total'], 502)

    def test_loss_labels_are_accepted_only_with_non_positive_amounts(self):
        loss = swap(swap(IS, '당기순이익', '당기순손실'), '법인세비용차감전순이익', '법인세비용차감전순손실')
        ok = read(is_rows=[[r[0], '(100)' if r[0] in ('당기순손실', '법인세비용차감전순손실') else r[1], r[2], r[3]] for r in loss])
        self.assertEqual((ok['values']['net_income_total'], ok['values']['pretax_income']), (-100, -100))
        bad = read(is_rows=[[r[0], '100' if r[0] in ('당기순손실', '법인세비용차감전순손실') else r[1], r[2], r[3]] for r in loss])
        self.assertNotIn('net_income_total', bad['values']);self.assertNotIn('pretax_income', bad['values'])
        self.assertEqual((bad['notes']['net_income_total'], bad['notes']['pretax_income']), ('sign_unclear', 'sign_unclear'))
        self.assertEqual(bad['values']['revenue'], 5968)

    def test_a_tax_income_label_and_continuing_operations_net_income_are_not_read(self):
        result = read(is_rows=swap(IS, '법인세비용', '법인세수익'))
        self.assertNotIn('income_tax_expense', result['values']);self.assertEqual(result['notes'].get('income_tax_expense'), 'unsupported_label')
        only = read(is_rows=swap(IS, '당기순이익', '계속영업당기순이익'))
        self.assertNotIn('net_income_total', only['values']);self.assertEqual(only['notes'], {})

    def test_a_comprehensive_income_statement_alone_supplies_the_fields(self):
        result = parse(bs(rows=BS), inc(name='연결 포괄손익계산서', rows=IS), cf(rows=CF))
        self.assertEqual(result['values'], FULL)

    def test_a_bad_amount_or_a_repeat_drops_only_that_field_and_never_the_original_values(self):
        bad = read(is_rows=swap(IS, '금융비용', '금융비용')[:2] + [['금융비용', '12a', '1', '1']] + IS[3:])
        self.assertNotIn('finance_costs', bad['values']);self.assertEqual(bad['notes']['finance_costs'], 'bad_number')
        self.assertEqual(bad['values']['revenue'], 5968);self.assertEqual(bad['values']['operating_profit'], 746)
        dup = read(is_rows=IS + [['당기순이익', '1', '1', '1']])
        self.assertNotIn('net_income_total', dup['values']);self.assertEqual(dup['notes']['net_income_total'], 'duplicate')


class CashFlowTests(unittest.TestCase):
    def test_outflows_are_stored_as_absolute_values_whatever_the_sign_notation(self):
        positive = [[r[0]] + [c.strip('()') for c in r[1:]] if r[0] in ('유형자산의 취득', '무형자산의 취득', '배당금의 지급') else r for r in CF]
        for rows in (CF, positive):
            v = read(cf_rows=rows)['values']
            self.assertEqual((v['capex_tangible'], v['capex_intangible'], v['dividends_paid']), (163, 15, 46))
        alt = read(cf_rows=swap(CF, '배당금의 지급', '배당금지급'))['values']
        self.assertEqual(alt['dividends_paid'], 46)
        self.assertEqual(read(cf_rows=swap(CF, '감가상각비', '유형자산감가상각비'))['values']['depreciation'], 200)

    def test_depreciation_like_fields_must_not_be_negative(self):
        for label in ('감가상각비', '무형자산상각비', '사용권자산상각비', '이자비용'):
            rows = [[r[0], '(5)', r[2], r[3]] if r[0] == label else r for r in CF]
            result = read(cf_rows=rows)
            field = dict(감가상각비='depreciation', 무형자산상각비='amortization', 사용권자산상각비='rou_depreciation', 이자비용='interest_expense')[label]
            with self.subTest(label=label):
                self.assertNotIn(field, result['values']);self.assertEqual(result['notes'][field], 'negative')

    def test_a_repeated_cash_flow_label_drops_the_field(self):
        result = read(cf_rows=CF + [['유형자산의 취득', '(1)', '(1)', '(1)']])
        self.assertNotIn('capex_tangible', result['values']);self.assertEqual(result['notes']['capex_tangible'], 'duplicate')
        self.assertEqual(result['values']['capex_intangible'], 15)

    def test_interest_expense_comes_from_either_statement_and_a_disagreement_drops_it(self):
        from_income = read(is_rows=IS + [['이자비용', '53', '1', '1']], cf_rows=drop(CF, '이자비용'))
        self.assertEqual(from_income['values']['interest_expense'], 53)
        same = read(is_rows=IS + [['이자비용', '53', '1', '1']])
        self.assertEqual(same['values']['interest_expense'], 53)
        differ = read(is_rows=IS + [['이자비용', '54', '1', '1']])
        self.assertNotIn('interest_expense', differ['values']);self.assertEqual(differ['notes']['interest_expense'], 'conflict')

    def test_fields_that_do_not_exist_in_the_cash_flow_statement_stay_absent(self):
        result = read(cf_rows=[CF[0]])
        for key in ('depreciation', 'amortization', 'rou_depreciation', 'interest_expense', 'capex_tangible', 'capex_intangible', 'dividends_paid'):
            self.assertNotIn(key, result['values'])
        self.assertEqual(result['values']['ocf'], 493)


class CopiesAndZipTests(unittest.TestCase):
    def test_identical_statement_copies_are_fine_and_a_disagreeing_new_field_is_dropped_without_error(self):
        same = parse(bs(rows=BS), bs(rows=BS), inc(rows=IS), cf(rows=CF))
        self.assertEqual(same['values'], FULL)
        other = [r if r[0] != '자산총계' else ['자산총계', '9,999', '1', '1'] for r in BS]
        result = parse(bs(rows=BS), bs(rows=other), inc(rows=IS), cf(rows=CF))
        self.assertNotIn('total_assets', result['values']);self.assertEqual(result['notes']['total_assets'], 'conflict')
        self.assertEqual(result['values']['equity'], 2489)

    def test_an_original_field_conflict_between_copies_still_raises(self):
        other = [r if r[0] != '자본총계' else ['자본총계', '9', '9', '9'] for r in BS]
        with self.assertRaises(ValueError):
            parse(bs(rows=BS), bs(rows=other), inc(rows=IS), cf(rows=CF))

    def test_a_zip_builds_the_record_with_the_new_values_and_drops_disagreeing_members_fields(self):
        def member(rows):
            return doc(wrap(bs(rows=rows), inc(rows=IS), cf(rows=CF))).encode('utf-8')
        other = [r if r[0] != '자산총계' else ['자산총계', '9,999', '1', '1'] for r in BS]
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('a.xml', member(BS));archive.writestr('b.xml', member(other))
        record = pit_xml.parse_document_zip(buffer.getvalue(), receipt='20260310000001', year=2025, url='opendart:document.xml')
        self.assertEqual(record['values'], {k: v for k, v in FULL.items() if k != 'total_assets'})
        single = io.BytesIO()
        with zipfile.ZipFile(single, 'w') as archive:
            archive.writestr('a.xml', member(BS))
        self.assertEqual(pit_xml.parse_document_zip(single.getvalue(), receipt='20260310000001', year=2025, url='u')['values'], FULL)


def sectioned(label, section):
    """A balance sheet with ONE borrowing-like row `label` placed in the 유동부채 or 비유동부채 section."""
    head = [['유동자산', '1', '1', '1'], ['현금및현금성자산', '216', '1', '1'], ['자산총계', '1', '1', '1'], ['부채', '', '', ''], ['유동부채', '1', '1', '1']]
    body = [[label, '7', '7', '7'], ['비유동부채', '1', '1', '1']] if section == 'current' else [['비유동부채', '1', '1', '1'], [label, '7', '7', '7']]
    return head + body + [['부채총계', '1', '1', '1'], ['자본', '', '', ''], ['자본총계', '2,489', '2,055', '1']]


class AliasAndEdgeTests(unittest.TestCase):
    BORROW_ANY = ('차입금', '사채', '전환사채', '신주인수권부사채', '차입금및사채', '사채및차입금', '교환사채')
    BORROW_CURRENT = ('단기차입금', '유동성장기차입금', '유동성사채', '단기사채', '유동성전환사채', '유동성신주인수권부사채', '유동성장기사채', '당좌차월')
    BORROW_NONCURRENT = ('장기차입금', '장기사채', '비유동차입금', '비유동사채')
    LEASE_ANY = ('리스부채',)
    LEASE_CURRENT = ('유동리스부채', '유동성리스부채')
    LEASE_NONCURRENT = ('비유동리스부채', '비유동성리스부채', '장기리스부채')

    def test_every_listed_borrowing_and_lease_alias_is_read_in_its_section(self):
        groups = ((self.BORROW_ANY, ('current', 'noncurrent'), 'borrowings'), (self.BORROW_CURRENT, ('current',), 'borrowings'),
                  (self.BORROW_NONCURRENT, ('noncurrent',), 'borrowings'), (self.LEASE_ANY, ('current', 'noncurrent'), 'lease'),
                  (self.LEASE_CURRENT, ('current',), 'lease'), (self.LEASE_NONCURRENT, ('noncurrent',), 'lease'))
        for labels, sections, family in groups:
            for label in labels:
                for section in sections:
                    with self.subTest(label=label, section=section):
                        result = read(bs_rows=sectioned(label, section))
                        self.assertEqual(result['values'].get(f'{family}_{section}'), 7, result['notes'])
                        self.assertEqual(result['notes'], {})

    def test_every_listed_label_is_refused_in_the_other_section(self):
        for labels, wrong in ((self.BORROW_CURRENT, 'noncurrent'), (self.BORROW_NONCURRENT, 'current'), (self.LEASE_CURRENT, 'noncurrent'), (self.LEASE_NONCURRENT, 'current')):
            for label in labels:
                with self.subTest(label=label):
                    result = read(bs_rows=sectioned(label, wrong))
                    self.assertEqual(list(result['notes'].values()), ['section_mismatch'])

    def test_a_borrowing_row_inside_an_asset_section_is_a_mismatch(self):
        rows = [['유동자산', '1', '1', '1'], ['단기차입금', '5', '5', '5'], ['자산총계', '1', '1', '1'], ['부채총계', '1', '1', '1'], ['자본', '', '', ''], ['자본총계', '2,489', '1', '1']]
        self.assertEqual(read(bs_rows=rows)['notes'], {'borrowings': 'section_mismatch'})

    def test_headings_and_totals_close_the_current_section(self):
        for closer, rows in (('자산총계', [['유동자산', '1', '1', '1'], ['자산총계', '1', '1', '1'], ['차입금', '5', '5', '5']]),
                             ('부채', [['유동자산', '1', '1', '1'], ['부채', '', '', ''], ['차입금', '5', '5', '5']]),
                             ('자본', [['유동부채', '1', '1', '1'], ['자본', '', '', ''], ['차입금', '5', '5', '5']])):
            with self.subTest(closer=closer):
                result = read(bs_rows=rows + [['자본총계', '2,489', '1', '1']])
                self.assertEqual(result['notes'], {'borrowings': 'section_unknown'})

    def test_heading_rows_without_amounts_and_empty_rows_are_ignored(self):
        rows = BS[:8] + [['차입금', '', '', ''], [], ['리스부채', '', '', '']] + BS[8:]
        result = read(bs_rows=rows)
        self.assertEqual(result['values'], FULL);self.assertEqual(result['notes'], {})

    def test_the_first_reason_of_a_family_is_kept(self):
        rows = BS[:9] + [['단기차입금', '1', '1', '1'], ['유동성장기차입금', '12a', '1', '1']] + BS[10:]
        self.assertEqual(read(bs_rows=rows)['notes'], {'borrowings': 'duplicate'})

    def test_too_many_amounts_is_an_amount_count_problem_and_a_zero_loss_is_accepted(self):
        rows = [r if r[0] != '금융비용' else ['금융비용', '1', '2', '3', '4'] for r in IS]
        self.assertEqual(read(is_rows=rows)['notes'], {'finance_costs': 'amount_count'})
        loss = [r if r[0] != '당기순이익' else ['당기순손실', '0', '1', '1'] for r in IS]
        self.assertEqual(read(is_rows=loss)['values']['net_income_total'], 0)

    def test_the_other_pretax_loss_label_is_read(self):
        rows = [r if r[0] != '법인세비용차감전순이익' else ['법인세차감전순손실', '(100)', '1', '1'] for r in IS]
        self.assertEqual(read(is_rows=rows)['values']['pretax_income'], -100)

    def test_a_conflict_between_any_two_of_three_copies_stays_a_conflict(self):
        other = [r if r[0] != '자산총계' else ['자산총계', '9,999', '1', '1'] for r in BS]
        for copies in ((BS, other, BS), (other, BS, BS), (BS, BS, other)):
            result = parse(bs(rows=copies[0]), bs(rows=copies[1]), bs(rows=copies[2]), inc(rows=IS), cf(rows=CF))
            self.assertNotIn('total_assets', result['values']);self.assertEqual(result['notes']['total_assets'], 'conflict')

    def test_a_bare_any_section_label_inside_an_asset_section_is_a_mismatch_and_makes_no_odd_field(self):
        for label, family in (('차입금', 'borrowings'), ('리스부채', 'lease')):
            rows = [['유동자산', '1', '1', '1'], [label, '5', '5', '5'], ['자산총계', '1', '1', '1'], ['자본', '', '', ''], ['자본총계', '2,489', '1', '1']]
            with self.subTest(label=label):
                result = read(bs_rows=rows)
                self.assertEqual(result['notes'], {family: 'section_mismatch'})
                self.assertEqual({k for k in result['values'] if family in k}, set())

    def test_a_conflict_note_is_not_replaced_by_a_later_copys_other_problem(self):
        other = [r if r[0] != '자산총계' else ['자산총계', '9,999', '1', '1'] for r in BS]
        bad = [r if r[0] != '자산총계' else ['자산총계', '12a', '1', '1'] for r in BS]
        result = parse(bs(rows=BS), bs(rows=other), bs(rows=bad), inc(rows=IS), cf(rows=CF))
        self.assertEqual(result['notes']['total_assets'], 'conflict')

    def test_blank_prior_cells_in_the_period_number_layout_do_not_hide_the_current_amount(self):
        cf_rows = [r if r[0] != '배당금의 지급' else ['배당금의 지급', '(46)', '', ''] for r in CF]
        result = read(cf_rows=cf_rows)
        self.assertEqual(result['values']['dividends_paid'], 46);self.assertEqual(result['notes'], {})
        rows = [r if r[0] != '사채' else ['사채', '40', '', ''] for r in BS]
        result = read(bs_rows=rows)
        self.assertEqual(result['values']['borrowings_noncurrent'], 340);self.assertEqual(result['notes'], {})

    def test_a_blank_current_cell_with_a_filled_later_cell_or_too_many_cells_is_an_amount_count_problem(self):
        for row in (['금융비용', '', '280', '250'], ['금융비용', '', '', '250'], ['금융비용', '300', '280', '250', '1']):
            with self.subTest(row=row):
                self.assertEqual(read(is_rows=[r if r[0] != '금융비용' else row for r in IS])['notes'], {'finance_costs': 'amount_count'})

    def test_the_older_layout_still_needs_exactly_as_many_amounts_as_columns_for_the_new_fields(self):
        rows_is = [['Ⅰ. 매출액', '7', '5,968', '4,894'], ['Ⅵ. 영업이익', '', '746', '362'], ['금융비용', '', '300', '']]
        result = pit_xml.parse_statements(doc(balance(), income(rows=rows_is), cash()), year=2025)
        self.assertNotIn('finance_costs', result['values']);self.assertEqual(result['notes'], {'finance_costs': 'amount_count'})


LIQUID_LABELS = ('당기손익-공정가치금융자산', '당기손익-공정가치측정금융자산', '기타포괄손익-공정가치금융자산', '기타포괄손익-공정가치측정금융자산', '유동금융자산', '단기투자자산', '단기매매금융자산')


def with_row(row, after='단기금융상품', rows=BS):
    at = next(i for i, r in enumerate(rows) if r[0] == after)
    return rows[:at + 1] + [row] + rows[at + 1:]


class CurrentFinancialAssetsTests(unittest.TestCase):
    def test_every_liquid_financial_asset_label_inside_current_assets_is_read(self):
        for label in LIQUID_LABELS:
            with self.subTest(label=label):
                result = read(bs_rows=with_row([label, '25', '1', '1']))
                self.assertEqual(result['values'], {**FULL, 'current_financial_assets': 25});self.assertEqual(result['notes'], {})

    def test_distinct_labels_are_summed_and_note_references_are_removed(self):
        rows = with_row(['기타포괄손익-공정가치측정금융자산 (주6,31)', '5', '1', '1'], rows=with_row(['당기손익-공정가치금융자산 (주6,24)', '25', '1', '1']))
        result = read(bs_rows=rows)
        self.assertEqual(result['values']['current_financial_assets'], 30);self.assertEqual(result['notes'], {})

    def test_the_same_labels_in_non_current_assets_are_ignored_without_a_note_and_other_financial_assets_never_count(self):
        rows = with_row(['당기손익-공정가치금융자산', '77', '1', '1'], after='비유동자산')
        result = read(bs_rows=rows)
        self.assertNotIn('current_financial_assets', result['values']);self.assertEqual(result['notes'], {})
        both = read(bs_rows=with_row(['당기손익-공정가치금융자산', '77', '1', '1'], after='비유동자산', rows=with_row(['당기손익-공정가치금융자산', '25', '1', '1'])))
        self.assertEqual(both['values']['current_financial_assets'], 25)
        for label in ('기타금융자산', '장기금융자산', '기타비유동금융자산', '금융리스채권'):
            with self.subTest(label=label):
                other = read(bs_rows=with_row([label, '99', '1', '1']))
                self.assertNotIn('current_financial_assets', other['values']);self.assertEqual(other['notes'], {})

    def test_zero_dash_and_the_absence_of_any_row(self):
        for shown in ('0', '-'):
            self.assertEqual(read(bs_rows=with_row(['유동금융자산', shown, '1', '1']))['values']['current_financial_assets'], 0)
        self.assertNotIn('current_financial_assets', read()['values'])

    def test_anomalies_drop_only_this_field(self):
        cases = {'duplicate': with_row(['단기투자자산', '5', '1', '1'], rows=with_row(['단기투자자산', '25', '1', '1'])),
                 'amount_count': with_row(['단기투자자산', '', '1', '1']), 'bad_number': with_row(['단기투자자산', '12a', '1', '1']),
                 'negative': with_row(['단기투자자산', '(5)', '1', '1'])}
        for reason, rows in cases.items():
            with self.subTest(reason=reason):
                result = read(bs_rows=rows)
                self.assertNotIn('current_financial_assets', result['values']);self.assertEqual(result['notes'], {'current_financial_assets': reason})
                self.assertEqual(result['values']['short_term_financial_instruments'], 50);self.assertEqual(result['values']['equity'], 2489)

    def test_a_row_outside_any_asset_section_is_a_section_problem(self):
        rows = [['자산', '', '', ''], ['단기투자자산', '5', '1', '1'], ['자산총계', '7,227', '1', '1'], ['자본', '', '', ''], ['자본총계', '2,489', '1', '1']]
        self.assertEqual(read(bs_rows=rows)['notes'], {'current_financial_assets': 'section_unknown'})
        in_liability = with_row(['단기투자자산', '5', '1', '1'], after='유동부채')
        self.assertEqual(read(bs_rows=in_liability)['notes'], {'current_financial_assets': 'section_mismatch'})

    def test_the_older_layout_reads_it_too(self):
        rows_bs = [['Ⅰ. 유동자산', '', '', '3,738', '', '3,036'], ['현금및현금성자산', '5', '216', '', '249', ''], ['당기손익-공정가치금융자산', '6', '25', '', '20', ''],
                   ['자산총계', '', '', '7,227', '', '6,218'], ['자본 총계', '', '', '2,489', '', '2,055']]
        result = pit_xml.parse_statements(doc(balance(rows=rows_bs), income(), cash()), year=2025)
        self.assertEqual(result['values']['current_financial_assets'], 25)


if __name__ == '__main__':unittest.main()
