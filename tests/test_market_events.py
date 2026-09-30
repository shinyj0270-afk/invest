"""Offline event pipeline checks. Every event here is explicitly synthetic."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from investment.adapters import SetupPending
from investment.market_events import (KST, EventStore, dart_items, import_events,
                                      refresh_events, samsung_items)
from investment.store import Store

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 30, 9, tzinfo=KST)
ITEM = dict(code='005930', kind='news', title='가상 검증용 실적 발표', source='가상 출처',
            url='https://example.invalid/test', published_on='2026-09-29')


class MarketEventTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(self.temp.name, 'home', 'user_input')
        self.events = EventStore(self.store)

    def test_duplicate_and_changed_version_require_review_again(self):
        self.assertEqual(self.events.ingest([ITEM], ['005930'], NOW), 1)
        first = self.events.list('005930', '2026-09-30')[0]
        self.events.mark_reviewed(first['version'])
        self.assertEqual(self.events.ingest([ITEM], ['005930'], NOW), 0)
        self.assertEqual(self.events.pending(['005930'], '2026-09-30')['005930'], [])
        changed = dict(ITEM, title='가상 검증용 [정정] 실적 발표')
        self.events.ingest([changed], ['005930'], NOW+timedelta(minutes=1))
        rows = self.events.list('005930', '2026-09-30')
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['correction'])
        self.assertFalse(rows[0]['reviewed'])
        self.assertEqual(rows[0]['id'], first['id'])
        self.assertEqual(len(self.events.pending(['005930'], '2026-09-30')['005930']), 1)

    def test_first_seen_and_publication_are_separate(self):
        self.events.ingest([ITEM], ['005930'], NOW)
        self.assertEqual(self.events.list('005930', '2026-09-29'), [])
        row = self.events.list('005930', '2026-09-30')[0]
        self.assertIsNone(row['published_at'])
        self.assertEqual(row['first_seen_at'], NOW.isoformat())

    def test_invalid_source_batch_rolls_back(self):
        for extra in (dict(url='javascript:alert(1)'), dict(published_on='2026-10-01'),
                      dict(code='000660'), dict(title=None),
                      dict(published_at='2026-09-29T12:00:00')):
            with self.subTest(extra=extra), self.assertRaises((ValueError, TypeError)):
                self.events.ingest([ITEM, dict(ITEM, **extra)], ['005930'], NOW)
            self.assertEqual(self.events.list('005930', '2026-09-30'), [])

    def test_failure_preserves_cache_and_sanitizes_error(self):
        self.events.ingest([ITEM], ['005930'], NOW)
        def fail():
            raise RuntimeError('private credential must never be logged')
        result = refresh_events(ROOT, self.store, ['005930'], {'news':fail}, NOW)
        self.assertEqual(result['status'], 'unavailable')
        self.assertNotIn('credential', json.dumps(result))
        self.assertEqual(len(self.events.list('005930', '2026-09-30')), 1)

    def test_partial_success_does_not_claim_complete_coverage(self):
        def pending():
            raise SetupPending('key missing')
        result = refresh_events(ROOT, self.store, ['005930'], {'news':lambda:[ITEM], 'dart':pending}, NOW)
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['added'], 1)
        self.assertEqual(result['sources']['dart']['status'], 'setup_pending')

    def test_dart_exact_stock_mapping_and_day_precision(self):
        raw = dict(stock_code='005930', rcept_no='20260929000001', rcept_dt='20260929',
                   report_nm='가상 [정정] 공급계약')
        items = dart_items([raw, dict(raw, stock_code='000660')], '005930')
        self.assertEqual(len(items), 1)
        self.events.ingest(items, ['005930'], NOW)
        row = self.events.list('005930', '2026-09-30')[0]
        self.assertTrue(row['needs_review'])
        self.assertTrue(row['correction'])
        self.assertIsNone(row['published_at'])
        self.assertEqual(row['published_on'], '2026-09-29')

    def test_configured_dart_uses_existing_reader_and_correction_inclusive_range(self):
        root=Path(self.temp.name)
        (root/'config').mkdir()
        (root/'config/local.json').write_text(json.dumps(dict(profile='home',
            enabled_data_adapters=['dart'],market_events={'dart_corp_codes':{'000660':'12345678'}})),encoding='utf-8')
        (root/'config/runtime.local.json').write_text(json.dumps(dict(profile='home',permissions={'dart':True})),encoding='utf-8')
        # Explicit synthetic corp code and mocked Reader: no credentials/network.
        raw=dict(stock_code='000660',rcept_no='20260929000001',rcept_dt='20260929',report_nm='가상 공시')
        with patch('investment.market_events.Reader') as reader:
            reader.return_value.dart.return_value=[raw]
            result=refresh_events(root,self.store,['000660'],now=NOW)
            args=reader.return_value.dart.call_args.args
        self.assertEqual(result['status'],'complete')
        self.assertEqual(args[0],'disclosures')
        self.assertEqual(args[1]['last_reprt_at'],'N')
        self.assertEqual(args[1]['bgn_de'],'20260831')
        self.assertEqual(args[1]['end_de'],'20260930')

    def test_rss_timezone_and_bounded_parser(self):
        raw = b'<rss><channel><item><title>Synthetic test</title><link>https://news.samsung.com/kr/test</link><pubDate>Tue, 29 Sep 2026 16:00:00 +0000</pubDate></item></channel></rss>'
        items = samsung_items(raw)
        self.assertEqual(items[0]['published_on'], '2026-09-30')
        self.events.ingest(items, ['005930'], NOW)
        self.assertEqual(self.events.list('005930', '2026-09-30')[0]['published_at'], '2026-09-30T01:00:00+09:00')
        for bad in (b'<!DOCTYPE rss>'+raw, b'x'*(2*1024*1024+1),
                    raw.replace(b'https://news.samsung.com', b'https://example.invalid')):
            with self.assertRaises(ValueError):
                samsung_items(bad)

    def test_manual_import_does_not_trust_review_or_opinion_flags(self):
        payload = dict(schema_version='market-events-0.1',data_mode='user_input',
                       items=[dict(ITEM, reviewed=True, needs_review=False, opinion='BUY')])
        import_events(payload,self.events,['005930'],NOW)
        self.assertEqual(len(self.events.pending(['005930'], '2026-09-30')['005930']),1)
        payload['data_mode']='fixture'
        with self.assertRaises(ValueError):
            import_events(payload,self.events,['005930'],NOW)

    def test_pipeline_to_holdings_and_portfolio_review(self):
        from investment.holdings_bridge import holdings_input, linked_dashboard
        from tests.test_infomax_daily import DailyImportTests
        helper=DailyImportTests(); helper.setUp(); snapshot=helper.convert()
        code=snapshot['companies'][0]['code']
        self.events.ingest([dict(ITEM,code=code,title='가상 실적 </script><script>alert(1)</script>')], [code], NOW)
        pending=self.events.pending([code],'2026-09-30')
        market=holdings_input(snapshot,'2026-09-30',events=pending)
        self.assertEqual(market['research'][0]['pending_events'],pending[code])
        from tools.verify_portfolio_data import verify
        checked=verify(snapshot,as_of='2026-09-30',events=pending)
        self.assertIn('주요 공시·뉴스 재검토 필요',checked['candidates'][0]['reasons'])
        html=linked_dashboard('<script>start()</script>',snapshot,events=pending)
        self.assertNotIn('</script><script>alert(1)',html)
        script=r'''
const P=require('./src/portfolio_engine.js'),assert=require('assert/strict'),fs=require('fs');
const market=JSON.parse(fs.readFileSync(0,'utf8'));P.validate(market);
const x=P.fixture(),r=x.research[0],p=P.cleanPolicy({policyConfirmed:true,stressLossLimitPct:25});
assert.equal(P.companyReview(r,x.as_of,p).opinion,'HOLD');
r.pending_events=market.research[0].pending_events;
assert.equal(P.companyReview(r,x.as_of,p).opinion,'HOLD'); // Future news not yet available.
x.as_of='2026-09-30';for(const row of x.research)row.price_date=x.as_of;
assert.equal(P.companyReview(r,x.as_of,p).opinion,'WAIT');
assert.equal(P.candidateChecks(x,p)[0].ready,false);
assert(!P.propose(x,p).items.some(row=>row.code===r.code));
r.review.thesis='broken';assert.equal(P.companyReview(r,x.as_of,p).opinion,'SELL');
r.review.thesis='intact';r.pending_events=[];
assert.equal(P.companyReview(r,x.as_of,p).opinion,'HOLD');
const old=P.clone(market);old.research[0].price_date='2026-09-30';
const cleared=P.clone(market);cleared.research[0].pending_events=[];
assert.equal(P.attachMarket(old,cleared).research[0].pending_events.length,0);
assert.equal(P.attachMarket(old,cleared).research[0].price_date,'2026-09-30');
r.pending_events=[{id:'bad',title:'bad',url:'javascript:alert(1)',published_on:'2026-09-30'}];
assert.throws(()=>P.validate(x));
'''
        run=subprocess.run(['node','-e',script],cwd=ROOT,input=json.dumps(market),
                           text=True,encoding='utf-8',capture_output=True,timeout=20)
        self.assertEqual(run.returncode,0,run.stderr)

    def test_panel_marks_review_and_keeps_network_failure_visible(self):
        from streamlit.testing.v1 import AppTest
        self.events.ingest([ITEM],['005930'],NOW)
        source=f'''
from investment.events_ui import render_events
from investment.store import Store
from pathlib import Path
render_events(Path({str(ROOT)!r}),Store({self.temp.name!r},'home','user_input'),['005930'],'005930')
'''
        at=AppTest.from_string(source,default_timeout=20).run()
        self.assertEqual(len(at.exception),0)
        next(b for b in at.button if b.label=='원문·투자 논리 검토 완료').click().run()
        self.assertEqual(len(at.exception),0)
        self.assertEqual(self.events.pending(['005930'])['005930'],[])
        self.assertTrue(any(b.label=='확인 취소' for b in at.button))
        with patch('investment.events_ui.refresh_events',side_effect=RuntimeError('private detail')):
            next(b for b in at.button if b.label=='공시·뉴스 새로고침').click().run()
        self.assertEqual(len(at.exception),0)
        self.assertTrue(any('RuntimeError' in w.value for w in at.warning))
        self.assertFalse(any('private detail' in w.value for w in at.warning))


if __name__=='__main__':
    unittest.main()
