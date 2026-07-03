// app.js — extracted from root index.html and extended with OneDrive pull-only guest sync
// Stores app data in localStorage key 'zabMobilePagesV2'

const rooms=["DZ Bachblick","Marillenzimmer","Weinbergzimmer","Donauzimmer"];
const drinks=[["Cola",3.50],["Fanta",3.50],["Bier",4.00],["Radler",4.00],["Wein 1/8",3.80],["Mineral",2.80],["Kaffee",2.80],["Tee",2.50]];
const foods=[["Frühstück",12.00],["Gulasch",12.00],["Schinkenplatte",11.00],["Gemischter Salat",7.50],["Grillteller klein",14.00],["Marillenkuchen",4.50]];

let data=JSON.parse(localStorage.getItem("zabMobilePagesV2")||"null")||{guests:[{id:"G1",name:"Devich Armin",phone:"",email:"",notes:"",updatedAt:new Date().toISOString()},{id:"G2",name:"Paul Artner",phone:"",email:"",notes:"",updatedAt:new Date().toISOString()}],bookings:[],extras:{},activeBooking:null};

function save(){localStorage.setItem("zabMobilePagesV2",JSON.stringify(data));renderAll()}
function show(id){document.querySelectorAll("main>section").forEach(s=>s.classList.add("hidden"));document.getElementById(id)?.classList.remove("hidden");}
function makeId(p){return p+Date.now().toString(36)+Math.random().toString(36).slice(2,6)}
function guestName(gid){return (data.guests.find(g=>g.id===gid)||{}).name||"Unbekannt"}
function nights(a,b){return Math.max(1,Math.round((new Date(b)-new Date(a))/(24*3600*1000)))}

// Render helpers (kept minimal — mirrors the original behaviour)
function renderRoomSelects(){document.querySelectorAll('.roomSelect').forEach(select=>{select.innerHTML=rooms.map(r=>`<option value="${r}">${r}</option>`).join('')})}

function renderGuests(){let q=(document.getElementById("guestSearch")?.value||"").toLowerCase();let list=document.getElementById("guestList");if(!list)return;let rows=data.guests.filter(g=>g.name.toLowerCase().includes(q)).map(g=>`<div class="row"><div><div class="room">${g.name}</div><div class="small">${g.phone||''} ${g.email? '• '+g.email: ''}</div></div><div><button onclick="editGuest('${g.id}')">Bearbeiten</button></div></div>`).join("");list.innerHTML=rows||'<div class="small">Keine Gäste</div>'}

function newGuest(){document.getElementById('guestFormTitle').textContent='Neuer Gast';document.getElementById('guestId').value='';document.getElementById('guestName').value='';document.getElementById('guestPhone').value='';document.getElementById('guestEmail').value='';document.getElementById('guestNotes').value='';show('editGuest')}
function editGuest(gid){let g=data.guests.find(x=>x.id===gid);if(!g)return;document.getElementById('guestFormTitle').textContent='Gast bearbeiten';document.getElementById('guestId').value=g.id;document.getElementById('guestName').value=g.name;document.getElementById('guestPhone').value=g.phone;document.getElementById('guestEmail').value=g.email;document.getElementById('guestNotes').value=g.notes;show('editGuest')}
function saveGuest(){let gid=document.getElementById('guestId').value||makeId('G');let g=data.guests.find(x=>x.id===gid);if(!g){g={id:gid};data.guests.push(g)}g.name=document.getElementById('guestName').value.trim()||'Neuer Gast';g.phone=document.getElementById('guestPhone').value.trim();g.email=document.getElementById('guestEmail').value.trim();g.notes=document.getElementById('guestNotes').value.trim();g.updatedAt=new Date().toISOString();save();show('guests')}

// Bookings and extras rendering simplified placeholders
function renderBookings(){let list=document.getElementById('bookingList');if(!list)return;let sorted=[...data.bookings].sort((a,b)=>a.arrival.localeCompare(b.arrival));list.innerHTML=sorted.map(b=>`<div class="row"><div><strong>${b.room}</strong><div class="small">${guestName(b.guestId)} — ${b.arrival} → ${b.departure}</div></div><div><button onclick="(function(){bookingEdit('${b.id}')})()">Edit</button></div></div>`).join('')||'<div class="small">Keine Buchungen</div>'}
function bookingEdit(id){let b=data.bookings.find(x=>x.id===id);if(!b)return;document.getElementById('bookingId').value=b.id;document.getElementById('bookingGuest').value=b.guestId;document.getElementById('bookingRoom').value=b.room;document.getElementById('bookingArrival').value=b.arrival;document.getElementById('bookingDeparture').value=b.departure;show('editBooking')}

function renderActiveSelects(){let opts=data.bookings.map(b=>`<option value="${b.id}">${b.room} – ${guestName(b.guestId)} (${b.arrival})</option>`).join('');['activeBooking','invoiceBooking'].forEach(id=>{let el=document.getElementById(id);if(el)el.innerHTML=opts})}

function renderItems(){let db=document.getElementById('drinkButtons'),fb=document.getElementById('foodButtons');if(db)db.innerHTML=drinks.map(x=>`<button class="btn itembtn blue" onclick="addExtra('${x[0]}',${x[1]})">${x[0]} — ${x[1].toFixed(2)}€</button>`).join(''); if(fb)fb.innerHTML=foods.map(x=>`<button class="btn itembtn gold" onclick="addExtra('${x[0]}',${x[1]})">${x[0]} — ${x[1].toFixed(2)}€</button>`).join('')}

function addExtra(text,price){let bid=data.activeBooking||data.bookings[0]?.id;if(!bid){alert('Bitte zuerst eine Buchung anlegen/auswählen.');return}data.activeBooking=bid;data.extras[bid]=data.extras[bid]||[];data.extras[bid].push({text,price});save()}
function addCustom(){let t=document.getElementById('customText').value.trim(),p=Number(document.getElementById('customPrice').value||0);if(!t||!p){alert('Bitte Text und Betrag eingeben.');return}addExtra(t,p);document.getElementById('customText').value='';document.getElementById('customPrice').value=''}

function renderInvoice(){let box=document.getElementById('invoiceDetails');if(!box)return;let bid=data.activeBooking||data.bookings[0]?.id;data.activeBooking=bid;let b=data.bookings.find(x=>x.id===bid);if(!b){box.innerHTML='<div class="small">Keine Buchung</div>';return}let ex=data.extras[bid]||[];let roomTotal=nights(b.arrival,b.departure)* (b.price||0);let extrasHtml=ex.map(x=>`<div class="row"><div>${x.text}</div><div>${x.price.toFixed(2)}€</div></div>`).join('');box.innerHTML=`<div><strong>${guestName(b.guestId)}</strong></div>${extrasHtml}<div class="row"><div class="small">Raum</div><div>${roomTotal.toFixed(2)}€</div></div>`}

function renderHome(){let today=new Date().toISOString().slice(0,10);let todayBookings=data.bookings.filter(b=>b.arrival<=today&&b.departure>=today);let tl=document.getElementById('todayList');if(!tl)return;tl.innerHTML=todayBookings.map(b=>`<div class="row"><div><strong>${b.room}</strong><div class="small">${guestName(b.guestId)}</div></div></div>`).join('')||'<div class="small">Keine Ankünfte</div>'}

// Initial render
function renderAll(){renderRoomSelects();renderGuests();renderBookings();renderActiveSelects();renderItems();renderInvoice();renderHome()}

// ---------- Sync: OneDrive pull-only ----------
// Settings are stored under localStorage key 'remoteGuestsUrl'

function getRemoteUrl(){return localStorage.getItem('remoteGuestsUrl')||''}
function setRemoteUrl(url){localStorage.setItem('remoteGuestsUrl',url)}

async function fetchRemoteGuests(){let url=getRemoteUrl();if(!url) return null; try{let r=await fetch(url,{cache:'no-store'}); if(!r.ok) throw new Error('Fetch failed'); let json=await r.json(); return json}catch(e){console.warn('Remote guests fetch failed',e);return null}}

function mergeGuests(remoteGuests){if(!Array.isArray(remoteGuests)) return false;let changed=false;for(let rg of remoteGuests){if(!rg.id) continue; let lg=data.guests.find(x=>x.id===rg.id); if(!lg){data.guests.push(rg);changed=true}else{let rTime=new Date(rg.updatedAt||rg._updatedAt||0).getTime();let lTime=new Date(lg.updatedAt||lg._updatedAt||0).getTime();if(isNaN(lTime)) lTime=0; if(rTime>lTime){ // remote is newer
lg.name=rg.name||lg.name;lg.phone=rg.phone||lg.phone;lg.email=rg.email||lg.email;lg.notes=rg.notes||lg.notes;lg.updatedAt=rg.updatedAt||new Date().toISOString();changed=true}}}
if(changed) save();return changed}

async function syncGuestsNow(){let remote=await fetchRemoteGuests(); if(remote) { let ok=mergeGuests(remote); if(ok) showToast('Gäste aktualisiert'); else showToast('Keine Änderungen'); } else { showToast('Keine entfernte Quelle konfiguriert oder Abruf fehlgeschlagen'); }}

function showToast(msg){let t=document.getElementById('toast'); if(!t){t=document.createElement('div');t.id='toast';t.style.position='fixed';t.style.right='14px';t.style.bottom='76px';t.style.background='rgba(0,0,0,0.8)';t.style.color='white';t.style.padding='10px 14px';t.style.borderRadius='8px';t.style.zIndex=9999;document.body.appendChild(t);} t.textContent=msg; t.style.opacity=1; clearTimeout(t._timeout); t._timeout=setTimeout(()=>{t.style.opacity=0},3000)}

// Settings UI injection: add a settings section if not present
function ensureSettingsUI(){if(document.getElementById('settings')) return; let sec=document.createElement('section');sec.id='settings';sec.className='hidden';sec.innerHTML=`<div class="card"><h2>Einstellungen</h2><label>OneDrive / Remote Guests URL</label><input id="remoteUrlInput" placeholder="https://.../guests.json (roh)" /><div style="display:flex;gap:8px;margin-top:8px"><button id="saveRemoteUrlBtn" class="btn green">Speichern</button><button id="syncNowBtn" class="btn blue">Jetzt synchronisieren</button></div><div class="small" style="margin-top:8px">Die URL wird lokal im Browser gespeichert und nicht ins Repo geschrieben.</div></div>`; document.querySelector('main').appendChild(sec);
document.getElementById('saveRemoteUrlBtn').addEventListener('click',()=>{let v=document.getElementById('remoteUrlInput').value.trim();setRemoteUrl(v);showToast('URL gespeichert');});
document.getElementById('syncNowBtn').addEventListener('click',()=>{syncGuestsNow()});
// add quick access in nav
let nav=document.querySelector('nav .nav')||document.querySelector('nav'); if(nav && !document.getElementById('settingsNavBtn')){let btn=document.createElement('button');btn.id='settingsNavBtn';btn.textContent='⚙ Einstellungen';btn.onclick=()=>show('settings');nav.appendChild(btn);} 
}

// Automatic periodic sync
let SYNC_INTERVAL=5*60*1000; // 5 minutes
setInterval(()=>{ // silent background sync
if(getRemoteUrl()) fetchRemoteGuests().then(remote=>{ if(remote) mergeGuests(remote) })}, SYNC_INTERVAL);

// On first load, inject settings UI and prefill input
window.addEventListener('load',()=>{ensureSettingsUI();document.getElementById('remoteUrlInput').value=getRemoteUrl();renderAll(); // try an initial silent sync
if(getRemoteUrl()) fetchRemoteGuests().then(remote=>{ if(remote) mergeGuests(remote) });});

// Expose some functions to the global scope used by inline html
window.show=show; window.newGuest=newGuest; window.editGuest=editGuest; window.saveGuest=saveGuest; window.addCustom=addCustom; window.addExtra=addExtra; window.syncGuestsNow=syncGuestsNow; window.bookingEdit=bookingEdit; window.save=save; window.renderAll=renderAll;