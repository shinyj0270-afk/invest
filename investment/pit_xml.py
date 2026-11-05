"""Read consolidated annual DART XML tables and ZIP bytes without external I/O."""
from collections import Counter
from datetime import date
from html.parser import HTMLParser
import hashlib
import io
import re
import zipfile
from .pit_xml_accounts import read_accounts, drop_dashes, _merge, COMPANY_LABELS, COMPANY_NOTE_FACTS, COMPANY_BORROWINGS_INCLUDE_LEASE
from .pit_xml_tags import read_tagged_detail

PARSER_VERSION = 'pit-xml-1'
MAX_MEMBERS = 50
MAX_MEMBER_BYTES = 64 * 1024 * 1024
LOSS_LABELS = ('영업손실',)       # shown as a negative amount, this IS the operating profit; a positive amount has an unclear sign
GROSS_LABELS = ('매출총이익', '매출총이익(손실)', '매출총손익')       # operating profit = gross profit - selling and administrative expenses decides a positive loss amount
SELLING_LABELS = ('판매비와관리비', '판매비및관리비', '판매관리비')
LOSS_IDENTITY_UNITS = 3      # gross profit - selling expenses may be off from the operating line by this many statement units (rounding)
TITLES = {'연결재무상태표': 'balance', '연결손익계산서': 'income',
          '연결포괄손익계산서': 'income', '연결현금흐름표': 'cash'}
ALIASES = {
    'balance': {'equity': ('자본총계',), 'cash': ('현금및현금성자산',)},
    'income': {'revenue': ('매출액', '수익', '영업수익', '수익(매출액)', '매출액(수익)', '매출',
                           '매출액(영업수익)', '영업수익(매출액)'),
               'operating_profit': ('영업이익', '영업이익(손실)', '영업손익', '영업이익(영업손실)', '영업손실')},
    'cash': {'ocf': ('영업활동현금흐름', '영업활동으로인한현금흐름', '영업활동으로인한순현금흐름',
                     '영업활동순현금흐름', '영업활동으로인한현금유출입', '영업활동으로인한현금흐름(유출)')}}


class NoStatements(ValueError):
    """No recognized title followed by an account table."""


class Tables(HTMLParser):
    def __init__(self, nested=False):
        super().__init__(convert_charrefs=True)
        self.tables=[]; self.table=None; self.row=None; self.cell=None; self.depth=0
        self.nested=nested; self.stack=[]

    def _cell_end(self):
        if self.cell is not None:
            if self.row is None:self.row=[]
            self.row.append(' '.join(''.join(self.cell).split())); self.cell=None

    def _row_end(self):
        self._cell_end()
        if self.row is not None:
            self.table.append(self.row); self.row=None

    def handle_starttag(self, tag, attrs):
        tag=tag.lower()
        if tag == 'table':
            if self.nested:
                self.stack.append((self.table, self.row, self.cell))
                self.table=[]; self.row=None; self.cell=None
                self.tables.append(self.table)
            elif not self.depth:self.table=[]
            self.depth+=1
        elif self.depth and (self.nested or self.depth == 1):
            if tag == 'tr':self._row_end(); self.row=[]
            elif tag in ('td', 'th', 'te'):self._cell_end(); self.cell=[]
            elif tag == 'br' and self.cell is not None:self.cell.append(' ')

    def handle_data(self, value):
        if self.cell is not None:self.cell.append(value)

    def handle_endtag(self, tag):
        tag=tag.lower()
        if tag == 'table' and self.depth:
            if self.nested:
                self._row_end()
                self.table, self.row, self.cell=self.stack.pop()
            elif self.depth == 1:
                self._row_end(); self.tables.append(self.table); self.table=None
            self.depth-=1
        elif self.depth and (self.nested or self.depth == 1):
            if tag in ('td', 'th', 'te'):self._cell_end()
            elif tag == 'tr':self._row_end()

    def unknown_decl(self, data):
        pass

    def parse_html_declaration(self, index):
        try:return super().parse_html_declaration(index)
        except AssertionError:
            end=self.rawdata.find('>', index+2)
            if end < 0:return -1
            self.handle_data(self.rawdata[index:end+1])
            return end+1


def _compact(text):
    return re.sub(r'\s+', '', text)


def _label(text):
    text=re.sub(r'^(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫIVXivx]+[.．]|[0-9]+[.．)])', '', _compact(text), count=1)
    return re.sub(r'\(주[0-9,]+\)$', '', text.removeprefix('ㆍ'))


def _amount(text, unit):
    text=_compact(text).replace(',', '')
    if text == '-':return 0
    if re.fullmatch(r'\([0-9]+\)', text):text='-'+text[1:-1]
    elif text.startswith(('△', '▲')):text='-'+text[1:]
    if not re.fullmatch(r'-?[0-9]+', text):raise ValueError('금액 형식 오류')
    return int(text)*unit


def _current_period_cells(cells):
    """Period lines marked (당) win; otherwise the line(s) with the larger period number ('제 49 기' vs '제 48 기'), which needs two different numbers."""
    compact=[_compact(cell) for cell in cells]
    marked=[cell for cell in compact if '(당)' in cell]
    if marked:return marked
    numbered=[(int(m.group(1)), cell) for cell in compact if re.search(r'[0-9]{4}년[0-9]{1,2}월[0-9]{1,2}일', cell)
              for m in [re.search(r'제([0-9]+)(?:\(전\))?기', cell)] if m]
    if len({number for number, _ in numbered}) < 2:return []
    top=max(number for number, _ in numbered)
    return [cell for number, cell in numbered if number == top]


def _title_cells(table):
    return [re.sub(r'(?<![0-9])([0-9]{4})\s*\.\s*([0-9]{1,2})\s*\.\s*([0-9]{1,2})(?![0-9])', r'\1년\2월\3일', cell)
            for row in table for cell in row]


def _title_unit(table, kind, year):
    cells=_title_cells(table)
    units={match.group(1).strip() for cell in cells for match in re.finditer(r'\(\s*단위\s*:\s*([^()]*)\)', cell)}
    multipliers={'원': 1, '천원': 1000, '백만원': 1000000}
    if len(units) != 1 or not units <= multipliers.keys():raise ValueError('재무제표 단위 오류')
    current=_current_period_cells(cells)
    end=rf'(?<![0-9]){year}년0?12월0?31일'
    start=rf'(?<![0-9]){year}년0?1월0?1일부터'
    if not current or any(not re.search(end, cell) or (kind != 'balance' and not re.search(start, cell)) for cell in current):
        raise ValueError('당기 사업연도 오류')
    return multipliers[next(iter(units))]


def _sector_cash(table, unit, candidates, year):
    """Combine two disjoint cash sections only with independent closing-cash proof."""
    rows=table[1:]; section=None; hits=[]
    for i, row in enumerate(rows, 1):
        label=_label(row[0]) if row else ''
        if label in ('유동자산', '비유동자산', '금융업자산', '자산총계'):section=label
        if label == '현금및현금성자산':hits=hits+[(i, section, row)]
    if len(hits) < 2:return table
    if len(hits) != 2 or tuple(h[1] for h in hits) != ('유동자산', '금융업자산'):
        raise ValueError('동일 계정 중복 오류')
    def current(row, header, multiplier):
        note=len(header) > 1 and _compact(header[1]) == '주석'
        cells=row[1+note:]; columns=header[1+note:]
        numbered=all(re.fullmatch(r'제[0-9]+기말?', _compact(c)) for c in columns)
        if numbered and len(cells) == len(columns):return _amount(cells[0] or '-', multiplier)
        amounts=drop_dashes([c for c in cells if c], len(columns))
        if len(amounts) != len(columns):raise ValueError('계정 금액 개수 오류')
        return _amount(amounts[0], multiplier)
    total=sum(current(row, table[0], unit) for _, _, row in hits)
    closing=[current(row, body[0], _title_unit(title, 'cash', year))
             for name, title, body in candidates if TITLES[name] == 'cash'
             for row in body[1:] if row and _label(row[0]) in ('기말현금및현금성자산', '기말의현금및현금성자산', '기말재무상태표상현금및현금성자산')]
    if not closing or any(value != total for value in closing):
        raise ValueError('금융업 구분 현금 합계 불일치')
    first, _, original=hits[0]; second=hits[1][0]
    note=len(table[0]) > 1 and _compact(table[0][1]) == '주석'
    cells=original[1+note:]; position=next(i for i, cell in enumerate(cells) if cell)
    replacement=original[:1+note]+[str(total//unit) if i == position else c for i, c in enumerate(cells)]
    return [replacement if i == first else row for i, row in enumerate(table) if i != second]


def _opening_balance_columns(kind, columns, title):
    """Current close, previous close, previous opening: three instants, two periods."""
    if kind != 'balance' or len(columns) != 3:return False
    matches=[re.fullmatch(r'제([0-9]+)(?:\(([당전])\))?기(기말|말|기초|초)', c) for c in columns]
    if not all(matches):return False
    periods=[int(m.group(1)) for m in matches]
    if periods != [periods[0], periods[0]-1, periods[0]-1]:return False
    if [m.group(3) for m in matches] not in (['기말', '기말', '기초'], ['말', '말', '초']):return False
    if any(m.group(2) not in (None, mark) for m, mark in zip(matches, ('당', '전', '전'))):return False
    dated=[(int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
           for cell in map(_compact, _title_cells(title))
           for m in [re.search(r'제([0-9]+)기.*?([0-9]{4})년([0-9]{1,2})월([0-9]{1,2})일', cell)] if m]
    current=[d for d in dated if d[0] == periods[0]]
    if len(current) != 1:return False
    year=current[0][1]
    return set(dated) == {(periods[0], year, 12, 31), (periods[1], year-1, 12, 31), (periods[2], year-1, 1, 1)}


def _row_amounts(table, names, unit, first, columns):
    """The amounts of the one row labelled with one of `names`; None when it is absent, repeated or unreadable."""
    rows=[row for row in table if row and _label(row[0]) in names]
    if len(rows) != 1:return None
    amounts=drop_dashes([cell for cell in rows[0][first:] if cell], columns)
    if len(amounts) != columns:return None
    try:return [_amount(cell, unit) for cell in amounts]
    except ValueError:return None


def _settle_loss_sign(shown, table, unit, first):
    """A positive amount under 영업손실 has an unclear sign. The statement's own identity decides it: gross profit - selling and administrative
    expenses must match exactly one of +shown / -shown within LOSS_IDENTITY_UNITS statement units. Without both rows, or when neither or both
    candidates match, the sign stays unclear (None)."""
    columns=len(shown)
    gross=_row_amounts(table, GROSS_LABELS, unit, first, columns)
    selling=_row_amounts(table, SELLING_LABELS, unit, first, columns)
    if gross is None or selling is None:return None
    settled=[]
    for amount, profit, cost in zip(shown, gross, selling):
        if amount <= 0:settled.append(amount); continue
        matches=[candidate for candidate in (amount, -amount) if abs(candidate-(profit-cost)) <= LOSS_IDENTITY_UNITS*unit]
        if len(matches) != 1:return None
        settled.append(matches[0])
    return settled


def _statement(table, kind, unit, title, extra_labels=None, core_table=None):
    header=[_compact(cell) for cell in table[0]]
    note=len(header) > 1 and header[1] == '주석'
    columns=header[1+note:]
    opening=_opening_balance_columns(kind, columns, title)
    numbered=opening or len(columns) in (2, 3) and all(re.fullmatch(r'제[0-9]+기말?', column) for column in columns)
    widths=Counter(len(row) for row in table[1:] if row)
    positional=numbered and bool(widths) and widths.most_common(1)[0][0] <= 1+note+len(columns)      # one cell per period column, else detail and subtotal cells (grouped)
    if numbered:
        periods=[int(re.search(r'[0-9]+', column).group()) for column in columns]
        if not opening and any(a-b != 1 for a, b in zip(periods, periods[1:])):raise ValueError('당기와 전기 금액 열 오류')
        numbers={int(m.group(1)) for cell in map(_compact, _title_cells(title)) if re.search(r'[0-9]{4}년[0-9]{1,2}월[0-9]{1,2}일', cell)
                 for m in [re.search(r'제([0-9]+)기', cell)] if m}
        if len(numbers) < 2 or max(numbers) != periods[0]:raise ValueError('당기 사업연도 오류')
    elif header[0] != '과목' or len(columns) != 2 or re.findall(r'\((?:당|전|전전)\)', columns[0]) != ['(당)'] or re.findall(r'\((?:당|전|전전)\)', columns[1]) != ['(전)']:
        raise ValueError('당기와 전기 금액 열 오류')
    aliases={alias: field for field, names in ALIASES[kind].items() for alias in names}
    values={}; seen=set()
    for row in (core_table or table)[1:]:
        field=aliases.get(_label(row[0])) if row else None
        if field is None:continue
        if field in seen:raise ValueError('동일 계정 중복 오류')
        seen.add(field)
        amounts=drop_dashes([cell for cell in row[1+note:] if cell], len(columns))
        if not amounts and not positional:continue
        if len(amounts) != len(columns):raise ValueError('계정 금액 개수 오류')
        parsed=[_amount(cell, unit) for cell in amounts]
        if _label(row[0]) in LOSS_LABELS and any(value > 0 for value in parsed):
            parsed=_settle_loss_sign(parsed, table[1:], unit, 1+note)
            if parsed is None:raise ValueError('영업손실 금액 부호 불명확')
        values={**values, field: parsed[0]}
    extra, notes=read_accounts(kind, table[1:], unit=unit, first=1+note, columns=len(columns), positional=positional, extra_labels=extra_labels)
    return {**values, **extra}, notes


def _annual_title(title):
    """A title that names a half-year or a quarter belongs to an interim statement, which is never read."""
    return not any(re.search('반기|분기', _compact(cell)) for row in title for cell in row)


def parse_statements(text, *, year, extra_labels=None):
    """Return found annual fields in KRW; missing statement kinds are allowed."""
    if not isinstance(text, str) or not text:raise ValueError('문자열 원문이 필요합니다')
    if not isinstance(year, int) or isinstance(year, bool) or not 1990 <= year <= 2100:raise ValueError('사업연도 오류')
    candidates=[]
    for nested in (False, True):
        parser=Tables(nested=nested); parser.feed(text); parser.close()
        for title, account in zip(parser.tables, parser.tables[1:]):
            name=_compact(title[0][0]) if title and len(title[0]) == 1 else ''
            if name in TITLES and account and account[0] and _compact(account[0][0]) in ('', '과목') and _annual_title(title):
                candidates.append((name, title, account))
        if candidates:break
    if not candidates:raise NoStatements('연결 재무제표가 없습니다')
    income=any(name == '연결손익계산서' for name, _, _ in candidates)
    copies={}; counts={}; first_unit=None; values={}; notes={}
    for name, title, account in candidates:
        if income and name == '연결포괄손익계산서':continue
        kind=TITLES[name]; unit=_title_unit(title, kind, year)
        core_table=_sector_cash(account, unit, candidates, year) if kind == 'balance' else None
        found, problems=_statement(account, kind, unit, title, extra_labels, core_table=core_table)
        original={field: value for field, value in found.items() if field in ALIASES[kind]}
        if kind in copies and copies[kind] != original:raise ValueError('재무제표 사본 값 불일치')
        copies={**copies, kind: original}; counts={**counts, kind: counts.get(kind, 0)+1}
        values, notes=_merge(values, found, notes, problems)
        if first_unit is None:first_unit=unit
    tagged, problems, units=read_tagged_detail(text, year=year)
    tagged={field: value for field, value in tagged.items() if not (field in values and abs(values[field]-value) <= units[field]/2)}      # same value within the tag's rounding: the statement value stays
    values, merged_notes=_merge(values, tagged, notes, problems)
    notes={**merged_notes, **notes}
    listed=bool(values.get('_assets_listed'))
    values={k: v for k, v in values.items() if k != '_assets_listed'}
    if not values:raise ValueError('사용 가능한 계정이 없습니다')
    return dict(values=values, notes=notes, assets_listed=listed, basis='CFS', currency='KRW', unit=first_unit or 1,
                period_start=f'{year}-01-01', period_end=f'{year}-12-31', statements=counts)


LIQUID_FIELDS = ('short_term_financial_instruments', 'current_financial_assets')


def _confirm_zeros(parsed, listed):
    """The face lists every current asset (lines add up to the total): a liquid line that is absent after statements AND tags is a confirmed zero."""
    if not listed:return parsed
    zeros={f: 0 for f in LIQUID_FIELDS if f not in parsed['values'] and f not in parsed['notes']}
    return {**parsed, 'values': {**zeros, **parsed['values']}}


def _record(parsed, *, receipt, year, url, sha256):
    if not isinstance(receipt, str) or not re.fullmatch(r'[0-9]{14}', receipt):raise ValueError('접수번호 형식 오류')
    try:date(int(receipt[:4]), int(receipt[4:6]), int(receipt[6:8]))
    except ValueError as exc:raise ValueError('접수번호 날짜 오류') from exc
    if not isinstance(sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', sha256):raise ValueError('해시 형식 오류')
    return dict(basis='CFS', quarter=4, year=year, currency='KRW', unit='KRW',
                period_start=parsed['period_start'], period_end=parsed['period_end'],
                receipt=receipt, url=url, parser_version=PARSER_VERSION, values=dict(parsed['values']),
                period_contract={'report_kind': 'annual', 'source': {'sha256': sha256}})


def build_record(text, *, receipt, year, url, sha256):
    """Build the annual record consumed by pit_values.map_record."""
    parsed=parse_statements(text, year=year)
    return _record(_confirm_zeros(parsed, parsed['assets_listed']), receipt=receipt, year=year, url=url, sha256=sha256)


def _read_member(archive, member, year, extra_labels=None):
    with archive.open(member) as stream:data=stream.read(MAX_MEMBER_BYTES+1)
    if len(data) > MAX_MEMBER_BYTES:raise ValueError('XML 파일 크기 초과')
    for encoding in ('utf-8', 'cp949'):
        try:text=data.decode(encoding)
        except UnicodeDecodeError:continue
        try:return parse_statements(text, year=year, extra_labels=extra_labels)
        except NoStatements:return None
    return None


def _exclude_confirmed_leases(parsed, company, year):
    """Only source-verified inclusive debt totals can have leases subtracted."""
    expected=COMPANY_BORROWINGS_INCLUDE_LEASE.get((company, year))
    if expected is None:return parsed
    values=parsed['values']; converted={}
    for suffix, shown in expected.items():
        debt=values.get('borrowings_'+suffix); lease=values.get('lease_'+suffix)
        if debt != shown or lease is None or not 0 <= lease <= debt:
            raise ValueError('리스 포함 차입금 범위 미확인')
        converted={**converted, 'borrowings_'+suffix: debt-lease}
    return {**parsed, 'values': {**values, **converted}}


def parse_document_zip(data, *, receipt, year, url, company=None):
    """Merge agreeing XML members in memory; never interpret names as paths."""
    try:data=memoryview(data).tobytes()
    except (TypeError, ValueError) as exc:raise ValueError('ZIP 바이트가 필요합니다') from exc
    merged=None; listed=False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members=[member for member in archive.infolist() if member.filename.lower().endswith('.xml')]
            if len(members) > MAX_MEMBERS:raise ValueError('XML 파일 개수 초과')
            if any(member.file_size > MAX_MEMBER_BYTES for member in members):raise ValueError('XML 파일 크기 초과')
            if sum(member.file_size for member in members) > 2*MAX_MEMBER_BYTES:raise ValueError('XML 전체 크기 초과')
            for member in members:
                parsed=_read_member(archive, member, year, COMPANY_LABELS.get(company))
                if parsed is None:continue
                listed=listed or parsed['assets_listed']
                if merged is None:merged=parsed; continue
                if any(merged[key] != parsed[key] for key in ('period_start', 'period_end')):raise ValueError('문서 기간 불일치')
                original={field for fields in ALIASES.values() for field in fields}
                tolerance=max(merged['unit'], parsed['unit'])                                       # the same value rounded differently by two members
                if any(abs(merged['values'][key]-value) > tolerance for key, value in parsed['values'].items() if key in original and key in merged['values']):
                    raise ValueError('문서 계정 값 불일치')
                agreed={key: merged['values'][key] if key in merged['values'] and abs(merged['values'][key]-value) <= tolerance else value for key, value in parsed['values'].items()}      # a value within the rounding keeps the first member's
                values, notes=_merge(merged['values'], agreed, merged['notes'], parsed['notes'])
                merged={**merged, 'values': values, 'notes': notes}
    except zipfile.BadZipFile as exc:raise ValueError('ZIP 형식 오류') from exc
    if merged is None:raise ValueError('사용 가능한 XML 문서가 없습니다')
    merged=_confirm_zeros(merged, listed)
    facts=COMPANY_NOTE_FACTS.get((company, year), {})
    merged={**merged, 'values': {**{k: v for k, v in facts.items() if k not in merged['values']}, **merged['values']}}      # hand-read note facts fill absent fields only
    merged=_exclude_confirmed_leases(merged, company, year)
    return _record(merged, receipt=receipt, year=year, url=url, sha256=hashlib.sha256(data).hexdigest())
