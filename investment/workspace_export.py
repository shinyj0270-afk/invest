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
from .market_history import benchmark_calendar
from .financial_metrics import common_metrics,apply_common
from .market_insights import enrich_market
from .trend_following import build_trend_following

ROOT = Path(__file__).resolve().parents[1]


def market_summary(snapshot, market_cache, target_date):
    """Same-date observed benchmark closes; never substitute intraday quotes."""
    result = []
    cached = (market_cache or {}).get('history', {}).get('benchmarks', {})
    try:
        calendar = benchmark_calendar(cached)
        valid_cache = calendar['sessions'][-1] == target_date
    except (ValueError, KeyError, TypeError, IndexError):
        valid_cache = False
    for market in ('KOSPI', 'KOSDAQ'):
        if valid_cache:
            record = cached[market]
            bars = record['prices']
            source = record.get('source')
        else:
            bars = [b for b in snapshot.get('benchmarks', {}).get(market, [])
                    if b.get('final') is True and b.get('date', '') <= target_date]
            source = snapshot['meta'].get('source')
        if len(bars) < 2 or bars[-1].get('date') != target_date:
            continue
        a, b = bars[-2:]
        if not all(isinstance(p.get('close'), (int, float)) and not isinstance(p['close'], bool)
                   and 0 < p['close'] < float('inf') for p in (a, b)):
            continue
        result.append(dict(market=market, date=b['date'], close=b['close'],
                           change_pct=(b['close']/a['close']-1)*100, source=source))
    return result


def script_json(value):
    text = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    for char, replacement in [('<', '\\u003c'), ('>', '\\u003e'), ('&', '\\u0026'),
                              ('\u2028', '\\u2028'), ('\u2029', '\\u2029')]:
        text = text.replace(char, replacement)
    return text


def export_workspace(snapshot, *, live=None, events=None, references=None, market_cache=None, financials=None):
    """Embed only the supplied snapshot; never read local credentials or holdings."""
    validate_snapshot(snapshot)
    analysis = enrich_valuation(snapshot)
    research = build_research(analysis, events=events)
    discovery = build_discovery(analysis, research, market_cache, include_series=not (live or {}).get('lazy_company_views'))
    if discovery and (live or {}).get('lazy_company_views'):
        for facts in discovery['research']['rows'].values():
            facts['technical']['series'] = []
            facts['technical']['series_pending'] = True
    financial_cutoff=(live or {}).get('financial_as_of') or (discovery or {}).get('snapshot',{}).get('meta',{}).get('price_date') or analysis['meta']['price_date']
    financial_scope=dict(analysis,meta=dict(analysis['meta'],price_date=financial_cutoff))
    financial_tables = {r['code']: build_table(r, financial_scope, (financials or {}).get(r['code']),max_columns=48) for r in analysis['companies']}
    company_details = build_details(analysis, financial_tables, market_cache)
    if discovery:
        for row in discovery['snapshot']['companies']:
            row['collection_health']=(financials or {}).get(row['code'],{}).get('collection_health',{})
            if row['code'] not in discovery['research']['rows']:continue
            table=financial_tables.get(row['code'])
            if table is None and (financials or {}).get(row['code']):
                table=build_table(row,financial_scope,financials[row['code']],max_columns=48)
            if table:
                common=common_metrics(row,table,discovery['research']['rows'][row['code']]['technical'])
                apply_common(row,discovery['research']['rows'][row['code']],common)
                if row['code'] in company_details:
                    company_details[row['code']]['common_financial']=row.get('common_financial')
                    if row.get('common_financial'):
                        checked=next((r for r in analysis['companies'] if r['code']==row['code']),None)
                        if checked:checked['metrics'].update(row['common_financial']['metrics']);research['rows'][row['code']]['fundamental']['metrics'].update(row['common_financial']['metrics'])
    if discovery:
        extra=[r for r in discovery['snapshot']['companies'] if r['code'] not in company_details and (financials or {}).get(r['code'])] if not (live or {}).get('lazy_company_views') else []
        if extra:
            scope=dict(meta={**analysis['meta'],'price_date':financial_cutoff},companies=extra)
            extra_tables={r['code']:build_table(r,scope,financials[r['code']],max_columns=48) for r in extra}
            financial_tables.update(extra_tables)
            company_details.update(build_details(scope,extra_tables,market_cache))
            for r in extra:company_details[r['code']]['common_financial']=r.get('common_financial')
    market_insights=enrich_market(discovery,market_cache)
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
                         ('/*DASHBOARD_JOURNEY*/', 'dashboard_journey.js'),
                         ('/*TREND_FOLLOWING_UI*/', 'trend_following_ui.js'), ('/*TREND_FOLLOWING_CSS*/', 'trend_following.css'),
                         ('/*COMPANY_DETAIL_CSS*/', 'company_detail.css'), ('/*COMPANY_DETAIL_ENGINE*/', 'company_detail_engine.js'), ('/*COMPANY_DETAIL_UI*/', 'company_detail_ui.js'),
                         ('/*DISCOVERY_ENGINE*/', 'discovery_engine.js'), ('/*EBITDA_INPUTS*/', 'ebitda_inputs.js'), ('/*EBITDA_EDITOR*/', 'ebitda_editor.js'), ('/*FINANCIAL_TABLE_UI*/', 'financial_table_ui.js'), ('/*ADVANCED_VISUALS*/', 'advanced_visuals.js'), ('/*TREND_CHART_UI*/', 'trend_chart_ui.js'), ('/*DASHBOARD_UPGRADE_UI*/', 'dashboard_upgrade_ui.js'), ('/*RESEARCH_UI*/', 'research_ui.js'),
                         ('/*ENGINE*/', 'engine.js'), ('/*PORTFOLIO_ENGINE*/', 'portfolio_engine.js')]:
        html = html.replace(marker, (src / name).read_text(encoding='utf-8'))
    html = html.replace('/*LIVE_CONFIG*/', script_json(live))
    return html.replace('/*PAYLOAD*/', script_json(dict(snapshot=snapshot, analysis_snapshot=analysis,
        research=research, discovery=discovery, financial_tables=financial_tables, company_details=company_details,market_insights=market_insights,
        trend_following=build_trend_following(discovery['snapshot'] if discovery else analysis,discovery['research'] if discovery else research,market_cache),
        market_summary=market_summary(analysis, market_cache, discovery['snapshot']['meta']['price_date'] if discovery else analysis['meta']['price_date']),
        references=sanitize_references(references or {}, snapshot), detail_html=legacy)))
