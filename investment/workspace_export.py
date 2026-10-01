"""Offline HTML viewer using the existing market and portfolio engines."""
import json
from pathlib import Path
from .core import validate_snapshot
from .holdings_bridge import holdings_input, holdings_catalog
from .valuation import enrich_valuation
from .workspace_research import build_research
from .naver_reference import sanitize_references
from .market_discovery import build_discovery
from .financial_table import build_table
from .company_detail import build_details

ROOT = Path(__file__).resolve().parents[1]


def script_json(value):
    text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    for char, replacement in [('<', '\\u003c'), ('>', '\\u003e'), ('&', '\\u0026'),
                              ('\u2028', '\\u2028'), ('\u2029', '\\u2029')]:
        text = text.replace(char, replacement)
    return text


def export_workspace(snapshot, *, live=None, events=None, references=None, market_cache=None, financials=None):
    """Embed only the supplied snapshot; never read local credentials or holdings."""
    validate_snapshot(snapshot)
    analysis = enrich_valuation(snapshot)
    research = build_research(analysis, events=events)
    discovery = build_discovery(analysis, research, market_cache)
    financial_tables = {r['code']: build_table(r, analysis, (financials or {}).get(r['code']),max_columns=48) for r in analysis['companies']}
    company_details = build_details(analysis, financial_tables, market_cache)
    # Every analysis view uses the same date-checked metrics; keep original payload intact.
    for row in analysis['companies']:
        facts = research['rows'].get(row['code'])
        if facts:
            row['metrics'].update(facts['fundamental']['metrics'])
    src = ROOT / 'src'
    legacy = (src / 'shell.html').read_text(encoding='utf-8')
    for marker, name in [('/*STYLE*/', 'style.css'), ('/*ENGINE*/', 'engine.js'),
                         ('/*UI*/', 'ui.js'), ('/*PORTFOLIO_ENGINE*/', 'portfolio_engine.js'),
                         ('/*PORTFOLIO_UI*/', 'portfolio_ui.js'), ('/*HOLDINGS_SYNC_ENGINE*/','holdings_sync.js'), ('/*HOLDINGS_SYNC_UI*/','holdings_sync_ui.js')]:
        legacy = legacy.replace(marker, (src / name).read_text(encoding='utf-8'))
    values = dict(INVESTMENT_INITIAL_SNAPSHOT=analysis)
    if live and live.get('holdings_sync'):
        values['INVESTMENT_HOLDINGS_SYNC'] = dict(enabled=True,endpoint='/holdings',token=live['token'])
    if snapshot['meta']['data_mode'] == 'user_input':
        values['INVESTMENT_HOLDINGS_INPUT'] = holdings_input(snapshot)
        values['INVESTMENT_HOLDINGS_CATALOG'] = holdings_catalog(snapshot, market_cache)
    if live and live.get('holdings_market'):
        values['INVESTMENT_HOLDINGS_MARKET'] = dict(enabled=True,endpoint='/holding-market',token=live['token'])
    legacy = legacy.replace('<script>', '<script>Object.assign(window,' + script_json(values) + ');</script><script>', 1)
    # The parent owns navigation; retain internal tab buttons for existing detail flows.
    legacy = legacy.replace('</head>', '<style>header{display:none}main{max-width:none;padding:0}body{background:transparent}.notice,#scopeBar,.foot,#clearData{display:none}</style></head>')
    html = (src / 'workspace.html').read_text(encoding='utf-8')
    # Insert payload last so data containing template marker text stays literal.
    for marker, name in [('/*WORKSPACE_CSS*/', 'workspace.css'), ('/*WORKSPACE_JS*/', 'workspace.js'),
                         ('/*COMPANY_DETAIL_CSS*/', 'company_detail.css'), ('/*COMPANY_DETAIL_ENGINE*/', 'company_detail_engine.js'), ('/*COMPANY_DETAIL_UI*/', 'company_detail_ui.js'),
                         ('/*DISCOVERY_ENGINE*/', 'discovery_engine.js'), ('/*EBITDA_INPUTS*/', 'ebitda_inputs.js'), ('/*EBITDA_EDITOR*/', 'ebitda_editor.js'), ('/*FINANCIAL_TABLE_UI*/', 'financial_table_ui.js'), ('/*ADVANCED_VISUALS*/', 'advanced_visuals.js'), ('/*RESEARCH_UI*/', 'research_ui.js'),
                         ('/*ENGINE*/', 'engine.js'), ('/*PORTFOLIO_ENGINE*/', 'portfolio_engine.js')]:
        html = html.replace(marker, (src / name).read_text(encoding='utf-8'))
    html = html.replace('/*LIVE_CONFIG*/', script_json(live))
    return html.replace('/*PAYLOAD*/', script_json(dict(snapshot=snapshot, analysis_snapshot=analysis,
        research=research, discovery=discovery, financial_tables=financial_tables, company_details=company_details,
        references=sanitize_references(references or {}, snapshot), detail_html=legacy)))
