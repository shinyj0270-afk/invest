"""Offline HTML viewer using the existing market and portfolio engines."""
import json
from copy import deepcopy
from pathlib import Path
from .core import validate_snapshot
from .holdings_bridge import holdings_input, holdings_catalog
from .valuation import enrich_valuation
from .workspace_research import build_research
from .naver_reference import sanitize_references
from .market_discovery import build_discovery
from .financial_table import build_table
from .company_detail import build_details
from .market_history import benchmark_calendar, DAILY_PUBLICATION_TIME
from .financial_metrics import common_metrics,apply_common
from .market_insights import enrich_market
from .trend_following import build_trend_following
from .verification import verify_company, compact as compact_verification
from .thesis_monitor import load_theses, evaluate as evaluate_thesis

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
            source = deepcopy(record.get('source'))
        else:
            bars = [b for b in snapshot.get('benchmarks', {}).get(market, [])
                    if b.get('final') is True and b.get('date', '') <= target_date]
            source = deepcopy(snapshot['meta'].get('source'))
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


def export_holdings_frame(snapshot, *, live=None, market_cache=None, analysis_snapshot=None):
    """Existing holdings iframe contract, loaded separately for live dashboards."""
    analysis = analysis_snapshot or enrich_valuation(snapshot)
    if analysis_snapshot is None:
        research=build_research(analysis)
        for row in analysis['companies']:
            facts=research['rows'].get(row['code'])
            if facts:row['metrics'].update(facts['fundamental']['metrics'])
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
    legacy = legacy.replace('<body>', '<body class="soft-legacy">', 1)
    legacy = legacy.replace('</head>', '<style>' + (src / 'soft_ui.css').read_text(encoding='utf-8') + '</style></head>')
    legacy = legacy.replace('</head>', '<style>header{display:none}main{max-width:none;padding:0}body{background:transparent}.notice,#scopeBar,.foot,#clearData{display:none}</style></head>')
    return legacy


def compact_live_payload(payload):
    """Share duplicate summary contracts on the wire; selected detail stays lazy."""
    payload['wire_format']='live-v2'
    payload.pop('snapshot', None)
    discovery=payload.get('discovery')
    if discovery:
        for row in discovery['snapshot']['companies']:
            # Cache histories belong to /company-view, never the overview wire format.
            for key in ('prices','trend_prices','annual','quarters'):
                row.pop(key,None)
            # Detailed dependency rows remain in the authenticated company view.
            # Keep dates, publication uncertainty and qualification in overview.
            for detail in list(row.get('metric_details',{}).values())+list(row.get('valuation_details',{}).values()):
                if isinstance(detail,dict) and isinstance(detail.get('dependencies'),list):
                    detail['dependency_count']=len(detail.pop('dependencies'))
            valuation=row.get('valuation_details')
            if valuation and all(detail==row.get('metric_details',{}).get(k) for k,detail in valuation.items()):
                row.pop('valuation_details',None);row['valuation_from_details']=True
            facts=discovery['research']['rows'].get(row['code'],{})
            f=facts.get('fundamental',{})
            if f.get('metrics')=={k:row.get('metrics',{}).get(k) for k in f.get('metrics',{})}:
                f.pop('metrics',None);f['metrics_from_row']=True
            if f.get('metric_details')==row.get('metric_details'):
                f.pop('metric_details',None);f['details_from_row']=True
            common=row.get('common_financial')
            if common and common.get('metric_details')==row.get('metric_details'):
                common.pop('metric_details',None);common['details_from_row']=True
            if common and common.get('financial_completeness')==row.get('financial_completeness'):
                common.pop('financial_completeness',None);common['completeness_from_row']=True
    for row in payload.get('trend_following',{}).get('rows',[]):
        technical=row.get('technical',{})
        if technical.get('trend_analysis')==row.get('analysis'):
            technical.pop('trend_analysis',None);row['analysis_shared']=True
        original=(payload.get('discovery') or {}).get('research',{}).get('rows',{}).get(row['code'],{}).get('technical',{})
        if technical and all(value==original.get(key) for key,value in technical.items()):
            row['technical_from_research']=list(technical)
            row.pop('technical',None)
    share_live_text(payload)


def share_live_text(payload):
    """Losslessly share repeated source descriptions; reserve no input namespace."""
    from collections import Counter
    marker='__investment_wire_text__'
    counts=Counter();stack=[payload]
    while stack:
        value=stack.pop()
        if isinstance(value,dict):
            # Existing input with our reserved key is preserved without encoding.
            if marker in value or 'wire_text' in value:return
            stack.extend(value.values())
        elif isinstance(value,list):stack.extend(value)
        elif isinstance(value,str) and len(value.encode('utf-8'))>=80:counts[value]+=1
    texts=[value for value,count in counts.items() if count>1 and (len(value.encode('utf-8'))-40)*count>len(value.encode('utf-8'))+4]
    if not texts:return
    lookup={value:i for i,value in enumerate(texts)}
    def encode(value):
        if isinstance(value,str) and value in lookup:return {marker:lookup[value]}
        if isinstance(value,dict):
            for key,item in value.items():value[key]=encode(item)
        elif isinstance(value,list):
            for i,item in enumerate(value):value[i]=encode(item)
        return value
    encode(payload)
    payload['wire_text']=texts


def export_workspace(snapshot, *, live=None, events=None, references=None, market_cache=None, financials=None, trend_following_data=None, trend_checkpoint_directory=None):
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
    # Keep the reviewed snapshot intact; charts follow the validated discovery price date.
    # Financial availability may use today's separate cutoff even before today's close.
    price_cutoff=(discovery or {}).get('snapshot',{}).get('meta',{}).get('price_date') or analysis['meta']['price_date']
    detail_scope=dict(analysis,meta=dict(analysis['meta'],price_date=price_cutoff))
    company_details = {} if (live or {}).get('lazy_company_views') else build_details(detail_scope, financial_tables, market_cache)
    theses=load_theses();thesis_tables={}
    if discovery:
        for row in discovery['snapshot']['companies']:
            row['collection_health']=(financials or {}).get(row['code'],{}).get('collection_health',{})
            if row['code'] not in discovery['research']['rows']:continue
            table=financial_tables.get(row['code'])
            if table is None and (financials or {}).get(row['code']):
                table=build_table(row,financial_scope,financials[row['code']],max_columns=48)
            if table:
                row['financial_completeness']=table.get('financial_completeness')
                common=common_metrics(row,table,discovery['research']['rows'][row['code']]['technical'])
                if row['code'] in theses:thesis_tables[row['code']]=table
                apply_common(row,discovery['research']['rows'][row['code']],common)
                if row['code'] in company_details:company_details[row['code']]['common_financial']=row.get('common_financial')
                if row.get('common_financial'):
                    checked=next((r for r in analysis['companies'] if r['code']==row['code']),None)
                    if checked:checked['metrics'].update(row['common_financial']['metrics']);research['rows'][row['code']]['fundamental']['metrics'].update(row['common_financial']['metrics'])
    if discovery:
        extra=[r for r in discovery['snapshot']['companies'] if r['code'] not in company_details and (financials or {}).get(r['code'])] if not (live or {}).get('lazy_company_views') else []
        if extra:
            scope=dict(meta={**analysis['meta'],'price_date':financial_cutoff},companies=extra)
            extra_tables={r['code']:build_table(r,scope,financials[r['code']],max_columns=48) for r in extra}
            financial_tables.update(extra_tables)
            chart_scope=dict(scope,meta=dict(scope['meta'],price_date=price_cutoff))
            company_details.update(build_details(chart_scope,extra_tables,market_cache))
            for r in extra:company_details[r['code']]['common_financial']=r.get('common_financial')
    if discovery:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        verified_on=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
        for row in discovery['snapshot']['companies']:
            technical=discovery['research']['rows'].get(row['code'],{}).get('technical')
            row['verification']=compact_verification(verify_company(row,technical,verified_on))
    market_insights=enrich_market(discovery,market_cache)
    # Every analysis view uses the same date-checked metrics; keep original payload intact.
    for row in analysis['companies']:
        facts = research['rows'].get(row['code'])
        if facts:
            row['metrics'].update(facts['fundamental']['metrics'])
    src = ROOT / 'src'
    legacy = None if (live or {}).get('lazy_holdings_frame') else export_holdings_frame(snapshot,live=live,market_cache=market_cache,analysis_snapshot=analysis)
    html = (src / 'workspace.html').read_text(encoding='utf-8')
    # Insert payload last so data containing template marker text stays literal.
    for marker, name in [('/*DASHBOARD_STABILITY*/', 'dashboard_stability.js'), ('/*WORKSPACE_CSS*/', 'workspace.css'), ('/*SOFT_UI_CSS*/','soft_ui.css'), ('/*HOME_DASHBOARD_UI*/', 'home_dashboard_ui.js'), ('/*VERIFICATION_UI*/', 'verification_ui.js'), ('/*HOLDINGS_BRIEF_UI*/', 'holdings_brief_ui.js'), ('/*WORKSPACE_JS*/', 'workspace.js'),
                         ('/*DASHBOARD_JOURNEY*/', 'dashboard_journey.js'),
                         ('/*MARKET_EXPLANATION_CSS*/', 'market_explanation.css'), ('/*MARKET_EXPLANATION_UI*/', 'market_explanation_ui.js'),
                         ('/*TREND_CHANGES_UI*/', 'trend_changes_ui.js'), ('/*RISK_REVIEW_UI*/', 'risk_review_ui.js'),
                         ('/*FINANCIAL_COMPLETENESS_UI*/', 'financial_completeness_ui.js'), ('/*FINANCIAL_REVIEW_CSS*/', 'financial_review.css'),
                         ('/*TREND_FOLLOWING_UI*/', 'trend_following_ui.js'), ('/*TREND_FOLLOWING_CSS*/', 'trend_following.css'),
                         ('/*COMPANY_DETAIL_CSS*/', 'company_detail.css'), ('/*COMPANY_DETAIL_ENGINE*/', 'company_detail_engine.js'), ('/*COMPANY_DETAIL_UI*/', 'company_detail_ui.js'),
                         ('/*DISCOVERY_ENGINE*/', 'discovery_engine.js'), ('/*EBITDA_INPUTS*/', 'ebitda_inputs.js'), ('/*EBITDA_EDITOR*/', 'ebitda_editor.js'), ('/*FINANCIAL_TABLE_UI*/', 'financial_table_ui.js'), ('/*ADVANCED_VISUALS*/', 'advanced_visuals.js'), ('/*TREND_CHART_UI*/', 'trend_chart_ui.js'), ('/*DASHBOARD_UPGRADE_UI*/', 'dashboard_upgrade_ui.js'), ('/*RESEARCH_UI*/', 'research_ui.js'),
                         ('/*ENGINE*/', 'engine.js'), ('/*PORTFOLIO_ENGINE*/', 'portfolio_engine.js')]:
        html = html.replace(marker, (src / name).read_text(encoding='utf-8'))
    html = html.replace('/*LIVE_CONFIG*/', script_json(live))
    trend_data = trend_following_data or build_trend_following(discovery['snapshot'] if discovery else analysis,discovery['research'] if discovery else research,market_cache)
    if trend_checkpoint_directory is not None:
        from .trend_checkpoints import observe_trend
        try:
            trend_data['changes']=observe_trend(trend_data,trend_checkpoint_directory)
        except (OSError,ValueError,TypeError) as exc:
            trend_data['changes']=dict(status='pending',reason='추세 관측 저장 대기: '+str(exc),events=[])
    # Thesis checks need the trend diagnostics and market regime, so they run after the trend board exists.
    trend_rows={r['code']:r for r in trend_data.get('rows',[])};regimes={m['market']:m.get('regime') for m in trend_data.get('markets',[])}
    thesis_monitor={code:evaluate_thesis(theses[code],table,((discovery or {}).get('research',{}).get('rows',{}).get(code,{}).get('technical')),trend_rows.get(code),regimes.get(trend_rows.get(code,{}).get('market'))) for code,table in thesis_tables.items()}
    payload=dict(snapshot=snapshot, analysis_snapshot=analysis,
        research=research, discovery=discovery, financial_tables=financial_tables, company_details=company_details,market_insights=market_insights,thesis_monitor=thesis_monitor,
        trend_following=trend_data, market_contract=dict(same_day_after='%02d:%02d'%DAILY_PUBLICATION_TIME,timezone='Asia/Seoul'),
        market_summary=market_summary(analysis, market_cache, discovery['snapshot']['meta']['price_date'] if discovery else analysis['meta']['price_date']),
        references=sanitize_references(references or {}, snapshot), detail_html=legacy)
    if (live or {}).get('lazy_company_views'):
        # Wire compaction edits only a private graph, outside source caches
        # and caller-supplied trend models.
        payload=deepcopy(payload)
        payload['financial_tables']={}
        compact_live_payload(payload)
    return html.replace('/*PAYLOAD*/', script_json(payload))
