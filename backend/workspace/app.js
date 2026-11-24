"use strict";
const $=id=>document.getElementById(id);
let token="",org="",page="overview",offset=0,epoch=0,busy=false;
const names={overview:"Overview",attendance:"Live attendance",employees:"Employees",devices:"Biometric devices",reports:"Reports & exports"};
const day=new Intl.DateTimeFormat("en-CA",{timeZone:"Africa/Kampala",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(new Date());
const part=k=>day.find(p=>p.type===k).value;
$("start").value=$("end").value=part("year")+"-"+part("month")+"-"+part("day");
function range(){
 const a=new Date($("start").value+"T00:00:00+03:00"),b=new Date($("end").value+"T00:00:00+03:00");
 b.setUTCDate(b.getUTCDate()+1);
 if(!Number.isFinite(+a)||!Number.isFinite(+b)||b<=a||b-a>31*86400000)throw Error("Choose a valid date range of up to 31 days.");
 return new URLSearchParams({start:a.toISOString(),end:b.toISOString()});
}
async function api(path){
 const r=await fetch("/api/workspace/"+encodeURIComponent(org)+"/"+path,{headers:{Authorization:"Bearer "+token},cache:"no-store"});
 if(!r.ok)throw Error(r.status===401?"Session invalid or expired. Sign out and reconnect.":r.status===403?"Workspace access denied.":"Request failed ("+r.status+").");
 return r;
}
function node(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n}
function table(rows,cols){const box=node("div",undefined,"scroll"),t=node("table"),head=node("tr");cols.forEach(([key,label])=>head.append(node("th",label)));t.append(head);
 for(const row of rows){const tr=node("tr");for(const [key] of cols)tr.append(node("td",row[key]===null||row[key]===undefined?"—":String(row[key])));t.append(tr)}
 box.append(t);return box}
async function load(){
 if(!token||busy)return;busy=true;const current=++epoch;const view=page;$("error").textContent="";$("status").textContent="Loading…";
 try{
 const path=view==="overview"?"overview":view==="employees"?"employees?limit=100&offset="+offset:view==="devices"?"devices":"attendance?"+range()+"&limit=100&offset="+offset;
 const data=await (await api(path)).json();if(current!==epoch)return;
 const content=$("content");content.replaceChildren();
 if(view==="overview"){const grid=node("div",undefined,"metrics");for(const [key,label] of [["active_employees","Active employees"],["devices","Registered devices"],["recently_seen","Recently connected"],["received_24h","Punches received · 24h"]]){const card=node("div",label,"metric");card.append(node("strong",String(data[key])));grid.append(card)}content.append(grid)}
 else{const cols=view==="employees"?[["employee_number","Employee no."],["full_name","Employee"],["branch_name","Branch"],["department_name","Department"],["active","Active"]]:view==="devices"?[["label","Device"],["serial_number","Serial"],["branch_name","Branch"],["connection_status","Connection"],["last_seen_at","Last seen (UTC)"]]:[["occurred_at","Timestamp (UTC)"],["full_name","Employee"],["device_pin","Scanner PIN"],["branch","Branch"],["device","Device"],["interpretation","Punch"],["processing_status","Status"]];
 content.append(data.length?table(data,cols):node("p","No records available."));$("next").disabled=data.length<100||view==="devices";$("prev").disabled=offset===0}
 $("status").textContent="Updated "+new Date().toLocaleTimeString()+" · Real records only";
 }catch(e){if(current===epoch){$("content").replaceChildren();$("status").textContent="Unavailable";$("error").textContent=e.message}}
 finally{busy=false;if(current!==epoch&&token)load()}
}
function select(view){page=view;offset=0;epoch++;$("content").replaceChildren();$("title").textContent=names[view];$("filters").hidden=view==="overview";for(const id of ["start","end","export"])$(id).closest(id==="export"?"button":"label").hidden=!["attendance","reports"].includes(view);for(const id of ["prev","next"])$(id).hidden=view==="devices";document.querySelectorAll("[data-page]").forEach(b=>b.classList.toggle("active",b.dataset.page===view));load()}
$("loginform").addEventListener("submit",async e=>{e.preventDefault();org=$("org").value.trim();token=$("token").value.trim();$("token").value="";$("error").textContent="";
 try{await api("overview");$("login").hidden=true;$("workspace").hidden=false;$("nav").hidden=false;$("logout").hidden=false;select("overview")}catch(e){token="";$("error").textContent=e.message}});
$("logout").onclick=()=>{token="";org="";epoch++;$("content").replaceChildren();$("workspace").hidden=true;$("nav").hidden=true;$("logout").hidden=true;$("login").hidden=false;$("error").textContent=""};
document.querySelectorAll("[data-page]").forEach(b=>b.onclick=()=>select(b.dataset.page));
$("refresh").onclick=()=>{offset=0;load()};$("prev").onclick=()=>{offset=Math.max(0,offset-100);load()};$("next").onclick=()=>{offset+=100;load()};
$("export").onclick=async()=>{try{const blob=await(await api("report.csv?"+range())).blob();const url=URL.createObjectURL(blob),a=node("a");a.href=url;a.download="attendance.csv";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(e){$("error").textContent=e.message}};
setInterval(()=>{if(token&&page==="attendance"&&offset===0&&!document.hidden)load()},15000);
