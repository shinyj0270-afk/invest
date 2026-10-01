"""Bounded public company lookup; quote caches do not modify market DBs."""
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import re
import threading
import time

from .holdings_bridge import holdings_catalog
from .market_discovery import load_market_cache
from .market_history import fetch_history
from .core import num
from requests.exceptions import RequestException


class HoldingMarket:
    def __init__(self, root, snapshot_loader, *, fetcher=fetch_history, now=None):
        self.root=Path(root); self.snapshot_loader=snapshot_loader; self.fetcher=fetcher
        self.now=now or (lambda:datetime.now(ZoneInfo('Asia/Seoul')))
        self.lock=threading.RLock(); self.index=None; self.results={}

    def lookup(self, code, *, force=False):
        if not isinstance(code,str) or not re.fullmatch(r'\d{6}',code):
            raise ValueError('6자리 종목코드가 필요합니다.')
        with self.lock:
            if self.index is None:
                snapshot=self.snapshot_loader()
                self.index={r['code']:r for r in holdings_catalog(snapshot,load_market_cache(self.root,snapshot))}
            if code not in self.index:
                return dict(status='unavailable',code=code,row=None,message='연결된 기업 자료가 없습니다. 직접 입력할 수 있습니다.')
            prior=self.results.get(code)
            if prior and not force and time.monotonic()-prior[0]<300:
                return deepcopy(prior[1])
            row=deepcopy(self.index[code]); now=self.now()
            cutoff=now.date()-timedelta(days=1)
            try:
                record=self.fetcher(code,start=(cutoff-timedelta(days=14)).isoformat(),
                    end=cutoff.isoformat(),cache_dir=self.root/'.local/holding-market',now=now,force=True)
                bars=record['prices']; last=bars[-1]
                date.fromisoformat(last['date'])
                if (record.get('symbol')!=code or record.get('kind')!='item' or last.get('final') is not True or
                    last.get('venue')!='KRX' or last.get('adjustment_basis')!='naver_chart_adjusted' or
                    not num(last.get('close')) or last['close']<=0 or last['date']>cutoff.isoformat()):
                    raise ValueError('완료 관측일 확인 필요')
                if row['price_date'] is None or last['date']>row['price_date']:
                    row.update(price_krw=last['close'],price_date=last['date'],price_source=dict(kind='public_chart',
                        label='네이버 완료 일봉 · KRX · 차트 보정가격',url='https://stock.naver.com/domestic/stock/'+code+'/price'))
                result=dict(status='updated',code=code,row=row,message='최근 완료 종가 확인 · '+row['price_date'])
            except (RequestException,OSError,ValueError,KeyError,TypeError,IndexError):
                # A provider failure retains the dated cache, not a fabricated quote.
                result=dict(status='cached' if row['price_date'] else 'unavailable',code=code,row=row,
                    message='가격 연결 대기 · 저장 관측값 유지' if row['price_date'] else '기업 연결 완료 · 가격 확인 필요')
            self.results[code]=(time.monotonic(),result)
            return deepcopy(result)
