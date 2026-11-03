"""Map a parsed annual DART record (`dart_statements.parse_viewer` output, current-year column) to a `pit_annual` receipt.

Pure function, no network. Scope checks live here (full calendar year, KRW, annual report, CFS/OFS); `pit_annual` only checks
a December end date and partitions by basis. Mapped fields: revenue, op, ocf, equity, cash. `balance_debt` (identified loans
and bonds only, NOT total financial or lease debt) is mapped to `debt` only when the caller accepts that scope. Tax rate,
tax verification and dividends are never mapped (the parser has no support for them). Nothing is imputed.
The key names follow `dart_statements.py`; they are PROVISIONAL until checked against one real record at the first live call.
"""
from datetime import date
from math import isfinite
import re

MAPPING_VERSION = 'pit-values-1'
FIELDS = (('revenue', 'revenue'), ('op', 'operating_profit'), ('ocf', 'ocf'), ('equity', 'equity'), ('cash', 'cash'))
DEBT = ('debt', 'balance_debt')


def _number(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):return False
    try:return isfinite(value)
    except OverflowError:return False            # an int too large for a float is not a usable amount


def map_record(record, *, company, rcept_dt, include_debt=False):
    """-> (pit receipt dict for `pit_annual.project`, provenance dict). Raises ValueError for anything outside the pilot scope."""
    if not (isinstance(company, str) and re.fullmatch(r'[0-9A-Z]{6}', company)):raise ValueError('종목코드 형식 오류')
    if record.get('basis') not in ('CFS', 'OFS'):raise ValueError('회계 기준 미확인')
    contract = record.get('period_contract')
    if not isinstance(contract, dict) or contract.get('report_kind') != 'annual' or record.get('quarter') != 4:raise ValueError('연간 보고서가 아닙니다')
    if record.get('currency') != 'KRW' or record.get('unit') != 'KRW':raise ValueError('원화가 아닙니다')
    year, start, end = record.get('year'), record.get('period_start'), record.get('period_end')
    if not isinstance(year, int) or start != f'{year}-01-01' or end != f'{year}-12-31':raise ValueError('1월 1일~12월 31일 전체 사업연도가 아닙니다')
    receipt = record.get('receipt')
    if not (isinstance(receipt, str) and re.fullmatch(r'\d{14}', receipt)):raise ValueError('접수번호 형식 오류')
    try:expected = date(int(receipt[:4]), int(receipt[4:6]), int(receipt[6:8])).isoformat()
    except ValueError as exc:raise ValueError('접수번호 날짜 오류') from exc
    if expected != rcept_dt:raise ValueError('접수일이 접수번호와 다릅니다')
    values = record.get('values')
    if not isinstance(values, dict):raise ValueError('값이 없습니다')
    source = contract.get('source')
    mapped, keys = {}, {}
    for target, key in FIELDS + ((DEBT,) if include_debt else ()):
        if key not in values or values[key] is None:continue
        if not _number(values[key]):raise ValueError(f'숫자가 아닌 값: {key}')
        mapped[target] = float(values[key]);keys[target] = key
    if not mapped:raise ValueError('매핑 가능한 값이 없습니다')
    return (dict(company=company, period_end=end, basis=record['basis'], report_kind='annual', rcept_no=receipt, rcept_dt=rcept_dt, values=mapped),
        dict(rcept_no=receipt, mapping_version=MAPPING_VERSION, parser_version=record.get('parser_version'), source_keys=keys,
            source_url=record.get('url'), contract_sha256=source.get('sha256') if isinstance(source, dict) else None, include_debt=bool(include_debt)))
