"""Read cached public observations; no DB/network/source writes."""
import sys,json,hashlib,time,argparse
from pathlib import Path
from datetime import date
from collections import Counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root',type=Path,required=True)
parser.add_argument('--output',type=Path)
args=parser.parse_args();MAIN=args.root.resolve()
from investment.local_config import load_local
from investment.market_discovery import read_market_cache,build_discovery
from investment.market_insights import enrich_market
from investment.company_financials import folder,load_cached
from investment.financial_table import build_table
from investment.financial_metrics import common_metrics,apply_common
from investment.industry_phase import build as phase
from investment.leader_strategy import build as leader
cfg=load_local(MAIN);market_folder=cfg['data_dir']/cfg['profile']/'market-expansion'
paths=list(folder(MAIN).rglob('*.json'))+[market_folder/name for name in ('universe.json','histories.json','latest-quotes.json')]
def stamps():return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.exists()}
before=stamps();started=time.perf_counter();scope={'meta':{'data_mode':'user_input','price_date':date.today().isoformat()},'companies':[]}
cache=read_market_cache(MAIN,scope);assert cache
print('cache read',flush=True)
d=build_discovery(scope,{'rows':{}},cache,include_series=False);assert d
rows=[r for r in d['snapshot']['companies'] if r['discovery_allowed']];scope['companies']=rows
finances=load_cached(MAIN,scope,rows,as_of=scope['meta']['price_date'],cache=cache)
for r in rows:
    table=build_table(r,scope,finances.get(r['code']),max_columns=48)
    common=common_metrics(r,table,d['research']['rows'][r['code']]['technical'])
    apply_common(r,d['research']['rows'][r['code']],common)
enrich_market(d,cache)
a=phase(d,cache);b=leader(d,cache)
phase_markets={}
for m in ('KOSPI','KOSDAQ'):
    rs=[r for r in rows if r['market']==m]
    phase_markets[m]=dict(population=len(rs),phases=dict(Counter(a['rows'][r['code']]['phase'] for r in rs)),recent_weak=sum(a['rows'][r['code']]['recent_weak'] for r in rs),industries=len([g for g in a['sectors'] if g['market']==m]),rankable_industries=sum(g['rankable'] for g in a['sectors'] if g['market']==m))
report=dict(as_of=d['snapshot']['meta']['price_date'],scope='stored public caches; manual supplement and DB not loaded',phase=phase_markets,hypothesis_c=a['hypothesis_c'],leader=b['markets'],leader_reasons=dict(Counter(r['reason'] or 'coordinates_and_value_ready' for r in b['rows'])),turnover_methods=dict(Counter(r.get('turnover_method','missing') for r in b['rows'])),source_files_unchanged=before==stamps(),db_access=False,network_collection=False,elapsed_seconds=round(time.perf_counter()-started,2))
report['source_sha256']=hashlib.sha256(json.dumps(sorted(before.values())).encode()).hexdigest()
report['source_files']=len(before)
if args.output:
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True),flush=True)
assert report['source_files_unchanged']
