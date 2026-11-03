"""Acquisition flow for one receipt: choose the statements document, fetch it, keep the bytes, parse, map (design: docs/review/design_PIT_collection_adapter_2026-11-03.md).

Every network and parsing step is INJECTED (`discover`, `fetch`, `parse`), so this module is tested with fakes and performs no
request itself. How a real receipt tree is discovered and how the fiscal contract is built from a real viewer are NOT
implemented here: they need one real specimen and are part of the gated first live step. A receipt with zero or several
qualifying documents is blocked before any request. Downloaded bytes are always stored before parsing, failures are recorded,
and changed bytes are reported instead of reused.
"""
from .pit_values import map_record


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    """Shared request budget: a hard request cap and a minimum interval between requests."""
    def __init__(self, *, max_requests, min_interval, clock, sleep):
        self.max_requests, self.min_interval, self.clock, self.sleep = max_requests, min_interval, clock, sleep
        self.count = 0;self.last = None

    def spend(self):
        if self.count >= self.max_requests:raise BudgetExceeded(f'요청 한도 {self.max_requests}회 도달')
        if self.last is not None:
            wait = self.min_interval - (self.clock() - self.last)
            if wait > 0:self.sleep(wait)
        self.last = self.clock();self.count += 1


def acquire_receipt(*, entry, company, basis, discover, fetch, parse, store, now, budget=None, include_debt=False):
    """-> dict(status, rcept_no, reason?, receipt?, provenance?, artifact?). status: ok | blocked | failed | changed_bytes."""
    number = entry['rcept_no']
    nodes = [n for n in discover(number) if n.get('basis') == basis]
    if not nodes:return dict(status='blocked', rcept_no=number, reason='no_candidate')
    if len(nodes) > 1:return dict(status='blocked', rcept_no=number, reason='multiple_candidates')
    chosen = nodes[0]
    try:
        if budget:budget.spend()
        data = fetch(chosen['url'])
    except BudgetExceeded:
        raise
    except Exception as exc:
        failure = store.record_failure(number, chosen['document_id'], reason=str(exc) or type(exc).__name__, observed_at=now)
        return dict(status='failed', rcept_no=number, reason='fetch_failed', artifact=failure)
    artifact = store.put(number, chosen['document_id'], data, observed_at=now, source_url=chosen['url'])
    if artifact['status'] == 'changed':
        return dict(status='changed_bytes', rcept_no=number, reason='bytes_changed_since_last_observation', artifact=artifact)
    try:
        record = parse(data, chosen, entry)
    except Exception:
        return dict(status='failed', rcept_no=number, reason='parse_failed', artifact=artifact)
    try:
        receipt, provenance = map_record(record, company=company, rcept_dt=entry['rcept_dt'], include_debt=include_debt)
    except ValueError:
        return dict(status='failed', rcept_no=number, reason='mapping_failed', artifact=artifact)
    return dict(status='ok', rcept_no=number, receipt=receipt, provenance=provenance, artifact=artifact)
