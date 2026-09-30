"""Synthetic market/industry lists only, with no live requests."""
import copy
import json
import unittest

from investment.naver_universe import attach_industries, classify, fetch_listing, listing_url, normalize


TIME = '2026-09-30T14:00:00+09:00'


def raw(code='900000', name='가상제조', market='0', **changes):
    value = dict(itemcode=code, itemname=name, sosok=market, type='ST', nowPrice='10000',
        marketSum='100000000000', eps='1000', per='10', pbr='2', roe='15', roa='10',
        propertyTotal='1000', debtTotal='400', sales='500', operatingProfit='100',
        salesIncreasingRate='20', operatingProfitIncreasingRate='15', marketStatus='OPEN')
    value.update(changes)
    return value


class Session:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        payload = next(self.responses)
        class Response:
            status_code = 200
            content = b'{}'
            def json(self): return payload
        return Response()


class NaverUniverseTests(unittest.TestCase):
    def test_exploratory_arithmetic_keeps_period_and_quote_unknown(self):
        row = normalize(raw(), 'KOSPI', TIME, '기계')
        self.assertEqual(row['metrics']['operating_margin_pct'], 20)
        self.assertAlmostEqual(row['metrics']['debt_ratio_pct'], 400/600*100)
        self.assertEqual(row['metrics']['market_cap_eok'], 1000)
        self.assertEqual(row['metrics']['per'], 10)
        self.assertEqual(row['eligibility'], 'candidate')
        self.assertFalse(row['classification_verified'])
        self.assertIsNone(row['financial_period'])
        self.assertIsNone(row['financial_basis'])
        self.assertIsNone(row['price_date'])
        self.assertFalse(row['final'])
        self.assertEqual(row['status'], 'reference_only')

    def test_no_guess_from_code_or_missing_industry(self):
        row = normalize(raw(), 'KOSPI', TIME)
        self.assertEqual(row['eligibility'], 'unknown')
        self.assertFalse(row['classification_verified'])
        row = normalize(raw(type=None), 'KOSPI', TIME, '기계')
        self.assertEqual(row['eligibility'], 'unknown')
        row = normalize(raw(code='9000A0'), 'KOSPI', TIME, '기계')
        self.assertEqual(row['code'], '9000A0')

    def test_known_non_main_instruments_and_finance_excluded(self):
        for patch, industry in ((dict(name='가상제조우'), '기계'), (dict(name='가상2우B'), '기계'),
            (dict(name='가상스팩1호'), '창업투자'), (dict(name='가상리츠'), '부동산'),
            (dict(type='EF'), '기타'), (dict(type='EN'), '기타'), ({}, '은행'), ({}, '손해보험'),
            ({}, '증권'), ({}, '기타금융'), ({}, '창업투자')):
            with self.subTest(patch=patch, industry=industry):
                data = raw(name=patch.get('name', '가상제조'), **{k:v for k,v in patch.items() if k != 'name'})
                self.assertEqual(normalize(data, 'KOSPI', TIME, industry)['eligibility'], 'excluded')

    def test_loss_negative_equity_missing_and_zero(self):
        for patch in (dict(eps='-1'), dict(eps='0'), dict(eps=None), dict(per='-1')):
            self.assertIsNone(normalize(raw(**patch), 'KOSPI', TIME)['metrics']['per'])
        for patch in (dict(propertyTotal='300'), dict(propertyTotal='400'), dict(propertyTotal=None), dict(pbr='0')):
            self.assertIsNone(normalize(raw(**patch), 'KOSPI', TIME)['metrics']['pbr'])
        for sales in ('0', '-5', None, 'N/A'):
            self.assertIsNone(normalize(raw(sales=sales), 'KOSPI', TIME)['metrics']['operating_margin_pct'])
        self.assertIsNone(normalize(raw(debtTotal='-1'), 'KOSPI', TIME)['metrics']['debt_ratio_pct'])

    def test_private_unknown_fields_not_carried_forward(self):
        row = normalize(raw(api_key='not-real', holdings=[1], nowPrice='NaN', roe=True), 'KOSPI', TIME)
        self.assertNotIn('not-real', json.dumps(row))
        self.assertNotIn('holdings', row)
        self.assertIsNone(row['metrics']['price'])
        self.assertIsNone(row['metrics']['roe_pct'])

    def test_invalid_identity_market_timestamp_and_pagination(self):
        for data in (raw(code='../bad'), raw(market='1'), raw(name='')):
            with self.assertRaises(ValueError): normalize(data, 'KOSPI', TIME)
        with self.assertRaises(ValueError): normalize(raw(), 'KOSPI', '2026-09-30T14:00:00')
        with self.assertRaises(ValueError): listing_url('US')
        with self.assertRaises(ValueError): listing_url('KOSPI', -1)
        with self.assertRaises(ValueError): listing_url('KOSPI', 0, 101)

    def test_market_paging_and_duplicates_do_not_create_extra_companies(self):
        session = Session([[raw(), raw('900010')], [raw('900010')], [raw('900020', market='1')]])
        result = fetch_listing(session=session, page_size=2, pause=0)
        self.assertEqual(len(result['companies']), 3)
        self.assertEqual(result['market_counts'], {'KOSPI':2, 'KOSDAQ':1})
        self.assertEqual(result['pagination']['KOSPI']['duplicate_count'], 1)
        self.assertTrue(result['pagination_complete'])
        self.assertEqual(len(session.calls), 3)
        self.assertIn('startIdx=1', session.calls[1])

    def test_bounded_or_invalid_listing_is_not_reported_complete(self):
        result = fetch_listing(markets=['KOSPI'], session=Session([[raw()]]), page_size=1, max_pages=1, pause=0)
        self.assertFalse(result['pagination_complete'])
        result = fetch_listing(markets=['KOSPI'], session=Session([{}]), pause=0)
        self.assertFalse(result['pagination_complete'])
        self.assertTrue(result['errors'])
        self.assertEqual(result['companies'], [])

    def test_bulk_industry_mapping_preserves_source_and_excludes_finance(self):
        bundle = dict(companies=[normalize(raw(), 'KOSPI', TIME), normalize(raw('900010'), 'KOSPI', TIME)], errors=[])
        before = copy.deepcopy(bundle)
        response = [[dict(no='1',name='기계'), dict(no='2',name='은행')],
                    [raw()], [raw('900010')]]
        output = attach_industries(bundle, session=Session(response), pause=0)
        self.assertEqual(bundle, before)
        self.assertEqual(output['industry_mapped_count'], 2)
        self.assertEqual(output['companies'][0]['eligibility'], 'candidate')
        self.assertEqual(output['companies'][1]['eligibility'], 'excluded')
        self.assertEqual(output['companies'][1]['industry'], '은행')

    def test_industry_conflict_and_missing_classification_remain_unknown(self):
        bundle = dict(companies=[normalize(raw(), 'KOSPI', TIME), normalize(raw('900010'), 'KOSPI', TIME)], errors=[])
        output = attach_industries(bundle, session=Session([[dict(no='1',name='기계'),dict(no='2',name='화학')], [raw()], [raw()]]), pause=0)
        self.assertTrue(output['companies'][0]['industry_conflict'])
        self.assertEqual(output['companies'][0]['eligibility'], 'unknown')
        self.assertEqual(output['companies'][1]['eligibility'], 'unknown')


if __name__ == '__main__':
    unittest.main()
