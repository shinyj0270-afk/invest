"""Immutable, content-addressed store for retrieved receipt documents (design: docs/review/design_PIT_collection_adapter_2026-11-03.md).

Bytes live under `blobs/<sha256>` and are never overwritten; every observation appends one row to `manifest.jsonl` (append-only,
written under a cross-process lock). Changed bytes under the same receipt become a new version, failed downloads and hash
mismatches are kept as rows, and nothing here decides which version is historically valid. Local files only, no network.
"""
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from .trial_log import _exclusive

STATUSES = ('first', 'same', 'changed', 'hash_mismatch', 'failed')
FIELDS = ('seq', 'rcept_no', 'document_id', 'sha256', 'size', 'observed_at', 'source_url', 'status', 'expected_sha256', 'changed_from', 'reason')


def _check_ids(rcept_no, document_id, observed_at):
    if not (isinstance(rcept_no, str) and re.fullmatch(r'\d{14}', rcept_no)):raise ValueError('접수번호 형식 오류')
    if not (isinstance(document_id, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,80}', document_id)):raise ValueError('문서 식별자 형식 오류')
    try:datetime.fromisoformat(observed_at)
    except (TypeError, ValueError) as exc:raise ValueError('관측 시각 형식 오류') from exc


class ArtifactStore:
    def __init__(self, root):
        self.root = Path(root);self.manifest = self.root / 'manifest.jsonl';self.blobs = self.root / 'blobs'

    def entries(self):
        if not self.manifest.exists():return []
        rows = []
        for number, line in enumerate(self.manifest.read_text(encoding='utf-8').splitlines(), 1):
            if not line.strip():continue
            try:row = json.loads(line)
            except ValueError as exc:raise ValueError(f'보관소 목록 {number}번째 줄 손상') from exc
            if row.get('seq') != len(rows) + 1:raise ValueError(f'보관소 목록 순번 불일치(줄 {number})')
            rows.append(row)
        return rows

    def versions(self, rcept_no, document_id):
        return [e for e in self.entries() if e['rcept_no'] == rcept_no and e['document_id'] == document_id]

    def _append(self, row_fields):
        with _exclusive(self.manifest):
            rows = self.entries()
            if self.manifest.exists() and self.manifest.stat().st_size and not self.manifest.read_bytes().endswith(b'\n'):
                raise ValueError('보관소 목록 마지막 줄이 개행으로 끝나지 않음; 보존하고 검토')
            row = {k: None for k in FIELDS};row.update(row_fields, seq=len(rows) + 1)
            with self.manifest.open('a', encoding='utf-8', newline='\n') as f:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n')
            return row

    def _blob(self, digest, data):
        path = self.blobs / digest
        if path.exists():return
        self.blobs.mkdir(parents=True, exist_ok=True)
        temp = self.blobs / ('.' + digest + '.tmp')
        with temp.open('wb') as f:
            f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(temp, path)

    def put(self, rcept_no, document_id, data, *, observed_at, source_url, expected_sha256=None):
        _check_ids(rcept_no, document_id, observed_at)
        if not isinstance(data, (bytes, bytearray)) or not data:raise ValueError('원문 바이트가 비어 있습니다')
        digest = hashlib.sha256(bytes(data)).hexdigest()
        self._blob(digest, bytes(data))
        previous = self.versions(rcept_no, document_id);seen = [e for e in previous if e['sha256']]
        changed_from = None
        if expected_sha256 is not None and expected_sha256 != digest:status = 'hash_mismatch'
        elif not seen:status = 'first'
        elif seen[-1]['sha256'] == digest:status = 'same'
        else:status, changed_from = 'changed', seen[-1]['sha256']
        return self._append(dict(rcept_no=rcept_no, document_id=document_id, sha256=digest, size=len(data), observed_at=observed_at,
            source_url=source_url, status=status, expected_sha256=expected_sha256, changed_from=changed_from))

    def record_failure(self, rcept_no, document_id, *, reason, observed_at):
        _check_ids(rcept_no, document_id, observed_at)
        return self._append(dict(rcept_no=rcept_no, document_id=document_id, observed_at=observed_at, status='failed', reason=str(reason)[:200]))

    def read(self, entry):
        if not entry.get('sha256'):raise ValueError('이 항목에는 원문 바이트가 없습니다')
        data = (self.blobs / entry['sha256']).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry['sha256']:raise ValueError('원문 해시 불일치')
        return data

    def verify(self):
        problems = []
        for e in self.entries():
            if not e.get('sha256'):continue
            path = self.blobs / e['sha256']
            if not path.exists():problems.append(dict(seq=e['seq'], problem='blob_missing'))
            elif hashlib.sha256(path.read_bytes()).hexdigest() != e['sha256']:problems.append(dict(seq=e['seq'], problem='blob_hash_mismatch'))
        return problems
