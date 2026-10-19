import copy
import unittest
from investment.nice_financial import parse_finance, resolve_company


class NiceFinancialTests(unittest.TestCase):
    def sample(self):
        dates=['2021.12.31','2022.12.31','2023.12.31','2024.12.31','2025.12.31','2025.06.30','2026.06.30']
        return {'list': {'header': {'accountName':'계정명(억원)', **{f'a{i}':d+'<br/>(K-IFRS)' for i,d in enumerate(dates)}},
            'data':[{'accountName':'순차입금','screenExpressUnitCode':'4',**{f'a{i}':'-1,000' for i in range(7)}}]}}

    def parse(self, raw):
        return parse_finance(raw,'900000','가상기업','CFS','1234567',12,'2026-10-19T00:00:00+00:00')

    def test_annual_only_preserves_negative_net_debt(self):
        result=self.parse(self.sample())
        self.assertEqual(len(result['columns']),5)
        self.assertEqual(result['columns'][-1]['values']['net_borrowings'],-1000)

    def test_unit_duplicate_and_invalid_number_rejected(self):
        for mutation in ('unit','duplicate','number','period'):
            raw=self.sample()
            if mutation=='unit':raw['list']['data'][0]['screenExpressUnitCode']='9'
            if mutation=='duplicate':raw['list']['data'].append(copy.deepcopy(raw['list']['data'][0]))
            if mutation=='number':raw['list']['data'][0]['a0']='NaN'
            if mutation=='period':raw['list']['header']['a0']='2021.12.31(E)'
            with self.assertRaises(ValueError):self.parse(raw)

    def test_identity_is_exact_and_unique(self):
        html='<th>기업명</th><tbody><tr><td>에스케이하이닉스(주)</td><td>A</td><td>B</td><td>C</td><td>D</td><td>12</td></tr></tbody>/company/companyMajorFinance.do?cmpCd=1670352'
        self.assertEqual(resolve_company(html,'SK하이닉스')[0],'1670352')
        with self.assertRaises(ValueError):resolve_company(html,'SK')
        with self.assertRaises(ValueError):resolve_company(html+'/company/companyMajorFinance.do?cmpCd=1111111','SK하이닉스')


if __name__=='__main__':unittest.main()
