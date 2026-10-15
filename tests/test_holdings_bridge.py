"""Synthetic market observations; never represents the user's holdings."""
import copy
import json
import subprocess
import unittest
from pathlib import Path

from investment.holdings_bridge import holdings_catalog, holdings_input, linked_dashboard
from tests import test_infomax_daily

ROOT = Path(__file__).resolve().parents[1]


class HoldingsBridgeTests(unittest.TestCase):
    def setUp(self):
        helper = test_infomax_daily.DailyImportTests()
        helper.setUp()
        self.snapshot = helper.convert()

    def test_saved_observation_without_inventing_holdings_or_review(self):
        result = holdings_input(self.snapshot, '2026-09-30')
        self.assertEqual(result['holdings'], [])
        self.assertIsNone(result['cash_krw'])
        row = result['research'][0]
        self.assertEqual(row['price_krw'], 100)
        self.assertEqual(row['price_date'], '2026-09-27')
        self.assertEqual(row['review']['thesis'], 'unknown')
        self.assertEqual(row['evidence'], [])
        self.assertIn('잠정', row['price_source']['label'])

    def naver_cache(self, code, bars, sessions=None):
        prices = [dict(date=d, close=c, final=final, venue='KRX', adjustment_basis='naver_chart_adjusted') for d, c, final in bars]
        return dict(universe=dict(schema_version='naver-universe-0.1', companies=[]),
                    history=dict(calendar=dict(sessions=sessions or [b[0] for b in bars]),
                                 histories={code: dict(symbol=code, kind='item', prices=prices)}))

    def test_newer_saved_naver_close_supplements_infomax_observation(self):
        code = holdings_input(self.snapshot, '2026-10-15')['research'][0]['code']
        cache = self.naver_cache(code, [('2026-09-27', 90, True), ('2026-10-14', 120, True), ('2026-10-15', 130, False)],
                                 sessions=['2026-09-27', '2026-10-14', '2026-10-15'])
        result = holdings_input(self.snapshot, '2026-10-15', market_cache=cache)
        row = result['research'][0]
        self.assertEqual((row['price_krw'], row['price_date']), (120, '2026-10-14'))
        self.assertEqual(row['price_source']['kind'], 'public_chart')
        self.assertIn('인포맥스 관측 2026-09-27 이후', row['price_source']['label'])
        self.assertEqual(result['market_data_as_of'], '2026-10-14')
        self.assertEqual(holdings_catalog(self.snapshot, cache, '2026-10-15')[0]['price_date'], '2026-10-14')

    def test_infomax_observation_kept_when_naver_is_not_newer_or_invalid(self):
        code = holdings_input(self.snapshot, '2026-10-15')['research'][0]['code']
        for bars in ([('2026-09-27', 90, True)], [('2026-10-14', 120, False)], [('2026-09-20', 80, True)]):
            with self.subTest(bars=bars):
                result = holdings_input(self.snapshot, '2026-10-15', market_cache=self.naver_cache(code, bars))
                self.assertEqual((result['research'][0]['price_krw'], result['research'][0]['price_date']), (100, '2026-09-27'))
                self.assertEqual(result['research'][0]['price_source']['kind'], 'local_snapshot')
        mismatch = self.naver_cache(code, [('2026-10-14', 120, True)])
        mismatch['history']['histories'][code]['symbol'] = '999999'
        self.assertEqual(holdings_input(self.snapshot, '2026-10-15', market_cache=mismatch)['research'][0]['price_date'], '2026-09-27')
        self.assertEqual(holdings_input(self.snapshot, '2026-10-15')['market_data_as_of'], self.snapshot['meta']['price_date'])

    def test_missing_prices_do_not_use_undated_metrics(self):
        del self.snapshot['companies'][0]['prices']
        result = holdings_input(self.snapshot)
        self.assertIsNone(result['research'][0]['price_krw'])
        self.assertIsNone(result['research'][0]['price_source'])

    def test_fixture_cannot_be_misrepresented_as_real(self):
        self.snapshot['meta']['data_mode'] = 'fixture'
        with self.assertRaises(ValueError):
            holdings_input(self.snapshot)

    def test_script_injection_and_input_preservation(self):
        self.snapshot['companies'][0]['name'] = '</script><script>window.injected=true</script>'
        original = copy.deepcopy(self.snapshot)
        html = linked_dashboard('<script>start()</script>', self.snapshot)
        self.assertNotIn('</script><script>window.injected', html)
        self.assertIn('\\u003c/script', html)
        self.assertEqual(self.snapshot, original)

    def test_market_to_existing_javascript_engine(self):
        market = holdings_input(self.snapshot, '2026-09-30')
        script = r'''
const fs=require('fs'),assert=require('assert/strict'),P=require('./src/portfolio_engine.js');
const market=JSON.parse(fs.readFileSync(0,'utf8')),before=JSON.stringify(market);
P.validate(market);
const input=P.clone(market);
input.holdings=[{code:market.research[0].code,quantity:2,avg_cost_krw:50,thesis_note:'manual note'}];
input.cash_krw=100;
input.research[0].review.invalidation='manual condition';
const merged=P.attachMarket(input,market);
assert.deepEqual(merged.holdings,input.holdings);
assert.equal(merged.research[0].review.invalidation,'manual condition');
let review=P.reviewHoldings(merged);
assert.equal(review.rows[0].opinion,'WAIT');
assert.equal(review.rows[0].value_krw,200);
assert.equal(review.book.total_krw,300);
merged.as_of='2026-10-10'; review=P.reviewHoldings(merged);
assert.equal(review.rows[0].value_krw,null);
assert.equal(review.rows[0].weight_pct,null);
const newer=P.clone(input);newer.research[0].price_date='2026-09-29';newer.research[0].price_krw=120;
assert.equal(P.attachMarket(newer,market).research[0].price_krw,120);
const bad=P.clone(market);bad.research[0].price_source.snapshot_id='bad';
assert.throws(()=>P.validate(bad));
assert.throws(()=>P.attachMarket(P.fixture(),market));
assert.equal(JSON.stringify(market),before);
console.log('PASS market -> holdings -> stale/missing/manual-preservation');
'''
        run = subprocess.run(['node', '-e', script], cwd=ROOT, input=json.dumps(market),
                             text=True, encoding='utf-8', capture_output=True, timeout=20)
        self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
