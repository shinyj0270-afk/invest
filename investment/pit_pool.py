"""Local PIT pool: stored annual documents -> point-in-time rows -> factor scores. No network, no key.

The documents come from the hash-addressed store under `<root>/artifacts` (`manifest.jsonl` + `blobs/<sha256>`); the receipt lists and the trading calendar are plain inputs.
Original annual reports only (`correction == 'none'`, December period); a document that cannot be read is reported in `problems`, never silently dropped.
"""
import json
import io
from pathlib import Path
from .pit_annual import project
from .pit_factors import newer_periods_from_receipts, pit_scores
from .pit_values import map_record
from .pit_verify import verify
from .pit_xml import parse_document_zip


def load_sha(root):
    """{rcept_no: sha256} of the stored OpenDART document zips."""
    lines = (Path(root) / 'artifacts' / 'manifest.jsonl').read_text(encoding='utf-8').splitlines()
    entries = [json.loads(line) for line in lines if line.strip()]
    return {e['rcept_no']: e['sha256'] for e in entries if e.get('document_id') == 'document-zip' and e.get('sha256')}


def load_sessions(root, files):
    """Sorted ISO session dates of the given calendar files (each a JSON list of bars with `localDate` = YYYYMMDD)."""
    days = set()
    for name in files:
        for bar in json.loads((Path(root) / 'calendar' / name).read_text(encoding='utf-8')):
            day = bar['localDate']
            days.add(f'{day[:4]}-{day[4:6]}-{day[6:]}')
    return sorted(days)


def company_rows(root, code, receipts, sha, sessions):
    """Parse every stored original annual report of one company and project it: dict(rows, blocked, problems, verify_ok, parsed)."""
    mapped, problems = [], []
    for item in sorted(receipts, key=lambda r: r['rcept_dt']):
        period = item.get('title_period') or ''
        if item['correction'] != 'none' or not period.endswith('-12') or item['rcept_no'] not in sha:continue
        year = int(period[:4])
        path = Path(root) / 'artifacts' / 'blobs' / sha[item['rcept_no']]
        try:
            record = parse_document_zip(path.read_bytes(), receipt=item['rcept_no'], year=year, url='opendart:document.xml', company=code)
            receipt, _ = map_record(record, company=code, rcept_dt=item['rcept_dt'])
        except (ValueError, OSError) as exc:      # a missing blob (OSError) or any unreadable document
            problems.append(dict(year=year, rcept_no=item['rcept_no'], problem=str(exc)))
            continue
        mapped.append(receipt)
    projected = project(mapped, sessions)
    return dict(rows=projected['rows'], blocked=projected['blocked'], problems=problems, verify_ok=verify(mapped, sessions)['ok'], parsed=len(mapped))


def pool_scores(root, companies, sessions, as_of, *, tolerated=frozenset(), sha=None, minimum=5):
    """Score a pool: `companies` = {code: (name, receipts)}. Returns (scores, details): scores = `pit_scores` results with `name`, details = company_rows output per code."""
    if not isinstance(companies, dict) or not companies:raise ValueError('companies must be a non-empty dict')
    sha = load_sha(root) if sha is None else sha
    details = {code: company_rows(root, code, receipts, sha, sessions) for code, (_, receipts) in companies.items()}
    newer = newer_periods_from_receipts({code: receipts for code, (_, receipts) in companies.items()}, as_of)
    scores = pit_scores({code: d['rows'] for code, d in details.items()}, as_of, tolerated=tolerated, newer_periods=newer, minimum=minimum)
    return [dict(score, name=companies[score['code']][0]) for score in scores], details
