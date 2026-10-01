'use strict';
const H=require('../src/holdings_sync.js');
let raw='';process.stdin.setEncoding('utf8');process.stdin.on('data',s=>raw+=s);
process.stdin.on('end',()=>{try{const x=JSON.parse(raw),result=x.operation==='merge'?H.merge(x.base,x.local,x.remote,x.choice):H.validate(x.state);console.log(JSON.stringify(result));}catch{process.stderr.write('보유 입력 형식 또는 병합 결과를 확인하세요.');process.exitCode=1;}});
