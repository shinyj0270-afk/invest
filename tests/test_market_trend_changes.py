"""Synthetic observed-source and checkpoint contracts; no real data writes."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from investment.market_explanation import build_market_explanation
from investment.trend_checkpoints import observe_trend, summarize, compare_observations
from investment.trend_following import build_trend_following
from investment.workspace_research import build_research
from tests.test_trend_following import trend_fixture


def board(as_of='2026-10-06'):
    def row(code, rs, gap=-1, close=100, ma=90):
        return dict(code=code, name='가상 '+code, market='KOSPI', ready=True,
            cap_eok=1500, rs=rs, discovery_allowed=True, phase='돌파선 3% 이내',
            analysis=dict(pivot_gap_pct=gap), technical=dict(as_of=as_of, close=close,
                sma={'50':ma},price_strength={'eligible_count':7}))
    return dict(as_of=as_of, mode='fixture', source_note='synthetic validated source', rows=[row('A',69),row('B',80),row('C',90)])


class MarketTrendChangeTests(unittest.TestCase):
    def test_mixed_signals_and_independent_denominators(self):
        cutoff='2026-10-06'
        up=[dict(close=100+i,date='synthetic') for i in range(260)]
        down=[dict(close=400-i,date='synthetic') for i in range(260)]
        rows=[dict(code='A',market='KOSPI',ready=True),dict(code='B',market='KOSPI',ready=True),
              dict(code='C',market='KOSPI',ready=True),dict(code='D',market='KOSPI',ready=False)]
        cards=build_market_explanation(cutoff,[dict(market='KOSPI',status='ready',regime='상승 정렬')],rows,
            {'A':down,'B':down,'C':up[-70:]},{'KOSPI':up},'fixture')['markets']
        b=cards[0]['breadth']
        self.assertEqual(b['population'],4);self.assertEqual(b['valid'],3)
        self.assertEqual(b['above']['200'],{'count':0,'eligible':2,'pct':0})
        self.assertEqual(b['above']['50']['eligible'],3)
        self.assertEqual(b['change_eligible'],3)
        self.assertIn('혼합 신호',cards[0]['explanation'])
        self.assertEqual(cards[1]['breadth']['above']['200']['pct'],None)
        self.assertEqual(cards[1]['index']['status'],'pending')

    def test_missing_and_future_bars_do_not_enter_breadth(self):
        s=trend_fixture(8);research=build_research(s)
        baseline=build_trend_following(s,research)
        for r in s['companies']:r['prices'].append(dict(r['prices'][-1],date='2030-01-01',close=999999,final=False))
        self.assertEqual(build_trend_following(s,research),baseline)
        del s['companies'][-1]['prices'][-10]
        changed=build_trend_following(s,research)['market_explanation']['markets'][0]
        self.assertEqual(changed['breadth']['population'],8)
        self.assertEqual(changed['breadth']['valid'],7)

    def test_first_observation_is_not_yesterday_and_summary_is_compact(self):
        with TemporaryDirectory() as tmp:
            data=board();data['previews']={'A':[{'close':999}]*253}
            data['rows'][0]['technical']['series']=[{'close':888}]*500
            result=observe_trend(data,tmp,'2026-10-07T01:00:00Z')
            self.assertEqual(result['status'],'no_prior')
            self.assertEqual(result['new_qualified'],[]);self.assertIsNone(result['prior_as_of'])
            saved=list(Path(tmp).rglob('*.json'))[0].read_text(encoding='utf-8')
            self.assertNotIn('series',saved);self.assertNotIn('previews',saved)
            self.assertNotIn('999',saved);self.assertIn('백테스트',saved)

    def test_same_day_revision_reload_and_return_to_original_preserve_decisions(self):
        with TemporaryDirectory() as tmp:
            data=board();first=observe_trend(data,tmp)
            data['rows'][0]['rs']=70;data['rows'][1]['rs']=69
            second=observe_trend(data,tmp)
            self.assertEqual(second['revision'],2)
            self.assertEqual([r['code'] for r in second['new_qualified']],['A'])
            self.assertEqual([r['code'] for r in second['dropouts']],['B'])
            self.assertEqual(observe_trend(data,tmp),second)
            self.assertEqual(len(list(Path(tmp).rglob('*.json'))),2)
            third=observe_trend(board(),tmp)
            self.assertEqual(third['revision'],3)
            self.assertEqual(third['current_digest'],first['current_digest'])
            self.assertEqual([r['code'] for r in third['new_qualified']],['B'])
            self.assertEqual(len(list(Path(tmp).rglob('*.json'))),3)

    def test_exact_prior_observation_not_assumed_adjacent_trading_day(self):
        prior=summarize(board('2026-09-29'));current=summarize(board('2026-10-06'))
        result=compare_observations(current,prior)
        self.assertEqual(result['prior_as_of'],'2026-09-29')
        self.assertEqual(result['comparison'],'직전 저장 관측 비교')
        self.assertEqual(result['new_qualified'],[])
        self.assertEqual(compare_observations(prior,current)['status'],'no_prior')

    def test_pending_data_not_false_dropout_and_identity_not_code_only(self):
        prior=summarize(board());data=board();data['rows'][1].update(ready=False,reason='완료 가격 대기')
        data['rows'][2]['name']='가상 재사용 코드'
        result=compare_observations(summarize(data),prior)
        self.assertEqual(result['dropouts'],[])
        self.assertEqual({r['code'] for r in result['pending']},{'B','C'})
        self.assertEqual([r['code'] for r in result['new_qualified']],['C'])

    def test_filter_changes_cannot_change_historical_default_rank(self):
        with TemporaryDirectory() as tmp:
            data=board();first=observe_trend(data,tmp)
            before={p.name:p.read_bytes() for p in Path(tmp).rglob('*.json')}
            data.update(filters={'capMin':9999,'rsMin':99},default_rs=99,default_cap_eok=9999)
            self.assertEqual(observe_trend(data,tmp),first)
            self.assertEqual(before,{p.name:p.read_bytes() for p in Path(tmp).rglob('*.json')})
            record=json.loads(next(Path(tmp).rglob('*.json')).read_text(encoding='utf-8'))
            self.assertEqual([r['default_rank'] for r in record['rows'] if r['qualified']],[2,1])

    def test_missing_rank_or_cap_is_pending_not_confirmed_dropout(self):
        prior=summarize(board());data=board()
        data['rows'][1]['rs']=None;data['rows'][2]['cap_eok']=None
        result=compare_observations(summarize(data),prior)
        self.assertEqual(result['dropouts'],[])
        self.assertEqual({r['code'] for r in result['pending']},{'B','C'})

    def test_near_breakout_ma_fail_have_current_and_transition_states(self):
        prior=summarize(board());data=board();data['rows'][1].update(phase='거래량 동반 돌파',analysis={'pivot_gap_pct':1,'phase':'거래량 동반 돌파'})
        data['rows'][2]['technical']['close']=80
        result=compare_observations(summarize(data),prior)
        self.assertTrue(result['breakouts'][0]['newly_observed']);self.assertTrue(result['breakouts'][0]['volume_confirmed'])
        self.assertTrue(result['ma_fail'][0]['newly_observed'])
        self.assertFalse(result['near'][0]['newly_observed'])

    def test_corrupt_records_and_modes_cannot_supply_prior(self):
        with TemporaryDirectory() as tmp:
            observe_trend(board(),tmp)
            path=next(Path(tmp).rglob('*.json'));r=json.loads(path.read_text(encoding='utf-8'));r['rows'][0]['rs']=100
            path.write_text(json.dumps(r),encoding='utf-8')
            result=observe_trend(board('2026-10-07'),tmp)
            self.assertEqual(result['status'],'no_prior');self.assertEqual(result['unreadable_records'],1)
            data=board('2026-10-07');data['mode']='user_input'
            self.assertEqual(observe_trend(data,tmp)['status'],'no_prior')

    def test_prior_rule_records_are_reported_separately_not_as_corrupt(self):
        with TemporaryDirectory() as tmp:
            observe_trend(board(),tmp)
            path=next(Path(tmp).rglob('*.json'));r=json.loads(path.read_text(encoding='utf-8'));r['rule']='observed-default-cap1000-rs70-v1'
            path.write_text(json.dumps(r),encoding='utf-8')
            result=observe_trend(board('2026-10-07'),tmp)
            self.assertEqual(result['status'],'no_prior')
            self.assertEqual(result['unreadable_records'],0)
            self.assertEqual(result['prior_rule_records'],1)

    def test_invalid_identity_and_cutoff_rejected(self):
        data=board();data['rows'][0]['market']='wrong'
        with self.assertRaises(ValueError):summarize(data)
        data=board();data['as_of']='future'
        with self.assertRaises(ValueError):summarize(data)

if __name__=='__main__':unittest.main()
