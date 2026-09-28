from html import escape
from .core import valuation,num,digest

def onepager(snapshot,row,research):
    e=lambda v:escape(str(v))
    labels=dict(market_cap_eok='시가총액 · 억원',operating_margin_pct='영업이익률 · %',roe_pct='ROE · %',debt_ratio_pct='부채비율 · %',net_debt_equity_pct='순차입금/자본 · %',interest_coverage_x='이자보상배율 · 배',current_ratio_pct='유동비율 · %',revenue_growth_pct='매출 증가율 · %',foreign_net_20d_eok='외국인 순매수 · 억원',institution_net_20d_eok='기관 순매수 · 억원',foreign_net_turnover_20d_pct='외국인/거래대금 · %',institution_net_turnover_20d_pct='기관/거래대금 · %',avg_trading_value_20d_eok='평균 거래대금 · 억원',eps_ttm='TTM EPS · 원',price='가격 · 원',per='PER · 배',pbr='PBR · 배')
    m=snapshot['meta']; metrics=''.join(f'<tr><td>{e(labels.get(k,k))}</td><td>{v:,.2f}</td></tr>' for k,v in list(row['metrics'].items())[:16] if num(v))
    names=dict(turnaround='턴어라운드',domestic='내수 성장',substitution='수입대체',technology='기술',returns='주주환원')
    paths=' · '.join(names[p] for p,v in research['paths'].items() if v['signal_status']=='pass') or '수치 신호 없음 / 자료 부족'
    risk=row.get('data_quality',[])
    # Explicit summary receipt instead of clipping/hidden overflow.
    summaries=[str(x)[:140] for x in risk[:4]]
    risks=''.join('<li>'+e(s)+'</li>' for s in summaries)
    policy=' · '.join(row.get('user_policy_evidence',{}).get('labels',[]))
    if row.get('additional_financial_evidence',{}).get('provider_priority_applied'):
        policy+=' · 순차입금은 인포맥스 우선·원문 보충 혼합 출처 추정치'
    quality=f"{research['quality_score']:.1f}" if num(research['quality_score']) else '자료 부족'
    source_rows=row.get('sources',[])
    sources=''.join('<li>'+e(s.get('label',''))[:90]+' — '+e(s.get('url',''))[:220]+'</li>' for s in source_rows[:3])
    val=valuation(snapshot,row)
    scenario=' / '.join(f'{v:,.0f}원' for v in val['scenarios']) if val['scenarios'] else '산출 불가: '+val['reason']
    prices=row.get('prices',[])[-60:]; chart='가격 이력 미확보'
    if len(prices)>1 and all(num(p.get('close')) for p in prices):
        values=[p['close'] for p in prices]; lo,hi=min(values),max(values)
        points=' '.join(f'{i*480/(len(values)-1):.1f},{70-(v-lo)/max(hi-lo,1)*60:.1f}' for i,v in enumerate(values))
        chart=f'<svg viewBox="0 0 480 80" aria-label="최근 관측 가격 추이"><polyline fill="none" stroke="#245bb0" stroke-width="2" points="{points}"/></svg>'
    return f'''<!doctype html><html lang="ko"><meta charset="utf-8"><title>{e(row['name'])} One-Pager</title>
    <style>@page{{size:A4;margin:12mm}}*{{box-sizing:border-box}}body{{font:11px/1.45 "Malgun Gothic",sans-serif;color:#16304a;margin:0}}h1{{font-size:24px}}h2{{font-size:14px;border-bottom:1px solid #bbb}}.cols{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}td{{padding:3px;border-bottom:1px solid #ddd}}table{{width:100%}}li{{overflow-wrap:anywhere}}svg{{width:100%;height:80px}}.badge{{padding:8px;background:#edf3fd}}footer{{font-size:9px;margin-top:10px}}@media screen{{body{{max-width:186mm;margin:20px auto}}}}</style>
    <h1>{e(row['name'])} · {e(row['code'])}</h1><div class="badge">{'가상 테스트' if m['data_mode']=='fixture' else '실제 저장자료 · 부분 모집단'} · 가격 {e(m['price_date'])} · 재무 {e(m['financial_period'])} / {e(m['financial_basis'])}</div>
    <p>{e(row['market'])} / {e(row['industry'])} · 사업 설명 미입력 · 조회·연구 전용</p><p>{e(policy)}</p>
    <div class="cols"><section><h2>핵심 관측 지표 · 최대 16개 요약</h2><table>{metrics}</table></section>
    <section><h2>최근 가격 관측</h2>{chart}<h2>연구 신호와 근거</h2><p>{e(paths)}</p><p>경로 문서 근거는 별도 검토 상태. 품질 점수: {quality}</p>
    <h2>상대가치 시나리오</h2><p>{e(scenario)}</p><p>대상 제외 피어 {val['peer_count']}개. 미래 확률·확정 목표가 아님.</p><h2>반대 근거·제한</h2><ul>{risks}</ul><p>확인 항목 {len(risk)}개 중 {len(summaries)}개 요약. 전체 근거·장문은 앱과 동일 스냅샷에서 확인.</p></section></div>
    <h2>출처</h2><ul>{sources or '<li>실제 원문 출처 없음 · 가상 데이터 또는 근거 미확보</li>'}</ul><p>출처 {len(source_rows)}개 중 최대 3개 요약. 100배 수익·성공 확률을 예측하지 않습니다.</p>
    <footer>스냅샷 {digest(snapshot)[:16]} · 모형 {e(research['model'])} · 사용자 기준 및 미확인 사항은 앱에 보존. 관측 부족을 0으로 대체하지 않음.</footer></html>'''
