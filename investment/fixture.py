"""Entirely fictional observations. Never used as a failed-live fallback."""
import math
from datetime import date,timedelta

def make_fixture():
    end=date(2026,9,23); days=[]; d=end
    while len(days)<280:
        if d.weekday()<5: days.append(d.isoformat())
        d-=timedelta(days=1)
    days=sorted(days) # synthetic business dates, NOT a Korean exchange calendar
    rows=[]
    for i in range(8):
        annual=[]
        for y in range(2021,2026):
            k=y-2021
            annual.append(dict(period_end=f'{y}-12-31',available_at=f'{y+1}-03-31',basis='CFS',revenue=1e11*1.1**k,op=8e9*1.2**k,dps=100*1.3**k,dps_basis='ordinary_split_adjusted',special_dividend=False,equity=1e11,debt=2e10,cash=1e10,ocf=1e10,capex=3e9,effective_tax_rate=.22,tax_verified=True))
        quarters=[]
        for n in range(17):
            y=2022+n//4; q=n%4+1; month=q*3; last=31 if month in (3,12) else 30
            endq=date(y,month,last); rev=2e10*(1+n*.03)
            margin=(-.12 if n<9 else .03+(n-9)*.02)+(i*.002)
            quarters.append(dict(period_end=endq.isoformat(),available_at=(endq+timedelta(days=45)).isoformat(),basis='CFS',revenue=rev,op=rev*margin))
        prices=[]
        for n,d in enumerate(days):
            p=10000*math.exp((.001+i*.0001)*n + .003*math.sin(n/8))
            prices.append(dict(date=d,close=p,high=p*1.02,low=p*.98,volume=100000,turnover=p*100000,venue='KRX',adjustment_basis='split_adjusted'))
        evidence=[dict(path=p,document='가상 사업보고서',location='가상 시험 절',summary='기능 검증용 문서 근거. 실제 사업 사실 아님.',available_at='2026-06-01',first_seen_at='2026-06-02',reviewed_at='2026-06-03',review_status='confirmed',execution='paid_dividend') for p in ('turnaround','domestic','substitution','technology','returns')]
        rows.append(dict(code=f'9{i:05d}',name=f'가상 연구기업 {i+1}',market='KOSPI',industry='가상 산업',security_type='ordinary',analysis_profile='nonfinancial',
            price_venue='KRX',valuation_basis='ordinary_split_adjusted_TTM',metrics=dict(market_cap_eok=1000+i*100,operating_margin_pct=10+i,roe_pct=8+i,debt_ratio_pct=20+i,net_debt_equity_pct=10,interest_coverage_x=10,current_ratio_pct=150,revenue_growth_pct=10,foreign_net_20d_eok=i-3,institution_net_20d_eok=i,foreign_net_turnover_20d_pct=(i-3)/20,institution_net_turnover_20d_pct=i/20,avg_trading_value_20d_eok=20,eps_ttm=1000,price=prices[-1]['close'],per=10+i,pbr=1+i*.1),
            annual=annual,quarters=quarters,prices=prices,evidence=evidence,stages=[],history=[],sources=[],data_quality=['가상 테스트 · 실제 종목·공시 아님']))
    return dict(schema_version='0.1',meta=dict(data_mode='fixture',price_date=end.isoformat(),flow_start=days[-20],flow_end=end.isoformat(),financial_period='2026-03-31',financial_basis='CFS',venue='KRX',universe_label='명시적 가상 연구 fixture',universe_total=8,calendar_basis='synthetic_weekdays'),
        companies=rows,sessions=days,benchmarks={'KOSPI':[dict(date=d,close=1000*math.exp(n*.0005),adjustment_basis='split_adjusted') for n,d in enumerate(days)]})
