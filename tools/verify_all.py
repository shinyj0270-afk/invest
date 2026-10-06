"""Legacy in-place checks; prefer validate_share_candidates.py --ui for isolated checks."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime,timezone
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--in-place', action='store_true', help='Explicitly permit writes to this checkout and its fixture data')
args = parser.parse_args()
if not args.in_place:
    parser.error('Use tools/validate_share_candidates.py --ui; legacy worktree writes require --in-place')
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from investment.local_config import load_local,require_profile
profile=require_profile(load_local(ROOT))
out=ROOT/'validation/current'; out.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,PYTHONIOENCODING='utf-8')
edge=Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
if edge.exists(): env.setdefault('CHROMIUM_PATH',str(edge))
commands=[
 [sys.executable,'build.py'],
 ['node','tests/test_engine.js'],['node','tests/test_portfolio.js'],
 [sys.executable,'-m','unittest','tests.test_dual_pc','tests.test_research_app','tests.test_financial_reconciliation','tests.test_user_policy','tests.test_company_finish','tests.test_review_tolerance','tests.test_infomax_import','tests.test_marketcap_history','tests.test_streamlit_app','tests.test_infomax_daily','tests.test_infomax_financial_snapshot','tests.test_refresh','tests.test_auto_refresh','tests.test_holdings_bridge','tests.test_portfolio_data','tests.test_market_events','tests.test_daily_dashboard','tests.test_visuals','tests.test_workspace_export','tests.test_live_dashboard','tests.test_infomax_history','tests.test_trend_history','tests.test_returns_history'],
 [sys.executable,'tests/test_ui.py'],[sys.executable,'tests/test_portfolio_ui.py'],
 [sys.executable,'batch.py','init-fixture','--profile',profile],
 [sys.executable,'batch.py','daily','--profile',profile],[sys.executable,'batch.py','weekly','--profile',profile],
 [sys.executable,'batch.py','weekly','--profile',profile],
 [sys.executable,'tests/verify_report_browser.py'],
]
if (ROOT/'private_data/infomax/info.xlsx').exists(): commands.append([sys.executable,'tools/company_finish.py'])
results=[]
for i,command in enumerate(commands):
    run=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
    (out/f'{i:02}.txt').write_text(run.stdout+run.stderr,encoding='utf-8')
    results.append(dict(command=command,exit_code=run.returncode,log=f'{i:02}.txt'))
    print(('PASS ' if run.returncode==0 else 'FAIL ')+str(command[1:]))
(out/'results.json').write_text(json.dumps(dict(executed_at=datetime.now(timezone.utc).isoformat(),results=results),ensure_ascii=False,indent=2),encoding='utf-8')
sys.exit(any(r['exit_code'] for r in results))
