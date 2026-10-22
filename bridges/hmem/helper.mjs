// AfyaEvidence adapter; upstream sources remain unchanged. No network listener.
import fs from 'node:fs';
import path from 'node:path';
import { HMEM } from './upstream/src/index.ts';

if (Number(process.versions.node.split('.')[0]) !== 24) throw Error('Node 24 required');
const directory = process.argv[2];
if (!directory || !path.isAbsolute(directory)) throw Error('Absolute trusted store directory required');
// Detect corrupt/unbounded persistence before invoking the reference constructors.
for (const file of ['state.json', 'ledger.jsonl']) {
  const p = path.join(directory, file);
  if (fs.existsSync(p) && fs.statSync(p).size > 2_000_000) throw Error('Store limit exceeded');
}
if (fs.existsSync(path.join(directory,'state.json'))) {
  const s = JSON.parse(fs.readFileSync(path.join(directory,'state.json'),'utf8'));
  if (!Number.isInteger(s.seq) || s.seq < 0 || !Array.isArray(s.records) || s.records.length > 100 ||
      new Set(s.records.map(r=>r.id)).size !== s.records.length ||
      s.records.some(r=>typeof r.id!=='string'||!/^mem-[1-9][0-9]*$/.test(r.id)||Number(r.id.slice(4))>s.seq||typeof r.source!=='string'||typeof r.content!=='string')) throw Error('Invalid state');
}
if(fs.existsSync(path.join(directory,'state.json')) !== fs.existsSync(path.join(directory,'ledger.jsonl'))) throw Error('Incomplete state/ledger');
const hmem = new HMEM({ persistDir: directory, actor:'afyaevidence-review-bridge' });
function exact(obj, keys) {
  if (!obj || Array.isArray(obj) || typeof obj!=='object' ||
      Object.keys(obj).sort().join()!==[...keys].sort().join()) throw Error('Invalid request');
}
function execute(req) {
  exact(req,['id','op','args']);
  if (typeof req.id!=='string' || req.id.length>80) throw Error('Invalid request ID');
  const a=req.args;
  if(req.op==='health') {
    exact(a,[]);
    return {engine:'meterless-hmem-reference',commit:'1742dec56a66e58eef9dda2d2b865823758ca8cd',records:hmem.store.all().length};
  }
  if(req.op==='audit') {
    exact(a,[]);
    return {records:hmem.store.all(),ledger:hmem.ledger.all()};
  }
  if(req.op==='remember_reviewed_note') {
    exact(a,['source','content','scope','review_id','reviewed_at_utc','snapshot_id','analysis_id']);
    if (typeof a.content!=='string'||a.content.length<1||a.content.length>2000||
        typeof a.source!=='string'||!a.source.startsWith('afya-review:')||
        typeof a.review_id!=='string'||typeof a.scope!=='string') throw Error('Invalid note');
    const existing=hmem.store.all().find(r=>r.source===a.source);
    if(existing) {
      if(existing.content!==a.content || existing.chatId!==a.scope) throw Error('Conflicting event retry');
      return {memory_id:existing.id,duplicate:true};
    }
    if(hmem.store.all().length>=100) throw Error('Store record cap exceeded');
    const note=hmem.add({content:a.content,source:a.source,type:'general',layer:'long_term',
      chatId:a.scope,tags:['reviewed-context'],confidence:0.7,
      provenance:{origin:'manual',learnedAt:Date.parse(a.reviewed_at_utc),label:a.review_id,
                  refs:[a.snapshot_id,a.analysis_id]}});
    return {memory_id:note.id,duplicate:false};
  }
  if(req.op==='recall') {
    exact(a,['query','scope','eligible_sources']);
    if(typeof a.query!=='string'||a.query.length<1||a.query.length>1000||
       !Array.isArray(a.eligible_sources)||a.eligible_sources.length>100) throw Error('Invalid query');
    // Rank through the actual engine, then enforce source and scope before returning.
    const allowed=new Set(a.eligible_sources);
    const eligible=hmem.store.all().filter(r=>r.chatId===a.scope&&allowed.has(r.source));
    // A non-persistent view prevents ineligible future notes from affecting scoring,
    // relationships or output, while retaining the actual reference query operation.
    const view=new HMEM({actor:'afyaevidence-scoped-recall'});
    view.store.restoreAll(structuredClone(eligible),100);
    const result=view.query(a.query,{topN:3,threshold:0,chatId:a.scope});
    for(const {memory} of result.memories) hmem.ledger.log(memory.id,'read','afyaevidence-review-bridge');
    return {memories:result.memories.map(({memory,relevance})=>({memory_id:memory.id,source:memory.source,
      content:memory.content,scope:memory.chatId,review_id:memory.provenance.label,
      refs:memory.provenance.refs,relevance}))};
  }
  throw Error('Operation not allowed');
}
let pending='';
process.stdin.setEncoding('utf8');
process.stdin.on('data',chunk=>{
  pending+=chunk;
  if(Buffer.byteLength(pending)>65536) process.exit(2);
  let index;
  while((index=pending.indexOf('\n'))>=0) {
    const line=pending.slice(0,index); pending=pending.slice(index+1);
    let req;
    try {
      req=JSON.parse(line);
      const result=execute(req);
      const output=JSON.stringify({id:req.id,ok:true,result});
      if(Buffer.byteLength(output)>65536) throw Error('Output limit exceeded');
      process.stdout.write(output+'\n');
    } catch {
      process.stdout.write(JSON.stringify({id:typeof req?.id==='string'?req.id:null,ok:false,error:'H-MEM operation rejected'})+'\n');
    }
  }
});
