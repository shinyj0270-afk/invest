"""Read-only, bounded transport. Credentials never persisted or put in errors."""
import os
import time
import requests

class AdapterError(ValueError): pass
class SetupPending(AdapterError): pass

KIWOOM={'ka10001':'/api/dostk/stkinfo','ka10059':'/api/dostk/stkinfo','ka10081':'/api/dostk/chart'}
DART={'financial':'fnlttSinglAcntAll.json','disclosures':'list.json'}

class Reader:
    def __init__(self,profile,permissions,session=None,sleep=time.sleep):
        self.profile=profile; self.permissions=permissions; self.session=session or requests.Session(); self.sleep=sleep
    def _request(self,method,url,**kwargs):
        for attempt in range(3):
            self.sleep(.3 if attempt==0 else 2**attempt)
            try: r=self.session.request(method,url,timeout=(5,20),allow_redirects=False,**kwargs)
            except requests.RequestException:
                if attempt==2: raise AdapterError('network_unavailable') from None
                continue
            if r.status_code in (401,403): raise AdapterError('authentication_failed')
            if r.status_code==429 or r.status_code>=500:
                if attempt==2: raise AdapterError('retry_limit')
                continue
            if r.status_code!=200: raise AdapterError('http_failed')
            try: body=r.json()
            except (ValueError,TypeError): raise AdapterError('invalid_json') from None
            return body,{k.lower():v for k,v in r.headers.items()}
        raise AdapterError('retry_limit')
    def _guard(self,provider):
        if self.profile not in ('home','work') or self.permissions.get(provider) is not True:
            raise SetupPending('명시적 PC 프로필·공급자 조회 권한 설정 대기')
    def kiwoom(self,tr,params):
        if tr not in KIWOOM: raise AdapterError('read_only_TR_allowlist')
        self._guard('kiwoom')
        if self.permissions.get('kiwoom_spec_verified') is not True: raise SetupPending('현재 공식 TR 입력·단위·거래소 정의 검토 대기')
        token=os.environ.get('KIWOOM_ACCESS_TOKEN')
        if not token: raise SetupPending('KIWOOM_ACCESS_TOKEN 설정 대기')
        pages=[]; next_key=''; seen=set()
        for _ in range(100):
            body,headers=self._request('POST','https://api.kiwoom.com'+KIWOOM[tr],
                headers={'authorization':'Bearer '+token,'api-id':tr,'cont-yn':'Y' if next_key else 'N','next-key':next_key},json=params)
            if str(body.get('return_code'))!='0': raise AdapterError('provider_body_failed')
            pages.append(body)
            if headers.get('cont-yn')!='Y': return pages
            next_key=headers.get('next-key','')
            if not next_key or next_key in seen: raise AdapterError('incomplete_pagination')
            seen.add(next_key)
        raise AdapterError('page_limit')
    def dart(self,kind,params):
        if kind not in DART: raise AdapterError('read_only_endpoint_allowlist')
        self._guard('dart'); key=os.environ.get('OPENDART_API_KEY')
        if not key: raise SetupPending('OPENDART_API_KEY 설정 대기')
        if 'crtfc_key' in params: raise AdapterError('credentials_must_use_environment')
        records=[]
        for page in range(1,101):
            query=dict(params,crtfc_key=key)
            if kind=='disclosures': query.update(page_no=page,page_count=100)
            body,_=self._request('GET','https://opendart.fss.or.kr/api/'+DART[kind],params=query)
            code=body.get('status')
            if code=='013':
                if page==1: return []
                raise AdapterError('incomplete_pagination')
            if code!='000': raise AdapterError('provider_body_failed_'+str(code) if str(code).isdigit() else 'provider_body_failed')
            rows=body.get('list')
            if not isinstance(rows,list) or not rows: raise AdapterError('empty_success_response')
            records.extend(rows)
            if kind!='disclosures' or page>=int(body.get('total_page',1)): return records
        raise AdapterError('page_limit')

ACCOUNT_IDS={'ifrs-full_Revenue':'revenue','dart_OperatingIncomeLoss':'op',
    'ifrs-full_Equity':'equity','ifrs-full_Liabilities':'liabilities',
    'ifrs-full_CurrentAssets':'current_assets','ifrs-full_CurrentLiabilities':'current_liabilities',
    'ifrs-full_CashAndCashEquivalents':'cash','ifrs-full_CashFlowsFromUsedInOperatingActivities':'ocf'}

def normalize_dart(rows,period_end,available_at,basis='CFS'):
    """Quarter IS is 3 months; CF remains cumulative and is labelled explicitly."""
    result=dict(period_end=period_end,available_at=available_at,basis=basis,source='OpenDART',unit='KRW',currency='KRW',unmapped=[])
    seen=set()
    for r in rows:
        if r.get('currency')!='KRW': raise AdapterError('currency_unverified')
        field=ACCOUNT_IDS.get(r.get('account_id'))
        if field is None: result['unmapped'].append(r.get('account_id')); continue
        if field in seen: raise AdapterError('ambiguous_account')
        seen.add(field)
        raw=r.get('thstrm_amount','').replace(',','')
        try: result[field]=int(raw) if raw else None
        except ValueError: raise AdapterError('invalid_amount') from None
        result[field+'_report_id']=r.get('rcept_no')
        if field=='ocf': result['ocf_comp']='cumulative'
    return result
