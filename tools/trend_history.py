"""Join saved public OHLCV and index charts for a dated, provisional trend view."""
import argparse
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import quote
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from investment.core import num, validate_snapshot
from tools.infomax_import import require, write_new

SYMBOLS = {'005930': '005930.KS', '000660': '000660.KS',
           '005380': '005380.KS'}
INDEX = '^KS11'
SOURCE_URL = 'https://query1.finance.yahoo.com/v8/finance/chart/'
NOTE = '추세 가격은 Yahoo Finance 현재 조회본 · KRX 사용자 지정 기준. 인포맥스 종가와 차이 있음. 원자료 거래소·수정 기준 독립 검증 전.'


def fetch_charts(directory, timeout=15):
    """Save immutable public responses locally before using them in a snapshot."""
    import requests
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    files = {}
    for symbol in (*SYMBOLS.values(), INDEX):
        response = requests.get(SOURCE_URL + quote(symbol, safe=''),
            params={'range':'2y','interval':'1d','events':'splits,div'},
            headers={'User-Agent':'Mozilla/5.0'}, timeout=timeout)
        response.raise_for_status()
        payload = response.content
        require(0 < len(payload) <= 20*1024*1024, '시세 응답 크기 제한 초과')
        name = 'yahoo-' + symbol.replace('^','index-') + '-' + hashlib.sha256(payload).hexdigest()[:12] + '.json'
        path = directory / name
        if path.exists():
            require(path.read_bytes() == payload, '보관된 시세 응답 해시 불일치')
        else:
            temp = path.with_suffix('.tmp')
            temp.write_bytes(payload)
            temp.replace(path)
        files[symbol] = path
    return files


def chart(path, symbol, cutoff):
    """Read a saved Yahoo chart response; keep source bytes and exact hash."""
    path = Path(path)
    payload = path.read_bytes()
    require(len(payload) <= 20*1024*1024, '시세 응답 크기 제한 초과')
    data = json.loads(payload)['chart']['result'][0]
    meta = data['meta']
    require(meta['symbol'] == symbol and meta['exchangeTimezoneName'] == 'Asia/Seoul', '심볼·거래소 시간대 불일치')
    require(not data.get('events', {}).get('splits'), '조회 구간 주식분할 발생: 수정 기준 별도 검토 필요')
    times = data['timestamp']
    quote = data['indicators']['quote'][0]
    require(all(len(quote[key]) == len(times) for key in ('open','high','low','close','volume')),
            '시세 배열 길이 불일치')
    rows = {}
    for i, stamp in enumerate(times):
        date = datetime.fromtimestamp(stamp, ZoneInfo('Asia/Seoul')).date().isoformat()
        if date > cutoff: continue
        require(date not in rows, '중복 관측일')
        values = {k:quote[k][i] for k in ('open','high','low','close','volume')}
        if all(num(v) and v>0 for v in values.values()) and values['low'] <= min(values['open'],values['close']) <= max(values['open'],values['close']) <= values['high']:
            rows[date] = values
    require(len(rows) >= 253, '추세 분석용 유효 관측일 253개 미만')
    return rows, dict(symbol=symbol, file=path.name, sha256=hashlib.sha256(payload).hexdigest(),
                      url=SOURCE_URL+symbol, price_basis='no_split_event_in_query_range')


def build(base, chart_inputs, cutoff=None):
    validate_snapshot(base)
    require(base['meta']['data_mode'] == 'user_input', '실제 저장자료만 연결 가능')
    cutoff = cutoff or base['meta']['price_date']
    require(cutoff == base['meta']['price_date'], '가격 기준일 불일치')
    require({r['code'] for r in base['companies']} == set(SYMBOLS), '현재 조회 설정의 세 종목만 연결')
    require(set(chart_inputs) == set(SYMBOLS.values()) | {INDEX}, '차트 파일 집합 불일치')
    parsed = {symbol:chart(path,symbol,cutoff) for symbol,path in chart_inputs.items()}
    common = sorted(set.intersection(*(set(rows) for rows,_ in parsed.values())))
    require(len(common) >= 253 and common[-1] == cutoff, '지수·종목 공통 관측일이 가격일까지 253개 필요')
    sessions = common[-253:]
    result = copy.deepcopy(base)
    benchmark, index_source = parsed[INDEX]
    result['benchmarks']['KOSPI'] = [dict(date=d,close=benchmark[d]['close'],
        adjustment_basis='split_adjusted',source='Yahoo Finance',symbol=INDEX) for d in sessions]
    result['meta']['trend_sessions'] = sessions
    result['meta']['trend_source'] = dict(provider='Yahoo Finance', basis='provisional_user_KRX',
        cutoff=cutoff, index=index_source, note=NOTE,
        stock_sources={c:parsed[s][1] for c,s in SYMBOLS.items()})
    if NOTE not in result['meta'].setdefault('warnings',[]): result['meta']['warnings'].append(NOTE)
    for row in result['companies']:
        code = row['code']; values, provenance = parsed[SYMBOLS[code]]
        old = {p['date']:p for p in row.get('prices',[])}
        overlaps = [dict(date=d, yahoo_close=values[d]['close'],
                         infomax_close=old[d]['close'],difference=values[d]['close']-old[d]['close'])
                    for d in sessions if d in old and num(old[d].get('close'))]
        require(overlaps and overlaps[-1]['date'] == cutoff, '인포맥스 종가와 기준일 대조 불가')
        turnover = {p['date']:p.get('turnover') for p in row.get('prices',[])}
        require(all(num(turnover.get(d)) and turnover[d] >= 0 for d in sessions[-20:]),
                '최근 20개 공통 관측일 거래대금 결측')
        row['trend_prices'] = [dict(date=d,**values[d],turnover=turnover.get(d),venue='KRX',
            adjustment_basis='split_adjusted',final=False) for d in sessions]
        row['trend_price_venue'] = 'KRX'
        row['trend_source'] = dict(**provenance, cutoff=cutoff, overlaps=len(overlaps),
            disagreements=[x for x in overlaps if abs(x['difference'])>1],
            last_price_difference=overlaps[-1]['difference'], verified_same_source=False)
        row['sources'] = [s for s in row.get('sources',[]) if s.get('kind')!='provisional_trend']
        row['sources'].append(dict(label='Yahoo Finance 공개 조정 기준 추세 시세',
            kind='provisional_trend',**provenance))
        if NOTE not in row.setdefault('data_quality',[]): row['data_quality'].append(NOTE)
    return validate_snapshot(result)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base',required=True,type=Path)
    p.add_argument('--directory',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    snapshot=json.loads(args.base.read_text(encoding='utf-8-sig'))
    files={symbol:args.directory/('yahoo-'+symbol.replace('^','index-')+'.json')
           for symbol in (*SYMBOLS.values(),INDEX)}
    result=build(snapshot,files)
    write_new(args.output,result)
    print(json.dumps({r['code']:dict(observations=len(r['trend_prices']),
        disagreements=len(r['trend_source']['disagreements'])) for r in result['companies']},ensure_ascii=False))


if __name__=='__main__': main()
