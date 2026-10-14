"""Reviewed official-document extracts, separate from DART regular-report caches.

An extract is an explicit, reviewed transcription, not a PDF recognition result.
Original bytes are checked on import; reads never fetch or rewrite originals.
"""
import copy
import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from .financial_update_policy import decide_update
from .native_financial import financial_completeness

SCHEMA = 'official-document-statements-1'
REQUIRED = {'assets', 'liabilities', 'equity', 'revenue', 'operating_profit',
            'net_income', 'ocf', 'icf', 'financing_cf', 'cash_start', 'cash_end', 'fx_effect'}
FIELDS = REQUIRED | {'parent_net', 'nci_net', 'parent_equity', 'nci', 'cash',
                     'current_assets', 'current_liabilities', 'balance_debt', 'eps'}
KINDS = {'prospectus': '투자설명서', 'registration': '증권신고서',
         'audit': '감사보고서', 'review': '검토보고서'}


def valid_day(value):
    return isinstance(value, str) and date.fromisoformat(value).isoformat() == value


def validate_packet(packet, row):
    """Validate the reviewed import contract and independent balance equations."""
    try:
        if packet['schema'] != SCHEMA:
            raise ValueError('공식 원문 스키마 불일치')
        company = packet['company']
        if any(company[k] != row[k] for k in ('code', 'name', 'market')):
            raise ValueError('공식 원문 기업 식별 불일치')
        if not re.fullmatch(r'[0-9A-Z]{6}', company['code']) or not re.fullmatch(r'\d{8}', company['corp_code']):
            raise ValueError('기업 코드 미확인')
        document = packet['document']
        link = urlsplit(document['url'])
        if (link.scheme != 'https' or not link.hostname or link.username or link.password
                or document['kind'] not in KINDS
                or document['publisher_role'] not in ('issuer', 'underwriter', 'exchange')
                or not re.fullmatch(r'[a-f0-9]{64}', document['sha256'])
                or document['legal_name'] != company['name']
                or document['corp_code'] != company['corp_code']
                or type(document['pages']) is not int or document['pages'] < 1
                or not valid_day(document['available_at'])):
            raise ValueError('공식 원문 출처·기업 근거 미확인')
        review = packet['review']
        if review['status'] != 'user_confirmed' or not review['reviewer'].strip() or not valid_day(review['confirmed_on']):
            raise ValueError('원문 검증 완료 기록 필요')
        if not isinstance(document['caveats'], list) or any(not isinstance(x, str) for x in document['caveats']):
            raise ValueError('원문 제한사항 오류')
        reports = packet['reports']
        if not isinstance(reports, list) or not reports:
            raise ValueError('반영할 재무제표 없음')
        keys = set()
        for report in reports:
            start, end = report['period_start'], report['period_end']
            if not valid_day(start) or not valid_day(end) or start > end or end > document['available_at']:
                raise ValueError('재무 기간·공개일 불일치')
            y = int(end[:4]); q = report['quarter']
            if (type(q) is not int or q not in (2, 4) or report['year'] != y
                    or start != f'{y}-01-01'
                    or end != f'{y}-' + ('06-30' if q == 2 else '12-31')
                    or report['cadence'] != ('cumulative' if q == 2 else 'annual')
                    or report['basis'] not in ('CFS', 'OFS')
                    or report['currency'] != 'KRW' or report['actual'] is not True):
                raise ValueError('연간·반기 실제치 계약 불일치')
            key = (report['basis'], y, q)
            if key in keys:
                raise ValueError('같은 기간·기준 재무 중복')
            keys.add(key)
            cells = report['cells']
            if not isinstance(cells, dict) or not REQUIRED <= cells.keys() or not cells.keys() <= FIELDS:
                raise ValueError('필수 재무·현금 계정 미확보')
            values = {}
            for field, cell in cells.items():
                if (type(cell['page']) is not int or not 1 <= cell['page'] <= document['pages']
                        or any(type(cell[k]) is not int or cell[k] < 0 for k in ('table', 'row', 'column'))
                        or cell['column'] == 0 or not cell['label'].strip()
                        or not cell['column_label'].strip()
                        or cell['period_start'] != start or cell['period_end'] != end
                        or cell['basis'] != report['basis']
                        or type(cell['multiplier']) is not int or cell['multiplier'] not in (1, 1000, 1000000)):
                    raise ValueError('원문 열·기간·단위 근거 미확인')
                text = cell['text'].strip().replace(',', '').replace('−', '-')
                # Empty, dashes and guesses are never substituted with zero.
                if not re.fullmatch(r'-?\d+(?:\.\d+)?|\(\d+(?:\.\d+)?\)', text):
                    raise ValueError('원문 숫자 미확보')
                amount = -Decimal(text[1:-1]) if text.startswith('(') else Decimal(text)
                amount *= cell['multiplier']
                values[field] = int(amount) if amount == amount.to_integral_value() else float(amount)
            tolerance = max(cell['multiplier'] for cell in cells.values())
            if abs(values['assets'] - values['liabilities'] - values['equity']) > tolerance:
                raise ValueError('대차 검산 불일치')
            if abs(values['cash_start'] + values['ocf'] + values['icf'] + values['financing_cf']
                   + values['fx_effect'] - values['cash_end']) > tolerance:
                raise ValueError('현금흐름 검산 불일치')
            for a, b, total in (('parent_net', 'nci_net', 'net_income'), ('parent_equity', 'nci', 'equity')):
                if all(k in values for k in (a, b, total)) and abs(values[a] + values[b] - values[total]) >= 100000000:
                    raise ValueError('귀속 검산 불일치')
            if 'values' in report and report['values'] != values:
                raise ValueError('저장 값과 원문 셀 불일치')
            report['values'] = values
        return packet
    except (KeyError, TypeError, AttributeError, InvalidOperation, OverflowError) as error:
        raise ValueError('공식 원문 반영 계약 미확인') from error


def import_packet(root, packet_path, row):
    """Explicit local import; lock, backup, atomic replace and revision policy."""
    from .company_financials import folder, acquire_lock
    from .market_refresh import write_json
    from .local_config import load_local, require_profile
    require_profile(load_local(root))
    packet_path = Path(packet_path).resolve()
    packet = validate_packet(json.loads(packet_path.read_text(encoding='utf-8')), row)
    source = packet_path.parent / packet['document']['file']
    if source.resolve().parent != packet_path.parent or not source.is_file():
        raise ValueError('원문은 입력 파일과 같은 폴더에 보존해야 합니다')
    if hashlib.sha256(source.read_bytes()).hexdigest() != packet['document']['sha256']:
        raise ValueError('공식 원문 해시 불일치')
    dest = folder(root); dest.mkdir(parents=True, exist_ok=True)
    with acquire_lock(dest / 'collection.lock'):
        target = dest / 'official-documents' / (row['code'] + '.json')
        target.parent.mkdir(parents=True, exist_ok=True)
        previous = json.loads(target.read_text(encoding='utf-8')) if target.is_file() else None
        if previous:
            validate_packet(copy.deepcopy(previous), row)
        # Keep all already applied periods; updates remain subject to the same 7% policy.
        prior = {(r['basis'], r['year'], r['quarter']): r for r in (previous or {}).get('reports', [])}
        new = {(r['basis'], r['year'], r['quarter']): r for r in packet['reports']}
        # A single-source packet cannot silently attribute older data to a new PDF.
        if previous and previous['document']['sha256'] != packet['document']['sha256'] and not prior.keys() <= new.keys():
            raise ValueError('원문 변경 시 이전 기간을 포함한 검증본 필요')
        packet['reports'] = list((prior | new).values())
        def bundle(value):
            return {'companies': {row['code']: {'reports': (value or {}).get('reports', [])}}}
        decision = decide_update(bundle(previous), bundle(packet))
        if previous and (previous['document']['kind'], previous['document']['legal_name'], previous['document']['corp_code']) != (
                packet['document']['kind'], packet['document']['legal_name'], packet['document']['corp_code']):
            decision = dict(action='review', reason='document_contract_changed', changes=[])
        if previous and packet['document']['available_at'] < previous['document']['available_at']:
            decision = dict(action='review', reason='older_document', changes=[])
        packet['imported_at'] = datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='microseconds')
        packet['update_decision'] = decision
        write_json(target.with_suffix('.observed.json'), packet)
        if decision['action'] in ('update', 'unchanged'):
            if previous and decision['action'] == 'update':
                backup = dest / 'official-documents' / 'backups' / (row['code'] + '-' + packet['imported_at'].replace(':', '').replace('+', '_') + '.json')
                backup.parent.mkdir(parents=True, exist_ok=True)
                write_json(backup, previous)
            write_json(target, packet)
        return dict(code=row['code'], reports=len(packet['reports']), **decision)


def load_official(path, row, cutoff):
    """Read-only projection; no invented quarterly flows or DART attribution."""
    try:
        packet = validate_packet(json.loads(Path(path).read_text(encoding='utf-8')), row)
        if not valid_day(cutoff):
            return None
        document = packet['document']
        if document['available_at'] > cutoff:
            return None
        periods = []
        for report in packet['reports']:
            if report['period_end'] > cutoff:
                continue
            periods.append(dict(report['values'], basis=report['basis'], cadence=report['cadence'],
                period_start=report['period_start'], period_end=report['period_end'],
                available_at=document['available_at'], currency='KRW',
                source='공식 ' + KINDS[document['kind']] + ' · 검증된 실제 재무',
                source_url=document['url'], sha256=document['sha256'],
                document_kind=document['kind'], cell_notes={k: f"원문 {c['page']}쪽 · {c['column_label']} · {c['label']}" for k, c in report['cells'].items()}))
        if not periods:
            return None
        notes = ['공식 원문 검증 완료는 사용자 확인 기록입니다. 정기보고서로 재분류하지 않습니다.',
                 '연간·반기 누적 실적입니다. 미확보 단독분기·TTM·ROE는 추정하지 않습니다.'] + document['caveats']
        return dict(code=row['code'], name=row['name'], market=row['market'], periods=periods,
                    notes=notes, financial_completeness=financial_completeness(periods, cutoff),
                    official_document=dict(kind=document['kind'], url=document['url'], sha256=document['sha256'],
                        available_at=document['available_at'], review=packet['review'], imported_at=packet.get('imported_at')))
    except (OSError, ValueError, KeyError, TypeError):
        return None
