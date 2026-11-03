import copy
import unittest
from investment.pit_inventory import classify_title, parse_page, assemble

CORP = '00126380'
STOCK = '298040'


def row(no='20260310000001', name='사업보고서 (2025.12)', corp=CORP, stock=STOCK, dt=None):
    return dict(corp_code=corp, corp_name='가상회사', stock_code=stock, corp_cls='Y', report_nm=name, rcept_no=no,
        flr_nm='가상회사', rcept_dt=dt or no[:8], rm='')


def page(rows, no=1, total_page=1, total=None, status='000'):
    return dict(status=status, message='정상', page_no=no, page_count=100, total_count=len(rows) if total is None else total,
        total_page=total_page, list=rows)


class TitleTests(unittest.TestCase):
    def test_kinds_and_correction_prefixes_are_classified_separately(self):
        cases={'사업보고서 (2025.12)':('annual','none','2025-12'),'[기재정정]사업보고서 (2025.12)':('annual','기재정정','2025-12'),
               '[첨부정정]사업보고서 (2025.12)':('annual','첨부정정','2025-12'),'[첨부추가]사업보고서 (2025.12)':('annual','첨부추가','2025-12'),
               '반기보고서 (2025.06)':('half','none','2025-06'),'분기보고서 (2025.09)':('quarter','none','2025-09'),
               '[기재정정]분기보고서 (2025.03)':('quarter','기재정정','2025-03'),'사업결과보고서 (2025.12)':('other','none','2025-12'),'연결감사보고서 (2025.12)':('other','none','2025-12'),
               '주요사항보고서(자기주식취득결정)':('other','none',None)}
        for title,(kind,corr,period) in cases.items():
            with self.subTest(title=title):
                c=classify_title(title);self.assertEqual((c['kind'],c['correction'],c['title_period']),(kind,corr,period))

    def test_unknown_prefix_does_not_pass_as_a_plain_annual_report(self):
        c=classify_title('[기타정정]사업보고서 (2025.12)');self.assertEqual((c['kind'],c['correction']),('annual','unknown_prefix'))


class PageTests(unittest.TestCase):
    def test_a_valid_page_is_normalised_and_raw_titles_are_kept(self):
        p=parse_page(page([row()]),corp_code=CORP,stock_code=STOCK)
        self.assertEqual((p['page_no'],p['total_count'],p['total_page']),(1,1,1))
        r=p['rows'][0];self.assertEqual((r['rcept_dt'],r['report_nm'],r['kind'],r['correction']),('2026-03-10','사업보고서 (2025.12)','annual','none'))

    def test_no_data_status_is_an_empty_page_and_other_errors_raise(self):
        self.assertEqual(parse_page(page([],status='013',total=0),corp_code=CORP,stock_code=STOCK)['rows'],[])
        self.assertEqual(parse_page(page([],no=3,status='013',total=0),corp_code=CORP,stock_code=STOCK)['page_no'],3)
        for status in ('010','020','800'):
            with self.subTest(status=status),self.assertRaises(ValueError):parse_page(page([],status=status),corp_code=CORP,stock_code=STOCK)

    def test_identity_and_format_violations_raise(self):
        for bad in (row(corp='00000001'),row(stock='005930'),row(no='123'),row(dt='20260311'),row(no='20260310000001',dt='2026-03-10')):
            with self.subTest(bad=bad['rcept_no']),self.assertRaises(ValueError):parse_page(page([bad]),corp_code=CORP,stock_code=STOCK)

    def test_a_delisted_company_row_with_empty_stock_code_is_accepted_only_when_none_is_expected(self):
        parse_page(page([row(stock='')]),corp_code=CORP,stock_code=None)
        with self.assertRaises(ValueError):parse_page(page([row(stock='')]),corp_code=CORP,stock_code=STOCK)

    def test_malformed_pages_raise(self):
        for bad in ({},dict(status='000'),dict(page(()),list='x'),dict(page([]),total_count=-1),dict(page([row()]),page_no=0)):
            with self.subTest(bad=str(bad)[:30]),self.assertRaises(ValueError):parse_page(bad,corp_code=CORP,stock_code=STOCK)


class AssembleTests(unittest.TestCase):
    def pages(self):
        return [parse_page(page([row(),row(no='20260520000002',name='[기재정정]사업보고서 (2025.12)'),row(no='20250814000003',name='반기보고서 (2025.06)')],total_page=1),
            corp_code=CORP,stock_code=STOCK)]

    def test_annual_reports_are_selected_after_raw_count_validation_and_other_kinds_are_recorded_as_excluded(self):
        out=assemble(self.pages(),query=dict(corp_code=CORP,bgn_de='20230101',end_de='20261103'),collected_at='2026-11-04T00:00:00+09:00')
        self.assertEqual([r['rcept_no'] for r in out['receipts']],['20260310000001','20260520000002'])
        self.assertEqual(out['excluded'],[dict(rcept_no='20250814000003',reason='not_annual',report_nm='반기보고서 (2025.06)')])
        self.assertEqual(out['raw_count'],3);self.assertEqual(out['query']['corp_code'],CORP);self.assertEqual(out['collected_at'],'2026-11-04T00:00:00+09:00')

    def test_missing_page_or_changed_total_invalidates_the_whole_inventory(self):
        p1=parse_page(page([row()],no=1,total_page=2,total=2),corp_code=CORP,stock_code=STOCK)
        with self.assertRaisesRegex(ValueError,'누락'):assemble([p1],query={},collected_at='t')                       # page 2 missing
        other=parse_page(page([row(no='20260520000002')],no=2,total_page=2,total=9),corp_code=CORP,stock_code=STOCK)
        far=parse_page(page([row()],no=1,total_page=2,total=5),corp_code=CORP,stock_code=STOCK)
        with self.assertRaisesRegex(ValueError,'합계'):assemble([far,other],query={},collected_at='t')               # total changed between pages
        p2ok=parse_page(page([row(no='20260520000002')],no=2,total_page=2,total=2),corp_code=CORP,stock_code=STOCK)
        self.assertEqual(len(assemble([p1,p2ok],query={},collected_at='t')['receipts']),2)

    def test_filtering_before_counting_would_hide_a_missing_page_so_raw_counts_are_used(self):
        pages=[parse_page(page([row(no='20250814000003',name='반기보고서 (2025.06)')],total_page=1,total=2),corp_code=CORP,stock_code=STOCK)]
        with self.assertRaises(ValueError):assemble(pages,query={},collected_at='t')                                   # raw 1 row vs total_count 2

    def test_duplicate_receipt_numbers_are_an_error_even_when_identical(self):
        p=parse_page(page([row(),row()],total=2),corp_code=CORP,stock_code=STOCK)
        with self.assertRaises(ValueError):assemble([p],query={},collected_at='t')

    def test_pages_may_arrive_in_any_order(self):
        p1=parse_page(page([row()],no=1,total_page=2,total=2),corp_code=CORP,stock_code=STOCK)
        p2=parse_page(page([row(no='20260520000002')],no=2,total_page=2,total=2),corp_code=CORP,stock_code=STOCK)
        self.assertEqual(assemble([p2,p1],query={},collected_at='t'),assemble([p1,p2],query={},collected_at='t'))

    def test_inputs_are_not_mutated_and_an_empty_inventory_is_explicit(self):
        pages=self.pages();before=copy.deepcopy(pages);assemble(pages,query={},collected_at='t');self.assertEqual(pages,before)
        empty=parse_page(page([],status='013',total=0),corp_code=CORP,stock_code=STOCK)
        out=assemble([empty],query={},collected_at='t');self.assertEqual((out['receipts'],out['raw_count']),([],0))


if __name__=='__main__':unittest.main()
