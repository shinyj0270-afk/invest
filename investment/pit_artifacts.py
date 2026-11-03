"""Immutable, content-addressed store for retrieved receipt documents (design: docs/review/design_PIT_collection_adapter_2026-11-03.md).

Bytes live under `blobs/<sha256>` and are never overwritten; every observation appends one row to `manifest.jsonl` (append-only,
fsynced, written under ONE cross-process lock that also covers the history read and the status calculation). Changed bytes under
the same receipt become a new version, failed downloads and hash mismatches are kept as rows. An observation status is not a
historical-validity verdict: a `changed` or `hash_mismatch` row leaves the document UNRESOLVED until `resolve()` pins the accepted
hash, and repetition never clears it. An existing blob is hash-checked before it is trusted. Local files only, no network.
"""
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from .trial_log import _exclusive

STATUSES = ('first', 'same', 'changed', 'hash_mismatch', 'failed', 'resolved')
FIELDS = ('seq', 'rcept_no', 'document_id', 'sha256', 'size', 'observed_at', 'source_url', 'status', 'expected_sha256', 'changed_from', 'reason')
DIGEST = re.compile(r'[0-9a-f]{64}')


def _check_ids(rcept_no, document_id, observed_at):
    if not (isinstance(rcept_no, str) and re.fullmatch(r'\d{14}', rcept_no)):raise ValueError('접수번호 형식 오류')
    if not (isinstance(document_id, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,80}', document_id)):raise ValueError('문서 식별자 형식 오류')
    try:datetime.fromisoformat(observed_at)
    except (TypeError, ValueError) as exc:raise ValueError('관측 시각 형식 오류') from exc


def _digest_ok(value):
    return isinstance(value, str) and DIGEST.fullmatch(value) is not None


class ArtifactStore:
    def __init__(self, root):
        self.root = Path(root);self.manifest = self.root / 'manifest.jsonl';self.blobs = self.root / 'blobs'

    def _read_rows(self):
        if not self.manifest.exists():return []
        rows = []
        for number, line in enumerate(self.manifest.read_text(encoding='utf-8').splitlines(), 1):
            if not line.strip():continue
            try:row = json.loads(line)
            except ValueError as exc:raise ValueError(f'보관소 목록 {number}번째 줄 손상') from exc
            if row.get('seq') != len(rows) + 1:raise ValueError(f'보관소 목록 순번 불일치(줄 {number})')
            if row.get('sha256') is not None and not _digest_ok(row['sha256']):raise ValueError(f'보관소 목록 해시 형식 오류(줄 {number})')
            rows.append(row)
        return rows

    def entries(self):
        if not self.manifest.exists():return []
        with _exclusive(self.manifest):                      # a reader must not see another writer's half-written line
            return self._read_rows()

    def versions(self, rcept_no, document_id):
        return [e for e in self.entries() if e['rcept_no'] == rcept_no and e['document_id'] == document_id]

    @staticmethod
    def _state(rows):
        pinned, unresolved, latest = None, False, None
        for e in rows:
            if e['status'] == 'resolved':pinned, unresolved = e['sha256'], False
            elif e['status'] in ('changed', 'hash_mismatch'):unresolved = True
            elif e.get('sha256') and pinned and e['sha256'] != pinned:unresolved = True      # bytes other than the accepted ones were observed again
            if e['status'] != 'resolved' and e.get('sha256'):latest = e['sha256']
        if pinned and latest == pinned:unresolved = False           # the accepted bytes are what was observed last
        return dict(unresolved=unresolved, pinned_sha256=pinned)

    def state(self, rcept_no, document_id):
        """unresolved: a changed/mismatched version was seen after the last `resolve`; pinned_sha256: the hash a human accepted."""
        return self._state([e for e in self.entries() if e['rcept_no'] == rcept_no and e['document_id'] == document_id])

    def _append_locked(self, rows, fields):
        if self.manifest.exists() and self.manifest.stat().st_size and not self.manifest.read_bytes().endswith(b'\n'):
            raise ValueError('보관소 목록 마지막 줄이 개행으로 끝나지 않음; 보존하고 검토')
        row = {k: None for k in FIELDS};row.update(fields, seq=len(rows) + 1)
        with self.manifest.open('a', encoding='utf-8', newline='\n') as f:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n')
            f.flush();os.fsync(f.fileno())
        return row

    def _publish_blob(self, digest, data):
        path = self.blobs / digest
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('기존 원문 파일이 손상되어 있습니다; 보존하고 검토')   # never trust or overwrite a corrupt blob
            return
        self.blobs.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(dir=self.blobs, prefix='.', suffix='.tmp')           # unique name: identical content may race
        try:
            with os.fdopen(fd, 'wb') as f:
                f.write(data);f.flush();os.fsync(f.fileno())
            try:
                os.replace(temp, path)
            except OSError:
                # Windows refuses a replace onto a file another writer just published; that is fine if the published bytes are the right ones.
                if not (path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest):
                    raise
        finally:
            if os.path.exists(temp):os.unlink(temp)

    def put(self, rcept_no, document_id, data, *, observed_at, source_url, expected_sha256=None):
        _check_ids(rcept_no, document_id, observed_at)
        if not isinstance(data, (bytes, bytearray)) or not data:raise ValueError('원문 바이트가 비어 있습니다')
        if expected_sha256 is not None and not _digest_ok(expected_sha256):raise ValueError('기대 해시 형식 오류')
        digest = hashlib.sha256(bytes(data)).hexdigest()
        with _exclusive(self.manifest):
            self._publish_blob(digest, bytes(data))      # inside the lock: concurrent publication of one blob races badly on Windows
            rows = self._read_rows()
            seen = [e for e in rows if e['rcept_no'] == rcept_no and e['document_id'] == document_id and e['sha256'] and e['status'] != 'resolved']
            changed_from = None
            if expected_sha256 is not None and expected_sha256 != digest:status = 'hash_mismatch'
            elif not seen:status = 'first'
            elif seen[-1]['sha256'] == digest:status = 'same'
            else:status, changed_from = 'changed', seen[-1]['sha256']
            return self._append_locked(rows, dict(rcept_no=rcept_no, document_id=document_id, sha256=digest, size=len(data), observed_at=observed_at,
                source_url=source_url, status=status, expected_sha256=expected_sha256, changed_from=changed_from))

    def resolve(self, rcept_no, document_id, *, accepted_sha256, observed_at, reason):
        """A human decision: pin the accepted version. The hash must be one that was actually observed for this document."""
        _check_ids(rcept_no, document_id, observed_at)
        if not _digest_ok(accepted_sha256) or not isinstance(reason, str) or not reason.strip():raise ValueError('해결 기록 형식 오류')
        with _exclusive(self.manifest):
            rows = self._read_rows()
            if not any(e['rcept_no'] == rcept_no and e['document_id'] == document_id and e['sha256'] == accepted_sha256 and e['status'] != 'resolved' for e in rows):
                raise ValueError('관측된 적 없는 해시는 수용할 수 없습니다')
            return self._append_locked(rows, dict(rcept_no=rcept_no, document_id=document_id, sha256=accepted_sha256, observed_at=observed_at,
                status='resolved', reason=reason.strip()[:200]))

    def record_failure(self, rcept_no, document_id, *, reason, observed_at):
        _check_ids(rcept_no, document_id, observed_at)
        with _exclusive(self.manifest):
            rows = self._read_rows()
            return self._append_locked(rows, dict(rcept_no=rcept_no, document_id=document_id, observed_at=observed_at, status='failed', reason=str(reason)[:200]))

    def read(self, entry):
        digest = entry.get('sha256')
        if not digest:raise ValueError('이 항목에는 원문 바이트가 없습니다')
        if not _digest_ok(digest):raise ValueError('해시 형식 오류')
        data = (self.blobs / digest).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:raise ValueError('원문 해시 불일치')
        return data

    def verify(self):
        problems = []
        for e in self.entries():
            if not e.get('sha256'):continue
            path = self.blobs / e['sha256']
            if not path.exists():problems.append(dict(seq=e['seq'], problem='blob_missing'))
            elif hashlib.sha256(path.read_bytes()).hexdigest() != e['sha256']:problems.append(dict(seq=e['seq'], problem='blob_hash_mismatch'))
        return problems
