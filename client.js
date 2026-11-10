"use strict";
const $ = s => document.querySelector(s);
let ws=null, appList=[], selected=null, connectTimer=null, stopped=true, ready=false;
let remote={width:1280,height:800}, phone=false, blobURL=null, sentFrames=0, receivedBytes=0, lastTouch=null;
const presets={eco:{fps:5,quality:35},balanced:{fps:10,quality:55},smooth:{fps:20,quality:70}};
function toast(text){$('#toast').textContent=text;$('#toast').classList.add('show');clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').classList.remove('show'),5000)}
function send(data){if(ws?.readyState===WebSocket.OPEN){ws.send(JSON.stringify(data));return true}return false}
function status(text,online=false){$('#connectionLabel').textContent=text;$('#statusDot').classList.toggle('online',online)}
function home(){ $('#home').hidden=false;$('#workspace').hidden=true;$('#homeBtn').classList.add('selected') }
function loading(text,retry=false){$('#screen').hidden=true;$('#loading').hidden=false;$('#loadingText').textContent=text;$('#reconnectBtn').hidden=!retry;$('#loading .loader').hidden=retry}
function disconnect(){stopped=true;ready=false;clearTimeout(connectTimer);if(ws){ws.onclose=null;ws.close();ws=null}status('Standby');home()}
function openApp(id){const item=appList.find(a=>a.id===id);if(!item)return;selected=id;$('#home').hidden=true;$('#workspace').hidden=false;$('#homeBtn').classList.remove('selected');$('#address').value=item.url;document.querySelectorAll('#dock button').forEach(b=>b.classList.toggle('selected',b.dataset.app===id));
if(ready && ws?.readyState===WebSocket.OPEN){send({type:'open',app:id});return}connect()}
function connect(){if(ws) {ws.onclose=null;ws.close()}stopped=false;ready=false;loading('Starting your cloud browser…');status('Connecting');const socket=new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/stream`);ws=socket;socket.binaryType='arraybuffer';
connectTimer=setTimeout(()=>{if(!ready&&ws===socket){toast('Browser startup is taking longer than expected. Check server logs if it continues.')}},45000);
socket.onopen=()=>status('Starting');socket.onmessage=async event=>{if(ws!==socket)return;
if(event.data instanceof ArrayBuffer){receivedBytes+=event.data.byteLength;const img=$('#screen');const old=blobURL;blobURL=URL.createObjectURL(new Blob([event.data],{type:'image/jpeg'}));img.src=blobURL;try{await img.decode();if(ws!==socket)return;img.hidden=false;$('#loading').hidden=true;sentFrames++}catch(e){}finally{if(old)URL.revokeObjectURL(old);if(ws===socket)send({type:'ack'})}return}
let msg;try{msg=JSON.parse(event.data)}catch(e){return}
if(msg.type==='ready'){clearTimeout(connectTimer);ready=true;status('Connected',true);remote={width:msg.width,height:msg.height};send({type:'quality',...presets[$('#preset').value]});if(phone)send({type:'viewport',width:430,height:880});if(selected)send({type:'open',app:selected})}
else if(msg.type==='resize'){remote={width:msg.width,height:msg.height}}
else if(msg.type==='meta'){$('#pageTitle').textContent=msg.title||'Cloud browser';if(document.activeElement!==$('#address'))$('#address').value=msg.url;$('#stats').textContent=`${(receivedBytes/1048576).toFixed(1)} MB received · No audio`}
else if(msg.type==='status'){$('#loadingText').textContent=msg.message}
else if(msg.type==='error'||msg.type==='notice'){toast(msg.message);if(msg.type==='error')loading(msg.message,true)}};
socket.onclose=()=>{if(ws!==socket)return;ready=false;status('Disconnected');clearTimeout(connectTimer);if(!stopped)loading('Cloud browser disconnected',true)};
socket.onerror=()=>{if(ws===socket)toast('Connection failed. Use HTTPS and check that your host supports WebSockets.')};}
function coords(e){const r=$('#screen').getBoundingClientRect();if(!r.width||!r.height)return{x:0,y:0};return{x:(e.clientX-r.left)*remote.width/r.width,y:(e.clientY-r.top)*remote.height/r.height}}
function drawApps(filter=''){const grid=$('#appGrid');grid.replaceChildren();for(const a of appList.filter(a=>a.name.toLowerCase().includes(filter.toLowerCase()))){const b=document.createElement('button');b.className='app-card';b.style.setProperty('--app-color',a.color);const icon=document.createElement('span');icon.className='app-icon';icon.textContent=a.glyph;const arrow=document.createElement('span');arrow.className='card-arrow';arrow.textContent='↗';const name=document.createElement('h3');name.textContent=a.name;const tag=document.createElement('p');tag.textContent=a.tag;b.append(icon,arrow,name,tag);b.addEventListener('click',()=>openApp(a.id));grid.append(b)}}
async function boot(){try{const res=await fetch('/api/apps');if(!res.ok){location.href='/login';return}appList=(await res.json()).apps;drawApps();for(const a of appList.slice(0,6)){const b=document.createElement('button');b.className='rail-btn';b.title=a.name;b.textContent=a.glyph;b.style.color=a.color;b.dataset.app=a.id;b.onclick=()=>openApp(a.id);$('#dock').append(b)}}catch(e){toast('Could not load apps. Reload the page.')}}
$('#homeBtn').onclick=home;$('#disconnectBtn').onclick=disconnect;$('#reconnectBtn').onclick=connect;
$('#searchApps').oninput=e=>drawApps(e.target.value);
$('#urlForm').onsubmit=e=>{e.preventDefault();send({type:'open',url:$('#address').value})};
$('#backBtn').onclick=()=>send({type:'back'});$('#forwardBtn').onclick=()=>send({type:'forward'});$('#reloadBtn').onclick=()=>send({type:'reload'});
$('#mobileBtn').onclick=()=>{phone=!phone;send({type:'viewport',width:phone?430:1280,height:phone?880:800});toast(phone?'Phone viewport enabled':'Desktop viewport enabled')};
$('#shortsBtn').onclick=()=>send({type:'scroll',dy:remote.height*.85});
$('#settingsBtn').onclick=$('#settingsInline').onclick=()=>$('#settings').showModal();
$('#preset').value=localStorage.getItem('liquid-preset')||'balanced';if(!presets[$('#preset').value])$('#preset').value='balanced';
$('#preset').onchange=()=>{localStorage.setItem('liquid-preset',$('#preset').value);send({type:'quality',...presets[$('#preset').value]})};
$('#theme').value=localStorage.getItem('liquid-theme')||'dark';document.body.classList.toggle('light',$('#theme').value==='light');
$('#theme').onchange=()=>{document.body.classList.toggle('light',$('#theme').value==='light');localStorage.setItem('liquid-theme',$('#theme').value)};
$('#fullscreenBtn').onclick=()=>{const promise=document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen?.();promise?.catch(()=>toast('Fullscreen is unavailable on this browser.'))};
$('#textBtn').onclick=()=>{$('#textDialog').showModal();$('#textInput').focus()};$('#closeText').onclick=()=>{$('#textDialog').close();$('#textInput').value=''};
$('#textForm').onsubmit=e=>{e.preventDefault();if(send({type:'text',text:$('#textInput').value})){$('#textInput').value='';$('#textDialog').close();$('#stage').focus()}else toast('Connect to a cloud browser first.')};
$('#resetBtn').onclick=()=>{if(!ready){toast('Open an app first, then erase the cloud profile.');return}$('#settings').close();$('#resetDialog').showModal()};
$('#cancelReset').onclick=()=>$('#resetDialog').close();$('#confirmReset').onclick=()=>{$('#resetDialog').close();send({type:'reset'});toast('Profile erase requested. Wait for disconnect before reconnecting.')};
$('#logoutForm').onsubmit=()=>{stopped=true;if(ws)ws.close()};
for(const b of document.querySelectorAll('[data-key]'))b.onclick=()=>{send({type:'key',key:b.dataset.key});$('#stage').focus()};
$('#screen').addEventListener('click',e=>{if(e.pointerType==='touch')return;$('#stage').focus();send({type:'click',...coords(e)})});
$('#stage').addEventListener('wheel',e=>{if(!ready)return;e.preventDefault();send({type:'scroll',dx:e.deltaX,dy:e.deltaY,...coords(e)})},{passive:false});
$('#stage').addEventListener('keydown',e=>{if(!ready||e.isComposing)return;let key=e.key;const allowed=['Enter','Backspace','Delete','Tab','Escape','ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Home','End','PageDown','PageUp'];if((e.ctrlKey||e.metaKey)&&key.toLowerCase()==='a'){e.preventDefault();send({type:'key',key:e.metaKey?'Meta+a':'Control+a'})}else if(allowed.includes(key)){e.preventDefault();if(key==='Tab'&&e.shiftKey)key='Shift+Tab';send({type:'key',key})}else if(key.length===1&&!e.ctrlKey&&!e.metaKey&&!e.altKey){e.preventDefault();send({type:'text',text:key})}});
$('#stage').addEventListener('paste',e=>{if(!ready)return;e.preventDefault();send({type:'text',text:e.clipboardData.getData('text/plain')})});
$('#screen').addEventListener('touchstart',e=>{e.preventDefault();const t=e.changedTouches[0];lastTouch={x:t.clientX,y:t.clientY,time:Date.now()}},{passive:false});
$('#screen').addEventListener('touchend',e=>{e.preventDefault();if(!lastTouch)return;const t=e.changedTouches[0],dx=lastTouch.x-t.clientX,dy=lastTouch.y-t.clientY;if(Math.abs(dy)>20||Math.abs(dx)>20){send({type:'scroll',dx:dx*2,dy:dy*2,...coords(t)})}else if(Date.now()-lastTouch.time<800){send({type:'click',...coords(t)})}lastTouch=null},{passive:false});
function tick(){$('#clock').textContent=new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'})}tick();setInterval(tick,10000);window.addEventListener('beforeunload',()=>ws?.close());boot();
