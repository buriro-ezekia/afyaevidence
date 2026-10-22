// Execute the real UI logic against a small DOM/fetch test harness, not a browser.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element{constructor(){this.value='';this.children=[];this.listeners={};this.hidden=false;this.disabled=false;this.textContent='';}
 append(x){this.children.push(x);}replaceChildren(...xs){this.children=xs;}addEventListener(n,fn){this.listeners[n]=fn;}}
const elements=new Map();const element=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
let actor={subject:'person',issuer:'https://fixture.invalid',roles:['reviewer']};let fail=false;let posts=0;
const record={run_id:'run_demo',revision:1,disposition:'accept',candidate:{summary:'<img src=x onerror=bad()>',limitations:['synthetic_data']},execution:{data_mode:'zetaris',model_mode:'ollama',memory_mode:'hmem_reference'},provenance_status:'receipt_top_level',evidence:{metrics:[]},history:[{at:'now',reviewer:'local_operator',disposition:'accept',reason:'Earlier synthetic decision.',identity:{kind:'legacy_unverified'}}]};
for(const period of ['comparison','target'])for(const [name,value]of[['positive_total',100],['tested_total',500],['positivity_pct',20]])record.evidence.metrics.push({period,name,value,cohort:'all_available',view:'canonical',availability:'available'});
const context={document:{getElementById:element,createElement:()=>new Element()},AbortController,crypto:require('node:crypto').webcrypto,
 fetch:async(path,opts)=>{if(opts.method==='POST')posts++;return{ok:!fail,status:fail?401:200,json:async()=>fail?{error:'unauthorised'}:JSON.parse(JSON.stringify(path==='/api/me'?actor:record))};}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
(async()=>{element('run').value='run_demo';element('token').value='test-only';await element('load').listeners.click();
 assert.equal(element('metrics').children[0].children[3].textContent,'500');assert.equal(element('metrics').children[1].children[4].textContent,'20');
 assert.equal(element('submit').disabled,true);assert.match(element('reviewMessage').textContent,/Nothing to fill/);assert.match(element('history').children[0].textContent,/not individually verified/);
 assert.equal(element('summary').textContent,'<img src=x onerror=bad()>');
 element('run').listeners.input();assert.equal(element('content').hidden,true);await element('submit').listeners.click();assert.equal(posts,0);
 record.disposition=null;record.revision=0;record.history=[];actor.roles=['viewer'];await element('load').listeners.click();assert.equal(element('submit').disabled,true);
 fail=true;await element('load').listeners.click();assert.equal(element('content').hidden,true);assert.equal(element('raw').textContent,'');
 console.log('IDENTITY_UI_LOGIC=PASS (DOM harness; not visual browser acceptance)');})().catch(e=>{console.error(e);process.exitCode=1;});
