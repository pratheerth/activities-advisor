'use strict';
const $=s=>document.querySelector(s);
let conversationId=null,busy=false,toolRow=null,hasPlan=false;
const text=(tag,value,className)=>{const el=document.createElement(tag);el.textContent=value;if(className)el.className=className;return el;};
function error(message){$('#error').textContent=message;$('#error').hidden=!message;}
function setBusy(value){busy=value;$('#send').disabled=value;$('#new-trip').disabled=value;document.querySelectorAll('.example').forEach(b=>b.disabled=value);$('#send').textContent=value?'Working…':conversationId?'Revise my plan ↗':'Plan my day ↗';}
function bubble(role,message){const el=text('div','','bubble '+role);el.append(text('span',role==='user'?'YOU':'ACTIVITIES ADVISOR','who'),text('p',message));$('#chat').append(el);$('#chat').scrollTop=$('#chat').scrollHeight;}
function link(source,label){const a=text('a',label);try{const url=new URL(source.url);if(url.protocol!=='https:')return text('span',label);a.href=url.href;a.target='_blank';a.rel='noopener noreferrer';}catch{return text('span',label);}return a;}
function renderPlan(result){
 const plan=result.itinerary;if(!plan)return;
 hasPlan=true;$('#plan').hidden=false;$('#empty-plan').hidden=true;$('#plan-heading').textContent=plan.title;$('#plan-state').hidden=false;$('#plan-state').textContent=result.status==='limited'?'Provisional itinerary':'Draft itinerary';
 const weather=$('#weather');weather.replaceChildren(text('strong',plan.location+' · '+plan.date),text('p',plan.weather_summary));weather.hidden=false;
 if(result.weather?.slots){const slots=result.weather.slots;const temps=slots.map(s=>s.temperature_c).filter(Number.isFinite);if(temps.length)weather.append(text('p',Math.round(Math.min(...temps))+'–'+Math.round(Math.max(...temps))+'°C across returned forecast intervals · '+(result.weather.provider||'OpenWeather')));}
 const sources=Object.fromEntries(result.sources.map(s=>[s.id,s]));$('#activities').replaceChildren();
 plan.activities.forEach((a,i)=>{const card=text('article','','activity-card');card.append(text('span',String(i+1).padStart(2,'0'),'number'),text('span',a.time,'time'),text('h3',a.title),text('p',a.details),text('p',a.cost_note,'cost'));const tags=text('div','','source-tags');a.source_ids.forEach(id=>{if(sources[id])tags.append(link(sources[id],id+' ↗'));});card.append(tags);$('#activities').append(card);});
 const notes=text('ul','');plan.caveats.forEach(c=>notes.append(text('li',c)));$('#caveats').replaceChildren(notes);$('#sources').replaceChildren();result.sources.forEach(s=>{const li=text('li','');li.append(link(s,s.id+' · '+s.title+' ↗'));$('#sources').append(li);});
}
function handle(event){
 if(event.type==='started'){conversationId=event.conversation_id;$('#run-id').textContent=event.run_id;$('#run-details').hidden=false;$('#trace-link').href='/api/runs/'+encodeURIComponent(event.run_id);$('#trace-link').hidden=true;}
 if(event.type==='thinking')$('#run-status').textContent='Considering the next step…';
 if(event.type==='tool_started'){const row=text('li','');row.append(text('span','↻ '+event.label));const detail=document.createElement('details');detail.append(text('summary','Arguments'),text('pre',JSON.stringify(event.arguments,null,2)));row.append(detail);$('#activity').append(row);toolRow=row;$('#run-status').textContent='Calling tool…';}
 if(event.type==='tool_finished'&&toolRow){toolRow.firstChild.textContent=(event.ok?'✓ ':'! ')+event.label;toolRow.firstChild.className=event.ok?'done':'failed';const detail=document.createElement('details');detail.append(text('summary','Tool result'),text('pre',JSON.stringify(event.result,null,2)));toolRow.append(detail);toolRow=null;}
 if(event.type==='run_error')$('#run-status').textContent='Request interrupted';
 if(event.type==='result'){bubble('assistant',event.message);renderPlan(event);$('#run-status').textContent=event.status==='error'?'Could not finish':event.status==='needs_information'?'Waiting for your reply':event.status==='limited'?'Finished with limitations':'Finished';$('#trace-link').hidden=false;if(!event.itinerary&&hasPlan)$('#plan-state').textContent='Previous itinerary';}
}
$('#composer').onsubmit=async e=>{
 e.preventDefault();if(busy)return;const message=$('#message').value.trim();if(!message)return;setBusy(true);error('');$('#welcome').hidden=true;bubble('user',message);$('#message').value='';$('#activity').replaceChildren();$('#run-details').hidden=true;toolRow=null;if(hasPlan)$('#plan-state').textContent='Previous itinerary · updating';let finalReceived=false;
 try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,conversation_id:conversationId})});if(!r.ok){const d=await r.json();throw new Error(typeof d.detail==='string'?d.detail:'Please check the request and try again.');}
 const reader=r.body.getReader(),decoder=new TextDecoder();let buffer='';while(true){const {done,value}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});let index;while((index=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,index);buffer=buffer.slice(index+1);if(line.trim()){const event=JSON.parse(line);handle(event);if(event.type==='result')finalReceived=true;}}if(done)break;}if(!finalReceived)throw new Error('The connection ended before the plan finished. Please try again.');
 }catch(err){error(err.message);$('#run-status').textContent='Connection or request failed';if(hasPlan)$('#plan-state').textContent='Previous itinerary';}finally{setBusy(false);$('#message').focus();}
};
$('#new-trip').onclick=()=>{if(busy)return;conversationId=null;hasPlan=false;$('#chat').querySelectorAll('.bubble').forEach(e=>e.remove());$('#welcome').hidden=false;$('#plan').hidden=true;$('#empty-plan').hidden=false;$('#plan-state').hidden=true;$('#plan-heading').textContent='A plan worth stepping out for.';$('#activity').replaceChildren(text('li','No tools called yet.','placeholder'));$('#run-status').textContent='Ready when you are';$('#run-details').hidden=true;$('#message').value='';error('');setBusy(false);};
document.querySelectorAll('.example').forEach(button=>button.onclick=()=>{$('#message').value=button.dataset.request;$('#message').focus();});
$('#message').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('#composer').requestSubmit();}});
fetch('/api/config').then(r=>r.json()).then(c=>{$('#mode').textContent=c.mode==='live'?'Live tools':'Offline demo';$('#demo-banner').hidden=c.mode!=='demo';}).catch(()=>error('Cannot reach the server. Check that it is running.'));
