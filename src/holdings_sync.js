/* Shared browser/server contract. Three-way merges never guess between conflicting edits. */
'use strict';
const HoldingsSync = (() => {
  const P=typeof PortfolioEngine!=='undefined'?PortfolioEngine:require('./portfolio_engine.js');
  const copy=v=>v===undefined?undefined:P.clone(v);
  const canonical=v=>v===undefined?'undefined':JSON.stringify(v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.keys(v).sort().map(k=>[k,JSON.parse(canonical(v[k]))])):Array.isArray(v)?v.map(x=>JSON.parse(canonical(x))):v);
  const equal=(a,b)=>canonical(a)===canonical(b);
  function keys(x,allowed){if(!x||Object.keys(x).some(k=>!allowed.includes(k)))throw Error('보유 동기화에 알 수 없는 입력 항목이 있습니다. 입력 파일을 확인하세요.');}
  function validate(s){
    if(!s||s.version!==1)throw Error('보유 저장 형식을 확인하세요.');
    P.validate(s.input);if(s.input.mode!=='user_input')throw Error('가상 예제는 PC 간 보유 동기화에 포함하지 않습니다.');
    keys(s,['version','input','policy']);keys(s.input,['schema_version','mode','as_of','snapshot_id','cash_krw','holdings','research','market_data_as_of']);keys(s.policy,Object.keys(P.DEFAULT));
    for(const h of s.input.holdings)keys(h,['code','quantity','avg_cost_krw','thesis_note']);
    for(const r of s.input.research){
      keys(r,['code','issuer_id','name','market','security_type','analysis_profile','sector','risk_group','price_krw','price_date','price_source','review','evidence','pending_events']);
      keys(r.review,['thesis','business','finance','valuation','material_risk','reviewed_on','financial_period','positives','negatives','invalidation','next_review_on']);
      if(r.price_source)keys(r.price_source,['kind','label','snapshot_id','url']);
      for(const e of r.evidence)keys(e,['id','label','url','available_on','reviewed']);
      for(const e of r.pending_events||[])keys(e,['id','title','url','published_on']);
    }
    P.cleanPolicy(s.policy);return s;
  }
  function pack(input,policy){return validate({version:1,input:copy(input),policy:P.cleanPolicy(policy)});}
  function shape(s){
    if(!s)return undefined;
    const x=copy(validate(s));
    for(const k of ['as_of','snapshot_id','market_data_as_of'])delete x.input[k];
    for(const r of x.input.research){
      r.price_record={};r.identity_record={};
      for(const k of ['price_krw','price_date','price_source']){r.price_record[k]=r[k];delete r[k];}
      for(const k of ['issuer_id','name','market','security_type','analysis_profile']){r.identity_record[k]=r[k];delete r[k];}
    }
    return x;
  }
  function merge(base,local,remote,choice=null){
    const conflicts=[];
    function walk(b,l,r,path){
      if(equal(l,r))return copy(l);
      if(equal(l,b))return copy(r);
      if(equal(r,b))return copy(l);
      const last=path.split('/').pop();
      if(l&&r&&typeof l==='object'&&typeof r==='object'&&!Array.isArray(l)&&!Array.isArray(r)&&b!==undefined&&!['price_record','identity_record'].includes(last)){
        const x=Object.create(null);for(const k of new Set([...Object.keys(b||{}),...Object.keys(l),...Object.keys(r)])){
          const v=walk(b?.[k],l[k],r[k],path+'/'+k);if(v!==undefined)x[k]=v;
        }return x;
      }
      const key=['holdings','research'].includes(last)?'code':['evidence','pending_events'].includes(last)?'id':null;
      if(key&&Array.isArray(l)&&Array.isArray(r)){
        const maps=[b||[],l,r].map(a=>new Map(a.map(v=>[v[key],v]))),items=[];
        for(const id of [...new Set(maps.flatMap(m=>[...m.keys()]))].sort()){
          const v=walk(maps[0].get(id),maps[1].get(id),maps[2].get(id),path+'/'+id);if(v!==undefined)items.push(v);
        }return items;
      }
      conflicts.push({path,local:copy(l)??null,remote:copy(r)??null});
      return copy(choice==='remote'?r:l);
    }
    // An absent initial base is an empty collection, not permission to overwrite another PC.
    const shapedLocal=shape(local),shapedRemote=shape(remote);
    let shapedBase=shape(base);
    if(!shapedBase&&shapedLocal&&shapedRemote)shapedBase={version:1,input:{schema_version:'holdings-portfolio-0.1',mode:'user_input',cash_krw:null,holdings:[],research:[]},policy:P.cleanPolicy()};
    const state=walk(shapedBase,shapedLocal,shapedRemote,'');
    if(state){
      const template=local||remote;
      for(const k of ['as_of','snapshot_id','market_data_as_of'])if(template.input[k]!==undefined)state.input[k]=template.input[k];
      for(const r of state.input.research){Object.assign(r,r.price_record,r.identity_record);delete r.price_record;delete r.identity_record;}
      validate(state);
    }
    return {state:state||null,conflicts};
  }
  return Object.freeze({pack,validate,merge,equal});
})();
if(typeof module!=='undefined')module.exports=HoldingsSync;
