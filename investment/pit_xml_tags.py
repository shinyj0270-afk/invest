"""Read optional consolidated annual facts from tagged DART value cells (XBRL `ACODE`/`ACONTEXT`).

The unit comes from the `(단위 : …)` caption, never from `ADECIMAL` (real notes in thousand won carry `ADECIMAL="0"`). The text is walked once with a stack of open tables; a cell's caption is
looked for, in this order, (1) inside the cell's own table before the cell, (2) in the text between the previous table and this table (at most MAX_GAP characters before the table), (3) inside the previous
table when that table holds no tags (a statement title table). The caption of a previous table that holds tagged values is never inherited.
"""
from html import unescape
import re

CONCEPTS = {
    'ifrs-full_LeaseLiabilities': ('lease_total', 'e'),
    'ifrs-full_CurrentLeaseLiabilities': ('lease_current', 'e'),
    'ifrs-full_NoncurrentLeaseLiabilities': ('lease_noncurrent', 'e'),
    'ifrs-full_ShorttermDepositsNotClassifiedAsCashEquivalents': ('short_term_financial_instruments', 'e'),
    'ifrs-full_DepreciationAndAmortisationExpense': ('da_total', 'd')}
CONTEXT = 'FY_ifrs-full_ConsolidatedAndSeparateFinancialStatementsAxis_ifrs-full_ConsolidatedMember'
EVENT = re.compile(r'<TABLE\b|</TABLE\s*>|\(\s*단위\s*:\s*([^()]*)\)|<TE\b([^>]*)>', re.I)
ATTRS = re.compile(r'''\b([\w:-]+)\s*=\s*(["'])(.*?)\2''', re.S)
CELL_END = re.compile(r'</TE\s*>', re.I)
UNITS = {'원': 1, '천원': 1000, '백만원': 1000000}
MAX_GAP = 2500


def _caption(raw, position):
    """(factor, position) of a caption token; the factor is None for an unsupported unit."""
    return UNITS.get(re.sub(r'\s+', '', raw)), position


def _unit(stack, pending, position):
    """The unit factor for a cell at `position`, or None when no caption applies."""
    if not stack:return pending[0] if pending and position-pending[1] <= MAX_GAP else None
    table=stack[-1]
    if table['inside']:return table['inside'][0]
    before=table['before']
    if before and table['at']-before[1] <= MAX_GAP:return before[0]
    previous=table['previous']
    return previous[0][0] if previous and previous[0] and not previous[1] else None


def read_tagged(text, *, year):
    """(values, notes): scaled values and the first problem for each qualifying field."""
    return read_tagged_detail(text, year=year)[:2]


def read_tagged_detail(text, *, year):
    """(values, notes, units): like `read_tagged` plus the scale factor of each kept value. Facts of one field agree within half of the larger unit (table rounding); the finer value is kept."""
    from .pit_xml import _amount
    values={}; notes={}; units={}; stack=[]; pending=None; previous=None
    for token in EVENT.finditer(text):
        if token.group(1) is not None:
            caption=_caption(token.group(1), token.start())
            if stack:stack[-1]['inside']=caption
            else:pending=caption
        elif token.group(2) is not None:
            attrs={name.upper(): value for name, _, value in ATTRS.findall(token.group(2))}
            if 'ACODE' not in attrs:continue
            for table in stack:table['tagged']=True
            concept=CONCEPTS.get(attrs.get('ACODE'))
            if concept is None:continue
            field, period=concept
            if attrs.get('ACONTEXT') != f'CFY{year}{period}{CONTEXT}' or field in notes:continue
            end=CELL_END.search(text, token.end())
            body=text[token.end():end.start() if end else len(text)]
            reason=None
            try:value=_amount(unescape(re.sub(r'<[^>]*>', '', body)), 1)
            except (ValueError, TypeError, OverflowError):reason='bad_number'
            if not reason:
                if attrs.get('ANEGATED') == 'Y':value=-value
                if value < 0:reason='negative'
            unit=_unit(stack, pending, token.start())
            if not reason and unit is None:reason='unit_unknown'
            if not reason:
                value*=unit
                if field in values and abs(values[field]-value) > max(units[field], unit)/2:reason='conflict'
            if reason:
                notes={**notes, field: reason}
                values={key: value for key, value in values.items() if key != field}
                units={key: value for key, value in units.items() if key != field}
            elif field not in values or unit < units[field]:values={**values, field: value}; units={**units, field: unit}
        elif token.group(0)[1] == '/':
            if stack:
                closed=stack.pop(); previous=(closed['inside'], closed['tagged'])
            pending=None
        else:
            stack.append({'at': token.start(), 'before': pending, 'previous': previous, 'inside': None, 'tagged': False})
            pending=None
    return values, notes, units
