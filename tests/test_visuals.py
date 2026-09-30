"""Synthetic chart math, coverage and interactive viewer regressions."""
import copy
import unittest
from streamlit.testing.v1 import AppTest
from investment import visuals as v
from tests import test_infomax_daily


class VisualTests(unittest.TestCase):
    def setUp(self):
        helper=test_infomax_daily.DailyImportTests();helper.setUp();self.snapshot=helper.convert()
        base=self.snapshot['companies'][0]
        self.rows=[]
        for i,value in enumerate([-10,0,20]):
            r=copy.deepcopy(base);r.update(code=f'90000{i+1}',name='동일 이름',market='KOSPI' if i<2 else 'KOSDAQ')
            r['metrics'].update(roe_pct=value,operating_margin_pct=value*2,market_cap_eok=100+i)
            self.rows.append(r)
        self.snapshot['companies']=self.rows

    def test_bars_keep_zero_negative_and_duplicate_names_distinct(self):
        rows=v.metric_records(self.rows,'roe_pct')
        self.assertEqual([r['value'] for r in rows],[-10,0,20])
        self.assertEqual(len({r['label'] for r in rows}),3)
        self.assertTrue(v.bar_chart(rows,'ROE (%)').to_dict()['encoding']['x']['scale']['zero'])

    def test_scatter_requires_pairs_and_retains_entity_codes(self):
        self.rows[0]['metrics']['roe_pct']=None
        self.rows[1]['metrics']['operating_margin_pct']=float('nan')
        points=v.scatter_records(self.rows,'roe_pct','operating_margin_pct')
        self.assertEqual([r['code'] for r in points],['900003'])
        spec=v.scatter_chart(points,'x','y').to_dict()
        self.assertEqual(spec['params'][0]['select']['fields'],['code'])

    def test_heatmap_recomputes_on_filter_and_never_zero_fills_missing(self):
        self.rows[1]['metrics']['roe_pct']=None
        records=v.heatmap_records(self.rows,['roe_pct'])
        self.assertEqual([r['score'] for r in records],[0,None,100])
        self.assertEqual(records[1]['value_label'],'자료 없음')
        self.assertEqual(v.heatmap_records([self.rows[0]],['roe_pct'])[0]['score'],50)
        v.heatmap_chart(records).to_dict()

    def test_waterfall_reconciles_and_groups_large_books(self):
        positions=[dict(code=f'{i:06}',name=f'가상{i}',cost_krw=100,value_krw=80 if i%2 else 130) for i in range(15)]
        rows=v.waterfall_records(positions)
        self.assertEqual(len(rows),13)
        self.assertAlmostEqual(rows[0]['amount']+sum(r['amount'] for r in rows[1:-1]),rows[-1]['amount'])
        self.assertAlmostEqual(rows[-2]['end'],sum(r['value_krw'] for r in positions))
        self.assertEqual({r['kind'] for r in rows},{'합계','이익','손실'})
        v.waterfall_chart(rows).to_dict()

    def test_partial_cost_or_price_blocks_whole_waterfall(self):
        for p in [dict(value_krw=100,cost_krw=None),dict(value_krw=None,cost_krw=100),dict(value_krw=2**54,cost_krw=1)]:
            self.assertEqual(v.waterfall_records([dict(p,code='900001',name='가상')]),[])
        self.assertEqual(v.waterfall_records([]),[])

    def test_price_chart_uses_only_explicit_observations_before_cutoff(self):
        row=self.rows[0]
        chart=v.price_chart(row,self.snapshot['meta']['price_date'])
        spec=chart.to_dict()
        self.assertTrue(spec['data']['values'])
        self.assertTrue(all(p['date']<=self.snapshot['meta']['price_date'] for p in spec['data']['values']))
        for p in row['prices']:p.pop('adjustment_basis',None)
        self.assertIsNone(v.price_chart(row,self.snapshot['meta']['price_date']))

    def test_viewer_filters_reset_and_empty_selection(self):
        source=f'from investment.visuals import render_viewer\nrender_viewer({self.snapshot!r})'
        at=AppTest.from_string(source,default_timeout=20).run()
        self.assertEqual(len(at.exception),0)
        pick=next(s for s in at.selectbox if s.label=='뷰어 시장')
        pick.select('KOSDAQ').run()
        self.assertEqual(next(m for m in at.multiselect if m.label.startswith('비교할 기업')).value,['900003'])
        next(s for s in at.selectbox if s.label=='뷰어 시장').select('전체').run()
        self.assertEqual(len(at.multiselect[0].value),3)
        at.multiselect[0].set_value([]).run()
        self.assertTrue(any('선택한 기업이 없습니다' in i.value for i in at.info))
        next(b for b in at.button if b.label=='뷰어 초기화').click().run()
        self.assertEqual(len(at.multiselect[0].value),3)
        self.assertEqual(len(at.exception),0)


if __name__=='__main__':unittest.main()
