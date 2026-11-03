import copy
import unittest
from investment.pit_inventory import classify_title, parse_page, assemble

CORP = '00126380'
STOCK = '298040'


def row(no='20260310000001', name='사업보고서 (2025.12)', corp=CORP, stock=STOCK, dt=None):
    return dict(corp_code=corp, corp_name='가상회사', stock_code=stock, corp_cls='Y', report_nm=name, rcept_no=no,
        flr_nm='가상회사', rcept_dt=dt or no[:8], rm='')


def page(rows, no=1, total_page=1, total=None, status='000', count=100):
    return dict(status=status, message='정상', page_no=no, page_count=count, total_count=len(rows) if total is None else total,
        total_page=total_page, list=rows)


class TitleTests(unittest.TestCase):
    def test_kinds_and_correction_prefixes_are_classified_separately(self):
        cases = {'사업보고서 (2025.12)': ('annual', 'none', '2025-12'), '[기재정정]사업보고서 (2025.12)': ('annual', '기재정정', '2025-12'),
            '[첨부정정]사업보고서 (2025.12)': ('annual', '첨부정정', '2025-12'), '[첨부추가]사업보고서 (2025.12)': ('annual', '첨부추가', '2025-12'),
            '반기보고서 (2025.06)': ('half', 'none', '2025-06'), '분기보고서 (2025.09)': ('quarter', 'none', '2025-09'),
            '[기재정정]분기보고서 (2025.03)': ('quarter', '기재정정', '2025-03'), '[기재정정] 사업보고서 (2025.12)': ('annual', '기재정정', '2025-12'),
            '사업보고서(2025.12)': ('annual', 'none', '2025-12'), '사업보고서': ('annual', 'none', None),
            '연결감사보고서 (2025.12)': ('other', 'none', None), '주요사항보고서(자기주식취득결정)': ('other', 'none', None),
            '사업결과보고서 (2025.12)': ('other', 'none', None)}
        for title, (kind, corr, period) in cases.items():
            with self.subTest(title=title):
                c = classify_title(title);self.assertEqual((c['kind'], c['correction'], c['title_period']), (kind, corr, period))

    def test_doubtful_annual_titles_are_uncertain_not_annual_and_not_dropped(self):
        for title in ('사업보고서 설명자료', '사업보고서 (2025.99)', '사업보고서 (2025.00)', '[기타정정]사업보고서 (2025.12)', '[기재정정]사업보고서 (2025.12) 추가'):
            with self.subTest(title=title):self.assertEqual(classify_title(title)['kind'], 'uncertain')

    def test_unknown_prefix_keeps_its_name_in_the_correction_field(self):
        self.assertEqual(classify_title('[기타정정]사업보고서 (2025.12)')['correction'], 'unknown_prefix')


class PageTests(unittest.TestCase):
    def test_a_valid_page_is_normalised_and_raw_titles_are_kept(self):
        p = parse_page(page([row()]), corp_code=CORP, stock_code=STOCK)
        self.assertEqual((p['page_no'], p['total_count'], p['total_page']), (1, 1, 1))
        r = p['rows'][0];self.assertEqual((r['rcept_dt'], r['report_nm'], r['kind'], r['correction']), ('2026-03-10', '사업보고서 (2025.12)', 'annual', 'none'))

    def test_no_data_status_is_an_empty_page_and_other_errors_raise(self):
        self.assertEqual(parse_page(page([], status='013', total=0), corp_code=CORP, stock_code=STOCK)['rows'], [])
        self.assertEqual(parse_page(page([], no=3, status='013', total=0), corp_code=CORP, stock_code=STOCK)['page_no'], 3)
        for status in ('010', '020', '800'):
            with self.subTest(status=status), self.assertRaises(ValueError):parse_page(page([], status=status), corp_code=CORP, stock_code=STOCK)

    def test_a_no_data_status_that_carries_data_is_contradictory_and_rejected(self):
        with self.assertRaises(ValueError):parse_page(page([row()], status='013', total=100, total_page=4), corp_code=CORP, stock_code=STOCK)
        with self.assertRaises(ValueError):parse_page(page([], status='013', total=7), corp_code=CORP, stock_code=STOCK)
        omitted = dict(status='013', message='없음');self.assertEqual(parse_page(omitted, corp_code=CORP, stock_code=STOCK)['rows'], [])

    def test_page_size_total_page_and_row_counts_must_agree(self):
        bad = (page([row(), row(no='20260520000002')], count=1),                                    # two rows on a page of size one
               page([row()], total=2, total_page=1, count=1),                                          # total_page should be 2
               page([row()], no=1, total=3, total_page=3, count=2),                                    # non-last page should hold two rows
               page([row()], total=5, total_page=1, count=100))                                        # last page should hold all five rows
        for case in bad:
            with self.subTest(case=str(case)[:40]), self.assertRaises(ValueError):parse_page(case, corp_code=CORP, stock_code=STOCK)
        good = page([row(no='20260520000002')], no=2, total=2, total_page=2, count=1)
        self.assertEqual(len(parse_page(good, corp_code=CORP, stock_code=STOCK)['rows']), 1)

    def test_identity_and_format_violations_raise(self):
        for bad in (row(corp='00000001'), row(stock='005930'), row(no='123'), row(dt='20260311'), row(no='20260310000001', dt='2026-03-10'),
                    row(no='2026031000001'), row(no='202603100000001'), row(no='20260230000001'), row(no='20261310000001')):
            with self.subTest(bad=bad['rcept_no'] + bad['rcept_dt']), self.assertRaises(ValueError):parse_page(page([bad]), corp_code=CORP, stock_code=STOCK)

    def test_a_delisted_company_row_with_empty_stock_code_is_accepted_only_when_none_is_expected(self):
        parse_page(page([row(stock='')]), corp_code=CORP, stock_code=None)
        with self.assertRaises(ValueError):parse_page(page([row(stock='')]), corp_code=CORP, stock_code=STOCK)

    def test_malformed_pages_raise(self):
        for bad in ({}, dict(status='000'), dict(page(()), list='x'), dict(page([]), total_count=-1), dict(page([row()]), page_no=0), dict(page([row()]), page_count=0)):
            with self.subTest(bad=str(bad)[:30]), self.assertRaises(ValueError):parse_page(bad, corp_code=CORP, stock_code=STOCK)


class AssembleTests(unittest.TestCase):
    def pages(self):
        return [parse_page(page([row(), row(no='20260520000002', name='[기재정정]사업보고서 (2025.12)'), row(no='20250814000003', name='반기보고서 (2025.06)'),
            row(no='20260601000004', name='사업보고서 설명자료')], total_page=1), corp_code=CORP, stock_code=STOCK)]

    def test_annual_reports_are_selected_after_raw_count_validation_and_doubtful_titles_are_listed(self):
        out = assemble(self.pages(), query=dict(corp_code=CORP, bgn_de='20230101', end_de='20261103'), collected_at='2026-11-04T00:00:00+09:00')
        self.assertEqual([r['rcept_no'] for r in out['receipts']], ['20260310000001', '20260520000002'])
        self.assertEqual(out['excluded'], [dict(rcept_no='20250814000003', reason='not_annual', report_nm='반기보고서 (2025.06)')])
        self.assertEqual([(u['rcept_no'], u['reason']) for u in out['uncertain']], [('20260601000004', 'uncertain_title')])
        self.assertEqual(out['raw_count'], 4);self.assertEqual(out['query']['corp_code'], CORP);self.assertEqual(out['collected_at'], '2026-11-04T00:00:00+09:00')

    def test_missing_page_or_changed_total_invalidates_the_whole_inventory(self):
        p1 = parse_page(page([row()], no=1, total_page=2, total=2, count=1), corp_code=CORP, stock_code=STOCK)
        with self.assertRaisesRegex(ValueError, '누락'):assemble([p1], query={}, collected_at='t')                  # page 2 missing
        q1 = parse_page(page([row()], no=1, total_page=2, total=2, count=1), corp_code=CORP, stock_code=STOCK)
        q2 = parse_page(page([row(no='20260520000002')], no=2, total_page=3, total=3, count=1), corp_code=CORP, stock_code=STOCK)
        with self.assertRaisesRegex(ValueError, '합계'):assemble([q1, q2], query={}, collected_at='t')              # totals differ between pages
        p2ok = parse_page(page([row(no='20260520000002')], no=2, total_page=2, total=2, count=1), corp_code=CORP, stock_code=STOCK)
        self.assertEqual(len(assemble([p1, p2ok], query={}, collected_at='t')['receipts']), 2)

    def test_a_missing_row_is_caught_even_when_the_missing_data_would_have_been_filtered_out(self):
        with self.assertRaises(ValueError):                                                                         # raw 1 row vs total_count 2
            parse_page(page([row(no='20250814000003', name='반기보고서 (2025.06)')], total=2, total_page=1), corp_code=CORP, stock_code=STOCK)

    def test_duplicate_receipt_numbers_are_an_error_even_when_identical(self):
        p = parse_page(page([row(), row()], total=2), corp_code=CORP, stock_code=STOCK)
        with self.assertRaises(ValueError):assemble([p], query={}, collected_at='t')

    def test_duplicate_page_numbers_are_an_error(self):
        p1 = parse_page(page([row()], no=1, total_page=2, total=2, count=1), corp_code=CORP, stock_code=STOCK)
        with self.assertRaises(ValueError):assemble([p1, p1], query={}, collected_at='t')

    def test_pages_may_arrive_in_any_order(self):
        p1 = parse_page(page([row()], no=1, total_page=2, total=2, count=1), corp_code=CORP, stock_code=STOCK)
        p2 = parse_page(page([row(no='20260520000002')], no=2, total_page=2, total=2, count=1), corp_code=CORP, stock_code=STOCK)
        self.assertEqual(assemble([p2, p1], query={}, collected_at='t'), assemble([p1, p2], query={}, collected_at='t'))

    def test_inputs_are_not_mutated_and_an_empty_inventory_is_explicit(self):
        pages = self.pages();before = copy.deepcopy(pages);assemble(pages, query={}, collected_at='t');self.assertEqual(pages, before)
        empty = parse_page(page([], status='013', total=0), corp_code=CORP, stock_code=STOCK)
        out = assemble([empty], query={}, collected_at='t');self.assertEqual((out['receipts'], out['raw_count'], out['uncertain']), ([], 0, []))


if __name__ == '__main__':unittest.main()
