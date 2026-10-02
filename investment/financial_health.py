"""Compact collection provenance. Never changes validated financial values."""
import json
from pathlib import Path


def read_record(path):
    try:
        if path.stat().st_size > 5_000_000:return {}
        value=json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}


def collection_health(folder, code, bundle=None):
    path=Path(folder)/(code+'.json')
    saved=read_record(path);observed=read_record(path.with_suffix('.observed.json'))
    incomplete=read_record(path.with_suffix('.incomplete.json'))
    attempt=read_record(path.with_suffix('.status.json'))
    reports=observed.get('companies',{}).get(code,{}).get('reports',[])
    decision=observed.get('update_decision',{})
    available=bool((bundle or {}).get('periods'))
    errors=len(incomplete.get('errors',[]))
    last_check=max(filter(None,[attempt.get('checked_at',''),observed.get('retrieved_on',''),incomplete.get('retrieved_on','')]),default=None)
    status=attempt.get('status') if attempt.get('checked_at','')[:10]>=str(observed.get('retrieved_on','')) else None
    status=status or ('partial' if errors else 'ready' if available else 'missing')
    return dict(status=status,last_checked=last_check,last_success=saved.get('retrieved_on'),failed_periods=errors,
        decision=decision.get('reason'),decision_on=observed.get('retrieved_on'),
        material_changes=sum(c.get('material') is True for c in decision.get('changes',[])),
        source_urls=sorted({r['url'] for r in reports if isinstance(r.get('url'),str) and r['url'].startswith('https://dart.fss.or.kr/')}),
        retry='다음 일간 점검에 재시도' if status in ('failed','partial','missing') else '일간 공시 점검 · 새 분기 또는 7% 이상 정정 반영')
