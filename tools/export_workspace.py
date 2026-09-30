"""Export the last saved real snapshot; no API calls or personal holdings."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from investment.local_config import load_local
from investment.store import Store
from investment.workspace_export import export_workspace
from investment.naver_reference import load_cached_references
from investment.workspace_events import load_cached_events
from investment.market_discovery import load_market_cache

def main():
    config=load_local(ROOT)
    snapshot=Store(config['data_dir'],config['profile'],'user_input').latest()
    if snapshot is None:
        raise SystemExit('실제 저장 스냅샷 없음 · 갱신 앱에서 자료를 확인하세요.')
    target=Path(config['data_dir'])/config['profile']/'exports'/('investment_dashboard_'+snapshot['meta']['price_date'].replace('-','')+'.html')
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(export_workspace(snapshot,events=load_cached_events(ROOT,snapshot),
        references=load_cached_references(ROOT,snapshot),
        market_cache=load_market_cache(ROOT,snapshot)),encoding='utf-8')
    print(target.resolve())

if __name__=='__main__':
    main()
