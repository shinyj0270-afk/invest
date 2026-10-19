"""On-demand Naver/WiseReport reference bands. No DB, files or account access."""
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
import math
import re
import threading
import time
import requests
from .naver_reference import fetch_references

BASE='https://navercomp.wisereport.co.kr/v2'


def identity(code,basis):
    if not isinstance(code,str) or not re.fullmatch(r'\d{6}',code) or basis not in ('CFS','OFS'):
        raise ValueError('국내 종목코드·회계기준 확인 필요')


def parse_bands(raw,code,basis,retrieved_at):
    identity(code,basis)
    retrieved=datetime.fromisoformat(retrieved_at)
    if retrieved.tzinfo is None:raise ValueError('조회 시각 시간대 필요')
    cutoff=retrieved.date().isoformat()
    result=dict(code=code,basis=basis,status='ready',source='네이버 증권 · WiseReport 제공 밴드',
                source_url=BASE+'/company/c1010001.aspx?cmp_cd='+code,
                retrieved_at=retrieved_at,bands={})
    for key,field in [('per','bandChart1'),('pbr','bandChart2')]:
        chart=raw[field];prices=chart['price']
        if not isinstance(prices,list) or not 1<=len(prices)<=2400:raise ValueError('밴드 관측 수 확인 필요')
        labels=[chart['name']['VAL'+str(i)] for i in range(1,5)]
        if any(not isinstance(x,str) or not re.fullmatch(r'\d+(?:\.\d+)?배',x) for x in labels):
            raise ValueError('밴드 배수 형식 확인 필요')
        series=[chart['val'+str(i)] for i in range(1,5)]
        if any(not isinstance(s,list) or len(s)!=len(prices) for s in series):raise ValueError('밴드 길이 불일치')
        rows=[];previous=None
        for i,p in enumerate(prices):
            stamp=p['x']
            if type(stamp) not in (int,float) or not math.isfinite(stamp) or not 0<stamp<4102444800000:
                raise ValueError('밴드 날짜 확인 필요')
            day=datetime.fromtimestamp(stamp/1000,timezone.utc).date().isoformat()
            if previous is not None and day<=previous:raise ValueError('밴드 날짜 중복·정렬 오류')
            previous=day
            values={'close':p['y']}
            for j,s in enumerate(series,1):
                if s[i]['x']!=stamp:raise ValueError('밴드 날짜 불일치')
                values['band'+str(j)]=s[i]['y']
            if any(v is not None and (type(v) not in (int,float) or not math.isfinite(v) or v<0) for v in values.values()):
                raise ValueError('밴드 수치 오류')
            # Provider future bands/estimates lack observed prices: never invent a history.
            if day<=cutoff and type(values['close']) in (int,float) and values['close']>0:
                rows.append(dict(period_end=day,values=values))
        result['bands'][key]=dict(labels=labels,rows=rows)
    if not any(x['rows'] for x in result['bands'].values()):raise ValueError('관측 밴드 없음')
    return result


class NaverBands:
    """Bounded in-memory cache; only selected symbols, no polling or persistence."""
    def __init__(self):
        self.cache=OrderedDict()
        self.lock=threading.Lock()

    def lookup(self,code,basis):
        identity(code,basis)
        key=(code,basis)
        with self.lock:
            cached=self.cache.get(key)
            if cached and time.monotonic()-cached[0]<3600:
                self.cache.move_to_end(key)
                return deepcopy(cached[1])
            result=dict(code=code,basis=basis,status='unavailable',bands={},reason='네이버 밴드 조회 대기')
            try:
                with requests.Session() as session:
                    session.trust_env=False
                    response=session.get(BASE+'/common/BandChart3.aspx',params=dict(cmp_cd=code,gubun='4' if basis=='CFS' else '3'),
                        headers={'Referer':BASE+'/company/c1010001.aspx?cmp_cd='+code},timeout=(3,6),allow_redirects=False)
                    if response.status_code!=200 or len(response.content)>2*1024*1024:raise ValueError('밴드 응답 오류')
                    result=parse_bands(response.json(),code,basis,datetime.now().astimezone().isoformat(timespec='seconds'))
            except (requests.RequestException,ValueError,KeyError,TypeError,OverflowError,OSError):pass
            # Latest public quote is a separate observation; never use it as historical earnings.
            quote=fetch_references([code])
            if code in quote['companies']:result['quote']=quote['companies'][code]
            self.cache[key]=(time.monotonic(),result)
            while len(self.cache)>128:self.cache.popitem(last=False)
            return deepcopy(result)
