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
    value=re.sub(r'^\s*(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩIVX]+\s*[.)]|\(\d+\)|\d+\s*[.)])\s*','',value)
    return re.sub(r'\s+', '', value).replace('ㆍ','').replace('·','').replace('（','(').replace('）',')')


def amount(value):
    value=value.replace(',','').replace('−','-').strip()
    if not value or value in ('-','—'): return None
    if re.fullmatch(r'\(\d+(?:\.\d+)?\)',value): value='-'+value[1:-1]
    if not re.fullmatch(r'-?\d+(?:\.\d+)?',value): return None
    return float(value)


ALIASES={
 'balance':{
  'assets':['자산총계','자산합계'], 'current_assets':['유동자산'], 'noncurrent_assets':['비유동자산'],
  'liabilities':['부채총계','부채합계'], 'current_liabilities':['유동부채'], 'noncurrent_liabilities':['비유동부채'],
  'equity':['기말자본','자본','자본총계','자본합계'], 'parent_equity':['지배기업소유주지분','지배기업의소유주에게귀속되는자본','지배기업의소유주에게귀속되는지분','지배기업의소유주지분','지배기업소유주에게귀속되는자본','지배기업의소유지분'],
  'nci':['비지배주주지분','비지배지분'], 'cash':['현금및현금성자산'], 'retained_earnings':['이익잉여금','이익잉여금(결손금)'],
 },
 'income':{
  'revenue':['매출액(매출액)','수익','매출액및기타수익','매출및지분법손익','매출','매출액','수익(매출액)','영업수익','매출액(영업수익)'], 'cost_of_sales':['매출원가'],
  'gross_profit':['매출총이익','매출총이익(손실)'], 'sga':['판매비와관리비','판매비와관리비용'],
  'operating_profit':['영업손실','영업순손익','영업손익','영업이익','영업이익(손실)'], 'finance_income':['금융수익','금융이익'],
  'finance_cost':['금융원가','금융비용','금융손실'], 'other_income':['기타수익','기타영업외수익'],
  'other_cost':['기타비용','기타영업외비용'], 'pretax':['법인세비용차감전순이익','법인세비용차감전순이익(손실)','법인세비용차감전계속사업이익','법인세비용차감전계속사업이익(손실)','법인세차감전순이익','법인세차감전순이익(손실)'],
  'tax':['법인세수익(비용)','법인세비용','법인세비용(수익)'],
  'net_income':['당기순이익','당기순이익(손실)','반기순이익','반기순이익(손실)','분기순이익','분기순이익(손실)','당기순손익','반기순손익','분기순손익','연결당기순이익','연결반기순이익','연결분기순이익','연결당기순이익(손실)','연결반기순이익(손실)','연결분기순이익(손실)'],
  'parent_net':['지배기업의소유주에게귀속되는당기순이익(손실)','지배기업의소유주에게귀속되는반기순이익(손실)','지배기업의소유주에게귀속되는분기순이익(손실)','지배기업소유주','지배기업의소유주','지배회사지분당기순이익','지배회사지분반기순이익','지배회사지분분기순이익','지배기업의소유주에게귀속되는당기순이익','지배기업의소유주에게귀속되는반기순이익','지배기업의소유주에게귀속되는분기순이익','지배기업의소유주지분','지배기업소유주지분'],
  'nci_net':['비지배지분','비지배지분에귀속되는당기순이익(손실)','비지배지분에귀속되는반기순이익(손실)','비지배지분에귀속되는분기순이익(손실)'],
  'eps':['기본주당이익(손실)','기본주당이익','기본주당순이익(손실)','기본주당순이익','기본주당분기순이익','기본주당반기순이익','보통주기본주당이익','보통주기본주당이익(손실)'],
 },
 'cash':{
  'ocf':['영업활동으로인한순현금흐름','영업활동순현금흐름','영업활동현금흐름','영업활동으로인한현금흐름','영업활동으로부터의현금흐름'],
  'cash_generated':['영업에서창출된현금흐름','영업에서창출된현금','영업활동에서창출된현금흐름','영업으로부터창출된현금흐름'],
  'noncash_adjustments':['조정','비현금항목의조정','비현금항목조정'],
  'noncash_cost':['현금유출이없는비용등가산','현금의유출이없는비용등가산','현금유출이없는비용등의가산'],
  'noncash_income':['현금유입이없는수익등차감','현금의유입이없는수익등차감','현금유입이없는수익등의차감'],
  'working_capital':['영업활동으로인한자산부채의변동','영업활동으로인한자산부채변동','영업활동자산부채의변동','영업활동으로인한자산ㆍ부채의변동'],
  'icf':['투자활동순현금흐름','투자활동현금흐름','투자활동으로인한현금흐름','투자활동으로부터의현금흐름'],
  'financing_cf':['재무활동순현금흐름','재무활동현금흐름','재무활동으로인한현금흐름','재무활동으로부터의현금흐름'],
  'cash_change':['현금및현금성자산의증가(감소)','환율변동효과적용후현금및현금성자산의증가(감소)','현금및현금성자산의순증가(감소)','현금및현금성자산의증감'],
  'cash_start':['기초현금및현금성자산','기초의현금및현금성자산'],
  'cash_end':['기말현금및현금성자산','반기말의현금및현금성자산','분기말의현금및현금성자산','기말의현금및현금성자산','반기말현금및현금성자산','분기말현금및현금성자산'],
  'capex_ppe':['유형자산의취득','유형자산의취득에따른현금유출','유형자산취득'],
  'capex_intangibles':['무형자산의취득','무형자산의취득에따른현금유출','무형자산취득'],
 }
}
FLOW=set(ALIASES['income'])-{'eps'}
CASH_FLOW=set(ALIASES['cash'])-{'cash_start','cash_end'}

def reconciliation_reference(values, rows, context, unit):
    """Keep unique explicit accounts with a disclosed residual below KRW 100m."""
    fields=('parent_net','nci_net','net_income') if context=='income' else ('parent_equity','nci','equity')
    a,b,total=fields
    candidates={a:set(),b:set()}
    for row in rows:
        key=label(row['label'])
        if context=='income':
            if not re.search(r'순(?:이익|손익)',key) or any(w in key for w in ('포괄','계속','중단','주당','희석','기본','우선','보통')):continue
            target=b if '비지배' in key else a if '지배' in key else None
        else:target=next((k for k in (a,b) if key in ALIASES['balance'][k]),None)
        if target:candidates[target].add(row['value'])
    if total not in values or any(len(candidates[k])!=1 for k in (a,b)):return {}
    av=next(iter(candidates[a]));bv=next(iter(candidates[b]));difference=av+bv-values[total]
    if not unit<abs(difference)<1e8:return {}
    values[a]=av;values[b]=bv
    note=dict(difference_krw=difference,limit_krw=100000000,equation=a+'+'+b+'='+total,method='explicit_same_statement_accounts')
    return {a:dict(note),b:dict(note)}

def displayed_debt(rows):
    """Sum identified BS loans/bonds, never claim all financial or lease debt."""
    groups={};section='unclassified'
    names={'차입금','단기차입금','장기차입금','유동성장기차입금','유동성차입금','비유동성차입금',
           '사채','유동성사채','유동성장기사채','전환사채','유동성전환사채','차입금및사채','차입금과사채'}
    for r in rows:
        k=label(r['label']);v=r['value']
        if k in ('유동부채','비유동부채'):section=k
        if k not in names:continue
        if v<0:return None
        bucket=groups.setdefault(section,{})
        if k in bucket and bucket[k]!=v:return None
        bucket[k]=v
    total=0;found=False
    for bucket in groups.values():
        combined=[bucket[k] for k in ('차입금및사채','차입금과사채') if k in bucket]
        if len(combined)>1:return None
        if combined:total+=combined[0];found=True;continue
        loans=[v for k,v in bucket.items() if '차입금' in k]
        bonds=[v for k,v in bucket.items() if '사채' in k]
        if '사채' in bucket and len(bonds)>1:return None  # Parent/child scope ambiguous.
        if '차입금' in bucket and len(loans)>1 and abs(sum(loans)-2*bucket['차입금'])>1:return None
        total+=(bucket['차입금'] if '차입금' in bucket else sum(loans))+sum(bonds)
        found=found or bool(loans or bonds)
    return total if found else None


def parse_viewer(text, *, code, name, market, basis, year, quarter, receipt, url):
    if basis not in ('CFS','OFS') or quarter not in (1,2,3,4): raise ValueError('회계기준·분기 오류')
    available=date.fromisoformat(receipt[:4]+'-'+receipt[4:6]+'-'+receipt[6:8]).isoformat()
    end=f'{year}-{["03-31","06-30","09-30","12-31"][quarter-1]}'
    parser=Tables();parser.feed(text);result={};raw={};units={};reconciliation_notes={};context=None;unit=None
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
            if context and not re.search(rf'{year}\s*(?:\.|-|년)',joined):raise ValueError('보고서 연도 불일치')
            if context:
                expected=end.split('-')
                date_pattern=rf"{expected[0]}\s*(?:\.|-|년)\s*0?{int(expected[1])}\s*(?:\.|-|월)\s*0?{int(expected[2])}(?:\D|$)"
                if not re.search(date_pattern,joined):raise ValueError('보고기간 종료일 불일치')
            continue
        if not context or unit is None or context in result:continue
        quarter_column=context=='income' and quarter!=4 and any('3개월' in ''.join(row) for row in table[:3])
        col=2 if quarter_column else 1  # Store YTD so Q4 and CF are reconstructed consistently.
        values={};original=[];attribution=False;attributed_net=None; abbreviated_net=[];parent_candidates=[];nci_candidates=[];pairs=[];pending_parent=None;ambiguous=set();explicit_total=False
        for row in table:
            if len(row)<=col:continue
            v=amount(row[col]);key=label(row[0])
            if '순이익의귀속' in key:attribution=True
            if not key or v is None:continue
            is_eps='주당' in key
            value=v if is_eps else v*unit
            original.append(dict(label=row[0],value=value,unit='원/주' if is_eps else 'KRW'))
            if context=='income' and not any(w in key for w in ('포괄','계속','중단','주당','희석','기본','우선','보통')):
                if '지배' in key and '비지배' not in key:
                    parent_candidates.append(value);pending_parent=value
                elif '비지배' in key:
                    nci_candidates.append(value)
                    if pending_parent is not None:pairs.append((pending_parent,value))
                    pending_parent=None
                else:pending_parent=None
            if context=='income' and re.fullmatch(r'(?:당기|반기|분기)연결순(?:이익|손익)(?:\(손실\))?',key):
                values.setdefault('net_income',value)
                explicit_total=True
            if context=='income' and (key in ('분기','반기','당기') or re.fullmatch(r'부문(?:당기|반기|분기)순이익(?:\(손실\))?',key)):
                abbreviated_net.append(value)
            if context=='income' and key=='지배기업소유주지분순이익':
                if 'parent_net' in values:raise ValueError('귀속 손익 중복')
                values['parent_net']=value
            if context=='income' and key=='비지배지분순이익(손실)':
                if 'nci_net' in values:raise ValueError('귀속 손익 중복')
                values['nci_net']=value
            for dest,names in ALIASES[context].items():
                if key in names:
                    if dest in ambiguous:continue
                    if dest in values:
                        if dest=='revenue' and values[dest]==value:continue  # Identical parent/child presentation, never sum.
                        if context=='income' and dest=='net_income' and (attribution or explicit_total):
                            attributed_net=value;parent_candidates.append(value);pending_parent=value;continue
                        if context=='income' and dest in ('parent_net','nci_net'):continue
                        mandatory={'balance':{'assets','liabilities','equity'},'income':{'revenue','operating_profit','net_income'},'cash':{'ocf'}}[context]
                        if dest not in mandatory:
                            ambiguous.add(dest);values.pop(dest,None);continue
                        raise ValueError('계정 중복: '+dest)
                    values[dest]=-value if dest=='tax' and key=='법인세수익(비용)' else -abs(value) if dest=='operating_profit' and key=='영업손실' else value
        # Some public viewers abbreviate the total label to just "분기".
        # Accept only one numeric row corroborated by BOTH independent equations.
        if context=='income' and 'net_income' not in values and len(abbreviated_net)==1:
            candidate=abbreviated_net[0]
            if all(k in values for k in ('pretax','tax','parent_net','nci_net')) and (
                abs(values['pretax']-values['tax']-candidate)<=unit and
                abs(values['parent_net']+values['nci_net']-candidate)<=unit):
                values['net_income']=candidate
        if attributed_net is not None:
            if explicit_total and (not all(k in values for k in ('pretax','tax')) or abs(values['pretax']-values['tax']-values['net_income'])>unit):
                raise ValueError('연결 총손익 독립 대조 미확인')
            if 'nci_net' not in values or abs(attributed_net+values['nci_net']-values['net_income'])>unit:
                raise ValueError('귀속 손익 대조 불일치')
            values['parent_net']=attributed_net
        if context=='income' and 'net_income' in values:
            # Total, continuing-operation and comprehensive attribution can share labels.
            # Only the unique pair reconciled to TOTAL net profit supplies parent profit.
            matches={(p,n) for p,n in pairs if abs(p+n-values['net_income'])<=unit}
            if len(matches)==1:values['parent_net'],values['nci_net']=next(iter(matches))
            elif parent_candidates and nci_candidates:
                reference=reconciliation_reference(values,original,'income',unit)
                if reference:reconciliation_notes.update(reference)
                else:values.pop('parent_net',None);values.pop('nci_net',None)
        if context=='income' and 'parent_net' not in reconciliation_notes and all(k in values for k in ('parent_net','nci_net','net_income')) and abs(values['parent_net']+values['nci_net']-values['net_income'])>unit:
            values.pop('parent_net',None);values.pop('nci_net',None)
        if context=='balance' and all(k in values for k in ('parent_equity','nci','equity')) and abs(values['parent_equity']+values['nci']-values['equity'])>unit:
            reference=reconciliation_reference(values,original,'balance',unit)
            if reference:reconciliation_notes.update(reference)
            else:values.pop('parent_equity',None);values.pop('nci',None)
        if context=='balance' and 'parent_equity' not in values and all(k in values for k in ('equity','nci')):
            values['parent_equity']=values['equity']-values['nci']
        if context=='balance':
            debt=displayed_debt(original)
            if debt is not None:values['balance_debt']=debt
        if values:result[context]=values;raw[context]=original;units[context]=unit
        context=None
    if not all(k in result for k in ('balance','income','cash')):raise ValueError('3개 재무제표 또는 단위 미확인')
    b=result['balance'];i=result['income']
    if not all(k in b for k in ('assets','liabilities','equity')) or abs(b['assets']-b['liabilities']-b['equity'])>1e6:raise ValueError('대차 불일치')
    if not all(k in i for k in ('revenue','operating_profit','net_income')):raise ValueError('주요 손익 계정 미확인')
    return dict(code=code,name=name,market=market,basis=basis,year=year,quarter=quarter,period_end=end,
        available_at=available,receipt=receipt,url=url,values={**b,**i,**result['cash']},raw=raw,
        source='금융감독원 DART 공개 재무제표',unit='KRW',units=units,reconciliation_notes=reconciliation_notes,parser_version=10)


def quarter_records(reports, cutoff):
    """YTD differences within the same year/basis only; no 0 imputation."""
    reports=sorted(reports,key=lambda r:(r['basis'],r['period_end']));lookup={(r['basis'],r['year'],r['quarter']):r for r in reports}
    periods=[]
    for report in reports:
        if report['available_at']>cutoff or report['period_end']>cutoff:continue
        q=report['quarter'];prior=lookup.get((report['basis'],report['year'],q-1)) if q>1 else None
        current=report['values'];values=dict(current)
        for k in FLOW|CASH_FLOW:
            values[k]=(current[k] if q==1 else current[k]-prior['values'][k]
                       if prior and k in current and k in prior['values'] else None) if k in current else None
        # YTD EPS uses period-weighted shares. Subtracting two YTD EPS values
        # cannot recover quarterly EPS when the share count changes.
        values['eps']=current.get('eps') if q==1 else None
        # Cash opening balance is preceding quarter's closing cash, never a YTD sum.
        values['cash_start']=current.get('cash_start') if q==1 else prior['values'].get('cash_end') if prior else None
        available=max(report['available_at'],prior['available_at']) if prior else report['available_at']
        if available > cutoff: continue
        record=dict(period_end=report['period_end'],available_at=available,basis=report['basis'],cadence='quarter',
                    source=report['source'],source_url=report['url'],receipt=report['receipt'],**values)
        special=[r['label'] for r in report.get('raw',{}).get('income',[]) if label(r['label']) in ('매출액및기타수익','매출및지분법손익')]
        if special:record['cell_notes']={'revenue':'공시 표시 항목: '+special[0]+'; 순수 제품매출과 구성 차이 확인 필요'}
        for source_report in [report]+([prior] if prior else []):
            for field,note in source_report.get('reconciliation_notes',{}).items():
                if source_report is prior and field not in FLOW:continue
                message=f"{source_report['period_end']} 원문 명시 계정 참고 사용 · 귀속 합계 잔차 {note['difference_krw']:+,.0f}원 (1억원 미만) · 분기·TTM·비율의 오차 범위를 보장하지 않음"
                notes=record.setdefault('cell_notes',{})
                notes[field]=(notes.get(field,'')+' · '+message).strip(' ·')
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
            if periods and data.get('errors'):
                result[row['code']]['notes'].append('일부 과거 보고서는 조회·검증 대기입니다. 확보되지 않은 기간과 계정은 추정하지 않습니다.')
            if periods and data.get('cfs_unverified'):
                result[row['code']]['notes'].append('연결(CFS) 조회·검증 미확보: 확보된 별도(OFS) 재무를 구분해 제공합니다. 연결 수치로 대체하거나 합산하지 않습니다.')
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
        for context,a,b,total in [('income','parent_net','nci_net','net_income'),('balance','parent_equity','nci','equity')]:
            unit=r.get('units',{}).get(context,1)
            if type(unit) not in (int,float) or unit not in (1,1000,1000000):return False
            if all(k in v for k in (a,b,total)) and abs(v[a]+v[b]-v[total])>unit:
                observed=dict(v);reference=reconciliation_reference(observed,r.get('raw',{}).get(context,[]),context,unit)
                if observed!=v or not reference or any(r.get('reconciliation_notes',{}).get(k)!=note for k,note in reference.items()):return False
        return abs(v['assets']-v['liabilities']-v['equity'])<=1e6
    except (ValueError,KeyError,TypeError,AttributeError): return False
