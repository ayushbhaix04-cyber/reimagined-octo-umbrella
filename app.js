const tg=window.Telegram.WebApp; tg.ready(); tg.expand();
const API=""; // same origin
async function api(path,method="GET",body){
 const init=tg.initData; 
 const res=await fetch(path,{method,headers:{"Content-Type":"application/json",Authorization:"tma "+init},body:body?JSON.stringify(body):undefined});
 if(!res.ok) throw new Error(await res.text()); return res.json();}
async function load(){
 const u=tg.initDataUnsafe.user||{}; document.getElementById("user").textContent=`👤 ${u.first_name||"Guest"} (@${u.username||"-"})`;
 const gs=await api("/api/giveaways"); const list=document.getElementById("list"); list.innerHTML="";
 gs.forEach(g=>{const d=document.createElement("div");d.className="card";d.innerHTML=`<b>🎁 ${g.title}</b><br>🏆 ${g.prize}<br>👥 ${g.winners} winners`;
  const b=document.createElement("button");b.textContent="Join";b.onclick=async()=>{await api(`/api/join/${g.id}`,"POST");alert("Check bot for captcha")};d.appendChild(b);list.appendChild(d);});}
load();
