"""Source-backed fiscal identities; calendar display dates are not fiscal quarters."""
import calendar
import re
from datetime import date,timedelta
from urllib.parse import urlsplit,parse_qs


def shift_month(start,months):
    value=start.year*12+start.month-1+months
    year,month=divmod(value,12)
    return date(year,month+1,min(start.day,calendar.monthrange(year,month+1)[1]))


def fiscal_bounds(fiscal_year,end_month,quarter):
    end=date(fiscal_year,end_month,calendar.monthrange(fiscal_year,end_month)[1])
    start=shift_month(end.replace(day=1),-11)
    return start,shift_month(start,quarter*3)-timedelta(days=1)


def valid_source(source):
    try:
        receipt=source['receipt'];url=urlsplit(source['url'])
        return bool(re.fullmatch(r'\d{14}',receipt) and url.scheme=='https' and url.netloc=='dart.fss.or.kr' and url.path.replace('//','/')=='/report/viewer.do' and parse_qs(url.query).get('rcpNo')==[receipt] and re.fullmatch(r'[a-f0-9]{64}',source['sha256']) and source['available_at']==date(int(receipt[:4]),int(receipt[4:6]),int(receipt[6:8])).isoformat())
    except (KeyError,ValueError,TypeError):return False


def validate_contract(contract, *, year=None,quarter=None,receipt=None,url=None,sha256=None):
    try:
        fy=contract['fiscal_year'];q=contract['fiscal_quarter'];month=contract['year_end_month']
        if type(fy) is not int or type(q) is not int or q not in (1,2,3,4) or type(month) is not int or not 1<=month<=12:raise ValueError()
        start,end=fiscal_bounds(fy,month,q)
        if contract['period_start']!=start.isoformat() or contract['period_end']!=end.isoformat():raise ValueError()
        if contract['currency'] not in ('KRW','USD') or not isinstance(contract['calendar_segment'],str) or not contract['calendar_segment'].strip():raise ValueError()
        if contract['report_kind']!=('annual' if q==4 else 'half' if q==2 else 'quarter'):raise ValueError()
        if not valid_source(contract['source']):raise ValueError()
        if year is not None and fy!=year or quarter is not None and q!=quarter:raise ValueError()
        if receipt is not None and receipt!=contract['source']['receipt'] or url is not None and url!=contract['source']['url'] or sha256 is not None and sha256!=contract['source']['sha256']:raise ValueError()
        columns=contract['current_columns']
        if set(columns)!=set(('balance','income','cash')):raise ValueError()
        for evidence in columns.values():
            if any(type(evidence.get(k)) is not int or evidence[k]<0 for k in ('title_row','header_row','header_column','value_column')) or evidence['title_row']!=1 or evidence['header_column']!=1 or evidence['value_column'] not in (1,2):raise ValueError()
            if not isinstance(evidence.get('label'),str) or not evidence['label'].strip():raise ValueError()
        return dict(contract)
    except (KeyError,ValueError,TypeError):raise ValueError('원문 근거 회계기간·통화·현재 열 계약 미확인') from None


def dates_in(text):
    found=[]
    for y,m,d in re.findall(r'(20\d{2})\s*(?:[.\-/]|년)\s*(\d{1,2})\s*(?:[.\-/]|월)\s*(\d{1,2})',text):
        try:found.append(date(int(y),int(m),int(d)).isoformat())
        except ValueError:raise ValueError('원문 기간 날짜 오류') from None
    return found


def verify_current_table(title_table,account_table,context,contract):
    evidence=contract['current_columns'][context]
    try:
        current=' '.join(title_table[evidence['title_row']])
        header=account_table[evidence['header_row']][evidence['header_column']]
        compact=lambda x:re.sub(r'\s+','',x)
        if compact(evidence['label']) not in compact(current) or compact(header)!=compact(evidence['label']):raise ValueError()
        dates=dates_in(current)
        expected=[contract['period_end']] if context=='balance' else [contract['period_start'],contract['period_end']]
        if dates!=expected:raise ValueError()
        # A comparative end elsewhere in the title cannot prove this current column.
        if evidence['value_column']==2:
            row=evidence.get('subheader_row');col=evidence.get('subheader_column')
            if type(row) is not int or type(col) is not int or account_table[row][col].strip()!='누적':raise ValueError()
        return evidence['value_column'],dict(title=current,header=header,value_column=evidence['value_column'],dates=dates)
    except (IndexError,KeyError,TypeError,ValueError):raise ValueError('현재 열의 회계기간·누적 열 일치 미확인: '+context) from None


def same_fiscal_identity(a,b):
    return all(a.get(k)==b.get(k) for k in ('code','basis','currency','fiscal_year','calendar_segment','period_start','year_end_month'))


def contiguous_quarters(columns):
    if len(columns)!=4:return False
    if not all(c.get('period_start') and c.get('currency') and c.get('calendar_segment') for c in columns):return False
    if len({(c.get('basis'),c['currency'],c['calendar_segment'],c.get('year_end_month')) for c in columns})!=1:return False
    try:
        for c in columns:
            start=date.fromisoformat(c['period_start']);end=date.fromisoformat(c['period_end'])
            if start.day!=1 or end!=shift_month(start,3)-timedelta(days=1):return False
        return all(date.fromisoformat(b['period_start'])==date.fromisoformat(a['period_end'])+timedelta(days=1) for a,b in zip(columns,columns[1:]))
    except (ValueError,KeyError,TypeError):return False
