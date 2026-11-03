import io
import math
import random
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from investment.market_history import benchmark_calendar
from investment.market_discovery import technical
from investment.trial_log import read_all
from tools.threshold_sensitivity_report import BASE
from tools.trend_sensitivity_report import (TREND_BASE, terms, trend_variants, price_status, eligible_records, parity, trend_sensitivity, trial_entries, record_trials, render, label, main)

DAYS=300


def sessions(count=DAYS):
    out=[];d=date(2025,1,2)
    while len(out)<count:
        if d.weekday()<5:out.append(d.isoformat())
        d+=timedelta(days=1)
    return out


def walk(days,drift,noise,rng,start=100.0):
    out=[];x=start
    for _ in days:
        x*=math.exp(drift+rng.gauss(0,noise));out.append(round(x,4))
    return out


def bars(days,closes,index=False):
    return [dict(date=d,close=c,open=c,high=c,low=c,volume=1000,turnover=None,final=True,venue='KRX',no_trade=False,
        adjustment_basis='index_level' if index else 'naver_chart_adjusted') for d,c in zip(days,closes)]


def market(n=60,seed=3,bench_drift=0.0004):
    rng=random.Random(seed);days=sessions()
    bench={s:dict(symbol=s,kind='index',prices=bars(days,walk(days,bench_drift,0.007,rng),True),source=dict(url='x://'+s)) for s in ('KOSPI','KOSDAQ')}
    for s in bench:bench[s]['prices']=bench['KOSPI']['prices'] if s=='KOSPI' else [dict(p) for p in bench['KOSPI']['prices']]
    hist={str(900000+i):dict(symbol=str(900000+i),kind='item',prices=bars(days,walk(days,rng.uniform(-0.002,0.0045),0.015,rng))) for i in range(n)}
    return dict(benchmarks=bench,histories=hist),benchmark_calendar(bench)


def cache_of(history):
    return dict(history=history)


def row(code,status='fail'):
    return dict(code=code,rs=80,short=60,close=100,sma200=90,status=status,growth=20,margin=5,roe=10,debt=50,ocf=10)


class TrendSensitivityTests(unittest.TestCase):
    def test_baseline_status_matches_technical_exactly(self):
        history,cal=market();elig=eligible_records(history,cal,{})
        self.assertGreater(len(elig),30)
        for code,e in elig.items():
            self.assertEqual(price_status(e,TREND_BASE),technical(history['histories'][code],history['benchmarks']['KOSPI'],cal,include_series=False)['price_trend_status'])
        statuses={price_status(e,TREND_BASE) for e in elig.values()};self.assertEqual(statuses,{'pass','fail'})   # both outcomes exist, so the parity check has teeth
        self.assertEqual(parity(elig),0)

    def test_dropping_a_sub_condition_never_removes_a_pass(self):
        history,cal=market();elig=eligible_records(history,cal,{})
        base={c for c,e in elig.items() if price_status(e,TREND_BASE)=='pass'}
        for drop in ('stack','slope','return','rs'):
            got={c for c,e in elig.items() if price_status(e,{**TREND_BASE,'drop':drop})=='pass'}
            self.assertTrue(base<=got,drop)
        loose={c for c,e in elig.items() if price_status(e,{**TREND_BASE,'rs_min':-50.0})=='pass'};self.assertTrue(base<=loose)
        strict={c for c,e in elig.items() if price_status(e,{**TREND_BASE,'rs_min':50.0})=='pass'};self.assertTrue(strict<=base)

    def test_every_constant_and_sub_condition_can_decide_the_status_and_matches_technical(self):
        variants=[{**TREND_BASE,'drop':d} for d in ('stack','slope','return','rs')]+[{**TREND_BASE,k:v} for k,vals in (('sma_a',(40,60)),('sma_b',(120,180)),('sma_c',(180,220)),('ret_lag',(105,147)),('rs_lag',(105,147)),('rs_min',(-5.0,5.0))) for v in vals]
        flips=[0]*len(variants);days=sessions()
        for drift in (-0.0015,0.003):                                  # falling index lets 'return' bind, rising index lets 'rs' bind
            rng=random.Random(11);history,cal=market(2,seed=5,bench_drift=drift)
            for i in range(400):
                closes=[];x=100.0
                for seg in range(5):
                    d=rng.uniform(-0.006,0.006)
                    for _ in range(60):x*=math.exp(d+rng.gauss(0,0.005));closes.append(round(x,4))
                history['histories'][str(800000+i)]=dict(symbol=str(800000+i),kind='item',prices=bars(days,closes))
            elig=eligible_records(history,cal,{});self.assertGreater(len(elig),390);self.assertEqual(parity(elig),0)
            base={c:price_status(e,TREND_BASE) for c,e in elig.items()}
            for k,v in enumerate(variants):flips[k]+=sum(1 for c,e in elig.items() if price_status(e,v)!=base[c])
        for v,n in zip(variants,flips):self.assertGreater(n,0,f'variant {v} never changes a status; the test data cannot detect errors in it')

    def test_slope_window_slices_are_exactly_the_documented_ones(self):
        history,cal=market(1,seed=13);e=eligible_records(history,cal,{})['900000'];c=e['closes']
        for end,(lo,hi) in ((10,(-210,-10)),(20,(-220,-20)),(40,(-240,-40))):
            window=sum(c[lo:hi])/200;sma=sum(c[-200:])/200
            self.assertEqual(terms(e,{**TREND_BASE,'mean_end':end})['slope'],sma>window)
        shifted=dict(e,closes=[100.0]*60+[1000.0]*20+[100.0+0.01*i for i in range(220)])                          # old spike only inside the end=40 window
        self.assertTrue(terms(shifted,{**TREND_BASE,'mean_end':20})['slope']);self.assertFalse(terms(shifted,{**TREND_BASE,'mean_end':40})['slope'])

    def test_comparisons_are_strict_exactly_like_technical(self):
        history,cal=market(1,seed=9);e=eligible_records(history,cal,{})['900000']
        up=dict(e,closes=[100+0.5*i for i in range(DAYS)],bm={d:100.0 for d in e['dates']})                     # rising stock, flat index: passes
        self.assertEqual(price_status(up,TREND_BASE),'pass')
        self.assertEqual(price_status(up,{**TREND_BASE,'sma_a':1}),'fail')                                       # close == SMA1: strict '>' fails
        c=list(up['closes']);now=c[-1];c[-127]=now-1;c[-126]=now+1                                              # off-by-one guard: lag 126 means the close 127 bars back
        self.assertTrue(terms(dict(up,closes=c),TREND_BASE)['back'])
        c[-127]=now+1;c[-126]=now-1;self.assertFalse(terms(dict(up,closes=c),TREND_BASE)['back'])
        rs=((up['closes'][-1]/up['closes'][-127]-1)-0)*100
        self.assertEqual(price_status(up,{**TREND_BASE,'rs_min':rs}),'fail')                                     # excess return == threshold: strict
        self.assertEqual(price_status(up,{**TREND_BASE,'rs_min':rs-1e-6}),'pass')

    def test_unusable_histories_are_not_eligible(self):
        history,cal=market(10);history['histories']['900001']['prices']=history['histories']['900001']['prices'][-100:]   # too short
        history['histories']['900002']['prices'][-1]['final']=False                                                      # fails validation
        elig=eligible_records(history,cal,{'900003'})                                                                     # suspended
        self.assertNotIn('900001',elig);self.assertNotIn('900002',elig);self.assertNotIn('900003',elig)

    def test_sensitivity_replaces_status_only_for_eligible_codes_and_keeps_counts_consistent(self):
        history,cal=market();elig=eligible_records(history,cal,{})
        rows=[row(c) for c in list(elig)]+[row('999999','pass')]                                                          # extra code with no history keeps its stored status
        vs=trend_variants();out=trend_sensitivity(rows,elig,vs)
        base_pass=sum(1 for e in elig.values() if price_status(e,TREND_BASE)=='pass')+1
        self.assertEqual(out[0]['params'],TREND_BASE);self.assertEqual(out[0]['passed'],base_pass)
        for v in out:
            self.assertEqual(v['retained']+v['dropped'],out[0]['passed']);self.assertEqual(v['retained']+v['added'],v['passed'])
            self.assertFalse({'codes','passed_codes'}&set(v))
        self.assertEqual(out[0]['parity_mismatch'],0)

    def test_variants_are_distinct_and_trials_exclude_the_current_rule(self):
        vs=trend_variants();self.assertEqual(vs[0],TREND_BASE);self.assertEqual(len({str(sorted(v.items())) for v in vs}),len(vs))
        self.assertEqual(len(trial_entries(vs,'S10-trend-test')),len(vs)-1)
        self.assertEqual(label(vs[0]),'현재 규칙');self.assertTrue(all(label(v)!='현재 규칙' for v in vs[1:]))

    def test_trials_are_logged_as_rejected_and_second_run_counts_again(self):
        with tempfile.TemporaryDirectory() as folder:
            record_trials(folder,'work',trend_variants(),'S10-trend-test');rows=read_all(folder,'work')
            self.assertEqual(len(rows),len(trend_variants())-1);self.assertEqual({r['decision'] for r in rows},{'rejected'})
            record_trials(folder,'work',trend_variants(),'S10-trend-test');self.assertEqual(len(read_all(folder,'work')),2*len(rows))

    def test_render_has_no_company_codes_and_states_no_adoption(self):
        history,cal=market();elig=eligible_records(history,cal,{});rows=[row(c) for c in elig]
        text=render(trend_sensitivity(rows,elig,trend_variants()),'합성 입력',len(trend_variants())-1,len(elig))
        for needle in ('채택하지 않','합성 입력','price_trend_status'):self.assertIn(needle,text)
        self.assertNotIn('900000',text)

    def test_cli_synthetic_runs_without_logging_and_bad_root_fails(self):
        out=io.StringIO()
        with redirect_stdout(out):code=main(['--synthetic'])
        self.assertEqual(code,0);self.assertIn('시도 로그: 합성',out.getvalue())
        with redirect_stdout(io.StringIO()):self.assertEqual(main(['--root','Z:/definitely/not/here']),2)


if __name__=='__main__':unittest.main()
