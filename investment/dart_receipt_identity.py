"""Bind an inventoried viewer to the issuer and exact official receipt tree."""
import re
from html import unescape
from urllib.parse import urlsplit,parse_qs


def verify_receipt_section(text,viewer_url,receipt,corp,legal_name):
    clean=lambda s:re.sub(r'\s+','',unescape(re.sub('<[^>]+>','',s)))
    companies=re.findall(r"<span[^>]*onclick=[\"'][^>]*openCorpInfoNew\('([0-9]{8})'.*?>(.*?)</span>",text,re.S)
    if (corp,clean(legal_name)) not in [(c,clean(n)) for c,n in companies]:raise ValueError('제출 원문 회사 식별 불일치')
    query=parse_qs(urlsplit(viewer_url).query);fields=('rcpNo','dcmNo','eleId','offset','length','dtd')
    if any(len(query.get(k,[]))!=1 for k in fields) or query['rcpNo']!=[receipt]:raise ValueError('원문 재무 섹션 주소 미확인')
    # Every field must belong to ONE tree node, never independently appear elsewhere.
    pattern=r"(node\d+)\['rcpNo'\]\s*=\s*[\"']([^\"']+)[\"'];(.*?)(?:\1\['tocNo'\]|cnt\+\+;)"
    matches=[]
    for node,rcp,block in re.findall(pattern,text,re.S):
        values={'rcpNo':rcp}
        for field in fields[1:]:
            found=re.search(re.escape(node)+r"\['"+field+r"'\]\s*=\s*[\"']([^\"']+)[\"']",block)
            if found:values[field]=found[1]
        if all(query[k]==[values.get(k)] for k in fields):matches.append(values)
    if len(matches)!=1:raise ValueError('공식 제출 목차와 재무 섹션 연결 미확인')
    return dict(corp_code=corp,legal_name=legal_name,receipt=receipt,viewer_node=matches[0])
