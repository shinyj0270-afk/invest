"""Normalize saved public DART statement viewers. No credentials or DB writes."""
import re
import json
import math
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from html.parser import HTMLParser
from datetime import date
from .financial_table import valid_day


class Tables(HTMLParser):
    def __init__(self):
        super().__init__(); self.tables=[]; self.table=None; self.row=None; self.cell=None
    def handle_starttag(self, tag, attrs):
        if tag.lower()=='table': self.table=[]
        elif tag.lower()=='tr': self.row=[]
        elif tag.lower() in ('td','th'): self.cell=''
    def handle_data(self, value):
        if self.cell is not None: self.cell+=value
    def handle_endtag(self, tag):
        if tag.lower() in ('td','th') and self.cell is not None:
            self.row.append(self.cell.strip()); self.cell=None
        elif tag.lower()=='tr' and self.row is not None:
            if self.table is not None: self.table.append(self.row)
            self.row=None
        elif tag.lower()=='table' and self.table is not None:
            self.tables.append(self.table); self.table=None


def label(value):
    value=re.sub(r'\((?:주|주석|단위)[^)]*\)', '', value)
    return re.sub(r'\s+', '', value).replace('ㆍ','').replace('·','')


def amount(value):
    value=value.replace(',','').replace('−','-').strip()
    if not value or value in ('-','—'): return None
    if re.fullmatch(r'\(\d+(?:\.\d+)?\)',value): value='-'+value[1:-1]
    if not re.fullmatch(r'-?\d+(?:\.\d+)?',value): return None
    return float(value)


ALIASES={
 'balance':{
  'assets':['자산총계'], 'current_assets':['유동자산'], 'noncurrent_assets':['비유동자산'],
  'liabilities':['부채총계'], 'current_liabilities':['유동부채'], 'noncurrent_liabilities':['비유동부채'],
  'equity':['자본총계'], 'parent_equity':['지배기업소유주지분','지배기업의소유주에게귀속되는자본','지배기업의소유주에게귀속되는지분','지배기업의소유주지분','지배기업소유주에게귀속되는자본','지배기업의소유지분'],
  'nci':['비지배지분'], 'cash':['현금및현금성자산'], 'retained_earnings':['이익잉여금','이익잉여금(결손금)'],
 },
 'income':{
  'revenue':['매출액','수익(매출액)','영업수익','매출액(영업수익)'], 'cost_of_sales':['매출원가'],
  'gross_profit':['매출총이익','매출총이익(손실)'], 'sga':['판매비와관리비','판매비와관리비용'],
  'operating_profit':['영업이익','영업이익(손실)'], 'finance_income':['금융수익','금융이익'],
  'finance_cost':['금융원가','금융비용','금융손실'], 'other_income':['기타수익','기타영업외수익'],
  'other_cost':['기타비용','기타영업외비용'], 'pretax':['법인세비용차감전순이익','법인세비용차감전순이익(손실)','법인세비용차감전계속사업이익','법인세비용차감전계속사업이익(손실)','법인세차감전순이익','법인세차감전순이익(손실)'],
  'tax':['법인세비용','법인세비용(수익)'],
  'net_income':['당기순이익','당기순이익(손실)','반기순이익','반기순이익(손실)','분기순이익','분기순이익(손실)','당기순손익','반기순손익','분기순손익','연결당기순이익','연결반기순이익','연결분기순이익','연결당기순이익(손실)','연결반기순이익(손실)','연결분기순이익(손실)'],
  'parent_net':['지배기업의소유주에게귀속되는당기순이익(손실)','지배기업의소유주에게귀속되는반기순이익(손실)','지배기업의소유주에게귀속되는분기순이익(손실)','지배기업소유주','지배기업의소유주','지배회사지분당기순이익','지배회사지분반기순이익','지배회사지분분기순이익','지배기업의소유주에게귀속되는당기순이익','지배기업의소유주에게귀속되는반기순이익','지배기업의소유주에게귀속되는분기순이익','지배기업의소유주지분','지배기업소유주지분'],
  'nci_net':['비지배지분','비지배지분에귀속되는당기순이익(손실)','비지배지분에귀속되는반기순이익(손실)','비지배지분에귀속되는분기순이익(손실)'],
  'eps':['기본주당이익(손실)','기본주당이익','기본주당순이익(손실)','기본주당순이익','기본주당분기순이익','기본주당반기순이익','보통주기본주당이익','보통주기본주당이익(손실)'],
 },
 'cash':{
  'ocf':['영업활동현금흐름','영업활동으로인한현금흐름','영업활동으로부터의현금흐름'],
  'cash_generated':['영업에서창출된현금흐름','영업에서창출된현금','영업활동에서창출된현금흐름','영업으로부터창출된현금흐름'],
  'noncash_adjustments':['조정','비현금항목의조정','비현금항목조정'],
  'noncash_cost':['현금유출이없는비용등가산','현금의유출이없는비용등가산','현금유출이없는비용등의가산'],
  'noncash_income':['현금유입이없는수익등차감','현금의유입이없는수익등차감','현금유입이없는수익등의차감'],
  'working_capital':['영업활동으로인한자산부채의변동','영업활동으로인한자산부채변동','영업활동자산부채의변동','영업활동으로인한자산ㆍ부채의변동'],
  'icf':['투자활동현금흐름','투자활동으로인한현금흐름','투자활동으로부터의현금흐름'],
  'financing_cf':['재무활동현금흐름','재무활동으로인한현금흐름','재무활동으로부터의현금흐름'],
  'cash_change':['현금및현금성자산의증가(감소)','환율변동효과적용후현금및현금성자산의증가(감소)','현금및현금성자산의순증가(감소)','현금및현금성자산의증감'],
  'cash_start':['기초현금및현금성자산','기초의현금및현금성자산'],
  'cash_end':['기말현금및현금성자산','반기말의현금및현금성자산','분기말의현금및현금성자산','기말의현금및현금성자산','반기말현금및현금성자산','분기말현금및현금성자산'],
  'capex_ppe':['유형자산의취득','유형자산의취득에따른현금유출','유형자산취득'],
  'capex_intangibles':['무형자산의취득','무형자산의취득에따른현금유출','무형자산취득'],
 }
}
FLOW=set(ALIASES['income'])-{'eps'}
CASH_FLOW=set(ALIASES['cash'])-{'cash_start','cash_end'}


def parse_viewer(text, *, code, name, market, basis, year, quarter, receipt, url):
    if basis not in ('CFS','OFS') or quarter not in (1,2,3,4): raise ValueError('회계기준·분기 오류')
    available=date.fromisoformat(receipt[:4]+'-'+receipt[4:6]+'-'+receipt[6:8]).isoformat()
    end=f'{year}-{["03-31","06-30","09-30","12-31"][quarter-1]}'
    parser=Tables();parser.feed(text);result={};raw={};units={};context=None;unit=None
    for table in parser.tables:
        # The title/unit/date table directly precedes its account table.
        title=' '.join(c for row in table[:1] for c in row)
        if table and len(table[0])==1:
            context=('balance' if '재무상태표' in title else 'cash' if '현금흐름표' in title
                     else 'income' if '손익계산서' in title and '포괄' not in title else
                     'income' if '포괄손익계산서' in title and 'income' not in result else None)
            joined=' '.join(c for row in table for c in row)
            unit=1e6 if '백만원' in joined else 1e3 if '천원' in joined else 1 if re.search(r'단위\s*:\s*원',joined) else None
            if context and basis=='CFS' and '연결' not in title:raise ValueError('연결 제목 불일치')
            if context and basis=='OFS' and '연결' in title:raise ValueError('별도 제목 불일치')
            if context and str(year)+'.' not in joined:raise ValueError('보고서 연도 불일치')
            continue
        if not context or unit is None or context in result:continue
        quarter_column=context=='income' and quarter!=4 and any('3개월' in ''.join(row) for row in table[:3])
        col=2 if quarter_column else 1  # Store YTD so Q4 and CF are reconstructed consistently.
        values={};original=[];attribution=False;attributed_net=None
        for row in table:
            if len(row)<=col:continue
            v=amount(row[col]);key=label(row[0])
            if '순이익의귀속' in key:attribution=True
            if not key or v is None:continue
            is_eps='주당' in key
            value=v if is_eps else v*unit
            original.append(dict(label=row[0],value=value,unit='원/주' if is_eps else 'KRW'))
            for dest,names in ALIASES[context].items():
                if key in names:
                    if dest in values:
                        if context=='income' and dest=='net_income' and attribution:
                            attributed_net=value;continue
                        if context=='income' and dest in ('parent_net','nci_net'):continue
                        raise ValueError('계정 중복: '+dest)
                    values[dest]=value
        if attributed_net is not None:
            if 'nci_net' not in values or abs(attributed_net+values['nci_net']-values['net_income'])>unit:
                raise ValueError('귀속 손익 대조 불일치')
            values['parent_net']=attributed_net
        if values:result[context]=values;raw[context]=original;units[context]=unit
        context=None
    if not all(k in result for k in ('balance','income','cash')):raise ValueError('3개 재무제표 또는 단위 미확인')
    b=result['balance'];i=result['income']
    if not all(k in b for k in ('assets','liabilities','equity')) or abs(b['assets']-b['liabilities']-b['equity'])>1e6:raise ValueError('대차 불일치')
    if not all(k in i for k in ('revenue','operating_profit','net_income')):raise ValueError('주요 손익 계정 미확인')
    return dict(code=code,name=name,market=market,basis=basis,year=year,quarter=quarter,period_end=end,
        available_at=available,receipt=receipt,url=url,values={**b,**i,**result['cash']},raw=raw,
        source='금융감독원 DART 공개 재무제표',unit='KRW',units=units)


def quarter_records(reports, cutoff):
    """YTD differences within the same year/basis only; no 0 imputation."""
    reports=sorted(reports,key=lambda r:(r['basis'],r['period_end']));lookup={(r['basis'],r['year'],r['quarter']):r for r in reports}
    periods=[]
    for report in reports:
        if report['available_at']>cutoff or report['period_end']>cutoff:continue
        q=report['quarter'];prior=lookup.get((report['basis'],report['year'],q-1)) if q>1 else None
        current=report['values'];values=dict(current)
        for k in FLOW|CASH_FLOW|{'eps'}:
            values[k]=(current[k] if q==1 else current[k]-prior['values'][k]
                       if prior and k in current and k in prior['values'] else None) if k in current else None
        # Cash opening balance is preceding quarter's closing cash, never a YTD sum.
        values['cash_start']=current.get('cash_start') if q==1 else prior['values'].get('cash_end') if prior else None
        available=max(report['available_at'],prior['available_at']) if prior else report['available_at']
        if available > cutoff: continue
        record=dict(period_end=report['period_end'],available_at=available,basis=report['basis'],cadence='quarter',
                    source=report['source'],source_url=report['url'],receipt=report['receipt'],**values)
        periods.append(record)
        if q==4:periods.append(dict(record,cadence='annual',**current))
    return periods


def load_bundle(path, snapshot):
    path=Path(path)
    if not path.is_file():return {}
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        if data.get('schema')!='dart-public-statements-1' or data.get('unit')!='KRW':return {}
        result={}
        for row in snapshot['companies']:
            reports=data.get('companies',{}).get(row['code'],{}).get('reports',[])
            if not reports or any((r.get('code'),r.get('name'),r.get('market'))!=(row['code'],row['name'],row['market'])
                or r.get('unit')!='KRW' or not valid_day(r.get('available_at')) or not valid_day(r.get('period_end')) for r in reports):continue
            if not all(valid_report(r) for r in reports): continue
            keys=[(r['basis'],r['year'],r['quarter']) for r in reports]
            if len(keys)!=len(set(keys)): continue
            periods=quarter_records(reports,snapshot['meta']['price_date'])
            if periods:result[row['code']]=dict(code=row['code'],name=row['name'],market=row['market'],periods=periods,
                notes=['DART 최초 제출본이 아닌 현재 조회본입니다. 제출일 이전 값은 제외하며 정정 이력의 과거 재현은 보장하지 않습니다.'])
        return result
    except (OSError,ValueError,KeyError,TypeError):return {}


def valid_report(r):
    """Reject ambiguous periods, foreign links, non-finite values and broken balances."""
    try:
        q=r['quarter']; y=r['year']; receipt=r['receipt']; url=urlsplit(r['url'])
        if type(q) is not int or q not in (1,2,3,4) or type(y) is not int: return False
        if r['basis'] not in ('CFS','OFS'): return False
        if r['period_end']!=f'{y}-{["03-31","06-30","09-30","12-31"][q-1]}': return False
        if not re.fullmatch(r'\d{14}',receipt) or r['available_at']!=date(int(receipt[:4]),int(receipt[4:6]),int(receipt[6:8])).isoformat(): return False
        if url.scheme!='https' or url.netloc!='dart.fss.or.kr' or url.path.replace('//','/')!='/report/viewer.do' or parse_qs(url.query).get('rcpNo')!=[receipt]: return False
        v=r['values']
        if not isinstance(v,dict) or any(type(x) not in (int,float) or not math.isfinite(x) for x in v.values()): return False
        if any(k not in v for k in ('assets','liabilities','equity','revenue','operating_profit','net_income','ocf')): return False
        return abs(v['assets']-v['liabilities']-v['equity'])<=1e6
    except (ValueError,KeyError,TypeError,AttributeError): return False
