"""Readable, evidence-grounded local review dashboard. No external assets."""
PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AfyaEvidence | Evidence review</title>
<style>
:root{font-family:system-ui,-apple-system,sans-serif;color:#172b43;background:#f3f6fa}
*{box-sizing:border-box}body{margin:0}.top{background:#10283e;color:white;padding:20px max(22px,calc((100vw - 1160px)/2))}
.top h1{margin:0;font-size:23px}.top p{margin:7px 0 0;color:#c8d9e7}
main{max-width:1160px;margin:24px auto;padding:0 18px;display:grid;gap:18px}
.panel{background:white;border:1px solid #dce4ed;border-radius:12px;padding:20px;box-shadow:0 2px 10px #1c365008}
h2{margin:0 0 14px;font-size:18px}h3{font-size:15px;margin:18px 0 8px}
label{display:block;font-size:13px;font-weight:650;margin-bottom:6px}
input,select,textarea{width:100%;padding:10px;border:1px solid #b7c5d2;border-radius:7px;font:inherit;background:white}
textarea{min-height:100px}.fields{display:grid;grid-template-columns:1fr 1fr auto;gap:12px;align-items:end}
button{background:#0864ad;border:0;color:white;border-radius:7px;padding:11px 17px;cursor:pointer;font-weight:650}
button:disabled{opacity:.5;cursor:not-allowed}.muted{color:#567086}.small{font-size:13px}
.metricGrid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.metric{background:#f2f7fb;border:1px solid #dce7ee;border-radius:9px;padding:15px}
.metric strong{display:block;font-size:25px;margin-top:5px}.metric span{font-size:12px;color:#516b81}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:10px;text-align:left;border-bottom:1px solid #e0e8ef}th{background:#f2f5f8}
.tableWrap{overflow:auto}.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}.pill{display:inline-block;padding:5px 10px;border-radius:999px;background:#e6eff9;font-size:12px;font-weight:bold}
.success{color:#147047}.warn{color:#925500}.error{color:#a52435}details{margin-top:16px}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:400px;overflow:auto;background:#f2f5f8;padding:15px}
#message{white-space:pre-wrap;min-height:18px}ul{padding-left:22px}li{margin:7px 0}
@media(max-width:800px){.fields,.two{grid-template-columns:1fr}.metricGrid{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style></head><body>
<header class="top"><h1>AfyaEvidence <span style="font-weight:400">/ Evidence review</span></h1>
<p>Evidence-based synthetic reporting investigation · Human disposition only · No clinical approval</p></header>
<main>
<section class="panel"><h2>Load an investigation</h2>
<div class="fields"><div><label for="token">Private review token</label><input type="password" id="token" autocomplete="off"></div>
<div><label for="run">Run ID</label><input id="run" autocomplete="off" placeholder="run_..."></div>
<button id="loadBtn">Load candidate</button></div><p class="small muted">The token remains in this browser tab. Never include it in screenshots or exported evidence.</p>
<p id="message" role="status" aria-live="polite"></p></section>
<section id="dashboard" hidden>
<div class="panel"><h2>Investigation overview <span id="status" class="pill"></span></h2>
<p id="summary"></p><p class="small muted" id="identity"></p>
<p id="executionModes" class="small"></p><p id="provenanceState" class="small muted"></p>
<div class="metricGrid" id="metrics"></div>
<h3>Monthly comparison</h3><div class="tableWrap"><table><thead><tr><th>Period</th><th>Canonical positives</th><th>Raw positives</th><th>Canonical tested</th><th>Canonical positivity</th></tr></thead><tbody id="comparison"></tbody></table></div></div>
<div class="two"><div class="panel"><h2>Report-version history</h2><p class="small muted">Raw totals include report versions; canonical totals apply the reviewed version-selection policy.</p>
<div class="tableWrap"><table><thead><tr><th>Facility</th><th>Month</th><th>Report</th><th>Version</th><th>Positives</th></tr></thead><tbody id="versions"></tbody></table></div></div>
<div class="panel"><h2>Matched-facility contributions</h2><div class="tableWrap"><table><thead><tr><th>Facility</th><th>Earlier</th><th>Later</th><th>Change</th></tr></thead><tbody id="facilities"></tbody></table></div></div></div>
<div class="two"><div class="panel"><h2>Limitations and next checks</h2><h3>Limitations</h3><ul id="limitations"></ul><h3>Next checks</h3><ul id="checks"></ul></div>
<div class="panel"><h2>Review history</h2><div id="history" class="small"></div><h3>Record a disposition</h3>
<label for="decision">Decision</label><select id="decision"><option value="accept">Accept for review record</option><option value="request_more_evidence">Request more evidence</option><option value="reject">Reject</option></select>
<label for="reason">Reason (at least 10 characters)</label><textarea id="reason"></textarea>
<p class="small muted">One immutable disposition per imported run. Accepting does not alter source data.</p>
<button id="submitBtn">Record disposition</button></div></div>
<div class="panel"><details><summary>Technical JSON, evidence identifiers and provenance</summary><pre id="raw"></pre></details></div>
</section></main>
<script>
"use strict";
const $=id=>document.getElementById(id);let current=null,submissionKey=null;
const fmt=x=>x===undefined||x===null?"—":String(x);
function cell(tr,v){const td=document.createElement("td");td.textContent=fmt(v);tr.append(td)}
function tableRows(id,rows){$(id).replaceChildren();for(const values of rows){const tr=document.createElement("tr");values.forEach(v=>cell(tr,v));$(id).append(tr)}}
function list(id,values){$(id).replaceChildren();for(const value of values){const li=document.createElement("li");li.textContent=String(value).replaceAll("_"," ");$(id).append(li)}}
function metric(label,value){const div=document.createElement("div");div.className="metric";const title=document.createElement("span");title.textContent=label;const strong=document.createElement("strong");strong.textContent=fmt(value);div.append(title,strong);return div}
async function api(path,method="GET",body){const response=await fetch(path,{method,headers:{"Authorization":"Bearer "+$("token").value,"Content-Type":"application/json"},body:body?JSON.stringify(body):undefined,cache:"no-store"});const result=await response.json();if(!response.ok)throw Error(result.error||response.status);return result}
function render(r){
current=r;submissionKey=null;$("dashboard").hidden=false;$("raw").textContent=JSON.stringify(r,null,2);
const c=r.candidate||{},e=r.evidence||{},items=c.numerical_statements||[];
$("summary").textContent=c.summary||"No candidate summary";$("status").textContent=r.disposition||c.review_status||"Unknown";
$("identity").textContent="Run "+r.run_id+" · Snapshot "+r.snapshot_id+" · Revision "+r.revision;
const execution=r.execution||{};
$("executionModes").textContent="Data: "+fmt(execution.data_mode)+" · Provider: "+fmt(execution.model_mode)+" · Model: "+fmt(execution.model)+" · Memory: "+fmt(execution.memory_mode)+" · Profile: "+fmt(execution.execution_profile);
$("provenanceState").textContent=r.provenance_status==="receipt_top_level"?"Execution metadata from the hash-bound imported receipt; not independent live verification.":"Execution provenance unavailable: "+fmt(r.provenance_status)+". Analysis placeholders do not establish execution modes.";
// Host-calculated metrics are authoritative; the model-selected brief need not enumerate them.
const data={};
for(const m of (e.metrics||[])){
 if(!["comparison","target"].includes(m.period)||m.cohort!=="all_available")continue;
 if(!["canonical","raw_diagnostic"].includes(m.view))continue;
 if(!["positive_total","tested_total","positivity_pct"].includes(m.name))continue;
 if(m.availability==="available" && typeof m.value==="number" && Number.isFinite(m.value)){
   data[m.period+"_"+m.view+"_"+m.name]=m.value;
 }
}
const get=(p,v,n)=>data[p+"_"+v+"_"+n];
$("metrics").replaceChildren(metric("Canonical positives · earlier",get("comparison","canonical","positive_total")),
metric("Canonical positives · later",get("target","canonical","positive_total")),
metric("Raw positives · earlier",get("comparison","raw_diagnostic","positive_total")),
metric("Raw positives · later",get("target","raw_diagnostic","positive_total")));
tableRows("comparison",["comparison","target"].map(p=>[p,get(p,"canonical","positive_total"),get(p,"raw_diagnostic","positive_total"),get(p,"canonical","tested_total"),get(p,"canonical","positivity_pct")]));
const rows=(e.evidence_records||[]).filter(x=>x.table==="malaria_monthly").map(x=>x.record||{});
rows.sort((a,b)=>(a.period_month||"").localeCompare(b.period_month||"")||(a.facility_id||"").localeCompare(b.facility_id||"")||(a.report_version||0)-(b.report_version||0));
tableRows("versions",rows.map(x=>[x.facility_id,x.period_month,x.report_id,x.report_version,x.positive_episodes]));
tableRows("facilities",(e.matched_facility_contributions||[]).map(x=>[x.facility_id,x.comparison?.positive,x.target?.positive,x.positive_delta]));
list("limitations",c.limitations||[]);list("checks",c.next_checks||[]);
const history=r.history||[];$("history").textContent=history.length?history.map(x=>x.at+" · "+x.disposition+" · "+x.reason).join("\n"):"No review recorded";
$("submitBtn").disabled=r.disposition!==null&&r.disposition!==undefined;
$("message").textContent="Candidate loaded. Check supporting records and limitations before submitting.";
}
async function load(){try{$("message").textContent="Loading…";const r=await api("/api/runs/"+encodeURIComponent($("run").value));render(r)}catch(e){current=null;$("dashboard").hidden=true;$("message").textContent="Unable to load: "+e.message}}
async function submitReview(){try{
if(!current)throw Error("Load candidate first");
if(!$("reason").value.trim()||$("reason").value.trim().length<10)throw Error("Provide a reason of at least 10 characters");
submissionKey ||= crypto.randomUUID().replaceAll("-","");
const result=await api("/api/runs/"+encodeURIComponent(current.run_id)+"/reviews","POST",
{expected_revision:current.revision,event_key:submissionKey,disposition:$("decision").value,reason:$("reason").value});
await load();$("message").textContent="Disposition recorded: "+result.disposition+" (revision "+result.revision+").";
}catch(e){$("message").textContent="Review not recorded: "+e.message}}
$("loadBtn").addEventListener("click",load);$("submitBtn").addEventListener("click",submitReview);
</script></body></html>'''
