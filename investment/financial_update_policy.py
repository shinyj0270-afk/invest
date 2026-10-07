"""Compare validated statements with the last applied financial bundle."""
from decimal import Decimal


def decide_update(previous, observed):
    """New quarters apply immediately; revisions use cumulative absolute change."""
    def reports(bundle):
        return {(code, r['basis'], r['year'], r['quarter']): r
                for code, company in bundle.get('companies', {}).items()
                for r in company.get('reports', [])}

    before=reports(previous or {}); after=reports(observed)
    if not after:
        return dict(action='review', reason='no_reports', changes=[])
    # Same old identity can hide a currency/fiscal-calendar migration. Never
    # interpret that migration as a 7% provider correction or parser repair.
    contract_fields=('unit','currency','period_start','period_end','fiscal_year','fiscal_quarter','year_end_month','calendar_segment')
    changed_contract=[]
    for key in before.keys() & after.keys():
        a=before[key];b=after[key]
        if any(a.get(k, 'KRW' if k in ('unit','currency') else None)!=b.get(k,'KRW' if k in ('unit','currency') else None) for k in contract_fields):
            changed_contract.append(dict(code=key[0],basis=key[1],year=key[2],quarter=key[3],account='financial_contract',material=False))
    if changed_contract:return dict(action='review',reason='financial_contract_changed',changes=changed_contract)
    if not before or any(key not in before for key in after):
        return dict(action='update', reason='new_reporting_period', changes=[])
    changes=[]; missing=False
    for key, report in after.items():
        original=before[key]['values']; current=report['values']
        if set(original)!=set(current):missing=True
        for account in original.keys() & current.keys():
            old=Decimal(str(original[account])); new=Decimal(str(current[account]))
            if old==new:continue
            # A zero baseline cannot produce a meaningful percentage.
            material=old==0 or old*new<0 or abs(new-old)>=abs(old)*Decimal('0.07')
            changes.append(dict(code=key[0],basis=key[1],year=key[2],quarter=key[3],
                                account=account,material=material))
    if any(change['material'] for change in changes):
        return dict(action='update',reason='material_revision',changes=changes)
    if missing:
        return dict(action='review',reason='account_coverage_changed',changes=changes)
    return dict(action='defer' if changes else 'unchanged',
                reason='below_threshold' if changes else 'unchanged',changes=changes)
