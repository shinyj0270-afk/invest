"""Optional annual accounts; ambiguous rows are omitted with reason codes."""

_BORROWINGS = (
    ('차입금', '사채', '전환사채', '신주인수권부사채', '차입금및사채', '사채및차입금', '교환사채'),
    ('단기차입금', '유동성장기차입금', '유동성사채', '단기사채', '유동성전환사채', '유동성신주인수권부사채', '유동성장기사채', '당좌차월'),
    ('장기차입금', '장기사채', '비유동차입금', '비유동사채', '장기차입금(사채포함)', '사채및장기차입금'))
_LEASE = (('리스부채',), ('유동리스부채', '유동성리스부채', '단기리스부채'), ('비유동리스부채', '비유동성리스부채', '장기리스부채'))
_NOT_COUNTED = ('판매후리스부채', '비유동판매후리스부채')       # sale-and-leaseback financing: not a lease in the tags (CurrentLeaseLiabilities excludes it), so it is skipped
_PRETAX = ('법인세비용차감전순이익', '법인세차감전순이익', '법인세비용차감전계속영업이익', '법인세비용차감전계속사업이익', '법인세비용차감전계속영업순이익')
_LOSSES = ('당기순손실', '법인세비용차감전순손실', '법인세차감전순손실')
_TAX_INCOME = ('법인세수익', '법인세수익(비용)')       # a tax BENEFIT is shown positive here: the sign is settled by the identity
_CONTINUING = ('계속영업이익', '계속영업이익(손실)', '계속영업당기순이익', '계속영업당기순이익(손실)', '계속영업순이익', '계속영업순이익(손실)')     # only a target of the identity, never exported
_ALIASES = {
    'balance': {'total_assets': ('자산총계',), 'total_liabilities': ('부채총계',),
                'short_term_financial_instruments': ('단기금융상품',)},
    'income': {'finance_costs': ('금융비용', '금융원가'),
               'pretax_income': _PRETAX + tuple(label+'(손실)' for label in _PRETAX) + _LOSSES[1:],
               'income_tax_expense': ('법인세비용', '법인세비용(수익)', '법인세비용(환입)', '계속영업법인세비용') + _TAX_INCOME,
               'net_income_total': ('당기순이익', '당기순이익(손실)', '당기순손익', '연결당기순이익', '연결당기순이익(손실)', '당기연결순이익', '당기순손실'),
               'interest_expense': ('이자비용',)},
    'cash': {'depreciation': ('감가상각비', '유형자산감가상각비'), 'amortization': ('무형자산상각비',),
             'rou_depreciation': ('사용권자산상각비',), 'interest_expense': ('이자비용',),
             'capex_tangible': ('유형자산의취득',), 'capex_intangible': ('무형자산의취득',),
             'dividends_paid': ('배당금의지급', '배당금지급')}}
_SECTIONS = {'유동자산': 'assets_current', '비유동자산': 'assets_noncurrent',
             '유동부채': 'current', '비유동부채': 'noncurrent'}
_LIQUID_FINANCIAL = ('당기손익-공정가치금융자산', '당기손익-공정가치측정금융자산', '기타포괄손익-공정가치금융자산', '기타포괄손익-공정가치측정금융자산',
                   '유동금융자산', '단기투자자산', '단기매매금융자산')       # 기타금융자산 is deliberately absent: it mixes in non-liquid items
_CLOSE = ('부채총계', '자본', '자본총계', '자산총계', '부채', '자산')
_OUTFLOWS = ('capex_tangible', 'capex_intangible', 'dividends_paid', 'finance_costs')       # stored as magnitudes (a statement may print a cost as a deduction)
_SIGNED = ('pretax_income', 'income_tax_expense', 'net_income_total')
_NEGATIVE_OK = _SIGNED + ('_continuing',)
IDENTITY_UNITS = 3      # pretax_income - income_tax_expense = net_income_total may be off by this many statement units (rounding)


def read_accounts(kind, rows, *, unit, first, columns, positional=False):
    """Return readable fields and soft failures for one statement body.

    `positional` (period-number layout): the cells after the label are the period columns, so the current amount is the first one; later cells may be blank, and a blank current cell
    (with a later cell filled) reads as 0 because that format leaves zeros blank. A row with every cell blank is a heading."""
    from .pit_xml import _label, _amount
    aliases={label: field for field, labels in _ALIASES[kind].items() for label in labels}
    families={label: (family, required) for family, groups in (('borrowings', _BORROWINGS), ('lease', _LEASE))
              for required, labels in zip((None, 'current', 'noncurrent'), groups) for label in labels}
    values={}; notes={}; seen=set(); section=None; deferred={}
    for row in rows:
        if not row:continue
        label=_label(row[0])
        if kind == 'balance':
            if label in _SECTIONS:section=_SECTIONS[label]
            elif label in _CLOSE:section=None
        cells=row[first:]
        amounts=[cell for cell in cells if cell]
        if not amounts:continue
        if positional:amounts, counted=[cells[0] or '-'], len(cells) <= columns       # a blank current cell is a zero: the period-number layout leaves zeros blank
        else:amounts=drop_dashes(amounts, columns); counted=len(amounts) == columns
        family, required=families.get(label, (None, None)) if kind == 'balance' else (None, None)
        field=aliases.get(label); reason=None
        if family:
            field=family+'_'+str(section)
            if section is None:reason='section_unknown'
            elif section not in ('current', 'noncurrent') or required and section != required:reason='section_mismatch'
        elif kind == 'balance' and label in _LIQUID_FINANCIAL:
            if section == 'assets_noncurrent':continue
            field='current_financial_assets'
            if section != 'assets_current':reason='section_unknown' if section is None else 'section_mismatch'
        elif kind == 'balance' and label in _NOT_COUNTED:continue
        elif kind == 'balance' and section in ('current', 'noncurrent') and any(word in label for word in ('차입금', '사채', '리스부채', '당좌차월')):
            family='lease' if '리스부채' in label else 'borrowings'
            notes={**notes, family: 'unclassified'}
            continue
        elif kind == 'income' and label in _CONTINUING:field='_continuing'
        if field is None:continue
        summed=bool(family) or field == 'current_financial_assets'
        key=family or field
        identity=(section, label) if summed else field
        duplicate=identity in seen
        seen.add(identity)
        if field == 'short_term_financial_instruments' and section != 'assets_current':reason=reason or 'section_mismatch'
        if not counted:reason=reason or 'amount_count'
        if not reason:
            try:parsed=[_amount(cell, unit) for cell in amounts]
            except (ValueError, TypeError, OverflowError):reason='bad_number'
        if not reason:
            if label in _LOSSES and parsed[0] > 0 or label in _TAX_INCOME:
                deferred={**deferred, field: (parsed[0], 'unsupported_label' if label in _TAX_INCOME else 'sign_unclear', None)}
                continue
            if field == 'income_tax_expense' and parsed[0] < 0:                              # a benefit, or an expense printed as a deduction: the identity decides, else as shown
                deferred={**deferred, field: (parsed[0], 'sign_unclear', parsed[0])}
                continue
            if field not in _NEGATIVE_OK + _OUTFLOWS and parsed[0] < 0:reason='negative'
        if reason:
            notes={**notes, key: notes.get(key, reason)}
            continue
        value=abs(parsed[0]) if field in _OUTFLOWS else parsed[0]
        if duplicate:                                                                       # a repeat that says the same thing counts once, any other repeat is a duplicate
            if not summed and values.get(field) == value:continue
            notes={**notes, key: notes.get(key, 'duplicate')}
            continue
        values={**values, field: values.get(field, 0)+value if summed else value}
    continuing=None if '_continuing' in notes else values.get('_continuing')
    values={f: v for f, v in values.items() if f != '_continuing'}; notes={f: r for f, r in notes.items() if f != '_continuing'}
    if deferred:values, notes=_resolve(values, notes, deferred, unit, continuing)
    values={field: value for field, value in values.items()
            if field not in notes and not any(field.startswith(family+'_') for family in ('borrowings', 'lease') if family in notes)}
    return values, notes


def drop_dashes(amounts, columns):
    """More non-empty cells than period columns: `-` placeholder cells (a zero detail cell next to its subtotal) are dropped when that makes the count fit."""
    if len(amounts) > columns:
        kept=[cell for cell in amounts if cell.replace(' ', '') != '-']
        if len(kept) == columns:return kept
    return amounts


def _candidates(field, shown):
    return tuple(dict.fromkeys((-shown, shown) if field == 'income_tax_expense' else (shown, -shown)))


def _resolve(values, notes, deferred, unit, continuing):
    """Signs the labels do not settle are taken only when exactly one combination satisfies pretax - tax = net income (or = continuing income).
    A negative tax that cannot be evaluated stays as shown; every other deferred field keeps its old note."""
    options={field: _candidates(field, deferred[field][0]) if field in deferred else (values[field],)
             for field in _SIGNED if field in deferred or field in values and field not in notes}
    pretax, tax, net=(options.get(field) for field in _SIGNED)
    tolerance=IDENTITY_UNITS*unit
    evaluable=bool(pretax and tax and (net or continuing is not None))
    fits=lambda p, t, n: n is not None and abs(p-t-n) <= tolerance or continuing is not None and abs(p-t-continuing) <= tolerance
    matches=[(p, t, n) for p in pretax for t in tax for n in (net or (None,)) if fits(p, t, n)] if evaluable else []
    if len(matches) == 1:
        chosen=dict(zip(_SIGNED, matches[0]))
        return {**values, **{f: chosen[f] for f in deferred}}, notes
    kept={f: deferred[f][2] for f in deferred if not evaluable and deferred[f][2] is not None}
    return {**values, **kept}, {**notes, **{f: notes.get(f, deferred[f][1]) for f in deferred if f not in kept}}


def _merge(values, incoming, notes, incoming_notes):
    """Keep conflicts sticky across any number of copies."""
    conflicts={field: 'conflict' for field, value in incoming.items() if field in values and values[field] != value}
    notes={**notes, **incoming_notes, **conflicts,
           **{field: reason for field, reason in notes.items() if reason == 'conflict'}}
    values={field: value for field, value in {**values, **incoming}.items()
            if field not in notes and not any(field.startswith(family+'_') for family in ('borrowings', 'lease') if family in notes)}
    return values, notes
