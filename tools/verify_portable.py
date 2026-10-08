"""Offline fixture verification for the curated two-PC source set."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
env = dict(os.environ, PYTHONIOENCODING='utf-8')
commands = [
    [sys.executable, '-m', 'unittest', 'tests.test_portability'],
    [sys.executable, '-m', 'unittest', 'tests.test_financial_update_policy', 'tests.test_company_financials', 'tests.test_financial_account_recovery', 'tests.test_trend_diagnostics', 'tests.test_dashboard_upgrade', 'tests.test_portfolio_risk', 'tests.test_trend_following'],
    [sys.executable, 'build.py'],
    [sys.executable, '-m', 'unittest', 'tests.test_research_app', 'tests.test_streamlit_app', 'tests.test_infomax_daily', 'tests.test_infomax_financial_snapshot', 'tests.test_refresh', 'tests.test_auto_refresh','tests.test_holdings_bridge','tests.test_holding_market','tests.test_portfolio_data','tests.test_market_events','tests.test_daily_dashboard','tests.test_visuals','tests.test_workspace_export','tests.test_live_dashboard', 'tests.test_holdings_sync', 'tests.test_infomax_history', 'tests.test_trend_history', 'tests.test_returns_history', 'tests.test_valuation', 'tests.test_workspace_research', 'tests.test_workspace_events', 'tests.test_price_strength', 'tests.test_naver_reference', 'tests.test_naver_universe', 'tests.test_market_history', 'tests.test_market_refresh', 'tests.test_market_discovery', 'tests.test_financial_table', 'tests.test_company_detail', 'tests.test_dart_statements'],
    [sys.executable, 'batch.py', 'init-fixture'],
    [sys.executable, 'batch.py', 'daily'],
    [sys.executable, 'batch.py', 'weekly'],
]
if (ROOT/'tests/test_engine.js').exists():
    commands += [['node', 'tests/test_engine.js'], ['node', 'tests/test_portfolio.js'], ['node','tests/test_holdings_sync.js'], ['node', 'tests/test_discovery.js'], ['node', 'tests/test_advanced_visuals.js'], ['node', 'tests/test_ebitda_inputs.js'], ['node', 'tests/test_company_detail.js'], ['node', 'tests/test_company_valuation.js'], ['node', 'tests/test_trend_following.js'], ['node', 'tests/test_home_dashboard.js'], ['node', 'tests/test_verification_ui.js'], ['node', 'tests/test_thesis_ui.js'], ['node', 'tests/test_holdings_brief.js']]
commands += [[sys.executable, '-m', 'unittest', *['tests.test_dashboard_payload', 'tests.test_dashboard_stability', 'tests.test_fiscal_native_financial', 'tests.test_market_trend_changes', 'tests.test_risk_review', 'tests.test_upgrade_integration', 'tests.test_verification', 'tests.test_thesis_monitor']]]
commands += [['node', name] for name in ['tests/check_financial_review_ui.js', 'tests/test_company_fiscal.js', 'tests/test_dashboard_stability.js', 'tests/test_market_trend_changes.js']]
for command in commands:
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, encoding='utf-8', errors='replace',
                            capture_output=True, timeout=180)
    print(('PASS ' if result.returncode == 0 else 'FAIL ') + ' '.join(command[1:]), flush=True)
    if result.returncode:
        print((result.stdout + result.stderr)[-3000:], file=sys.stderr)
        sys.exit(result.returncode)
