'use strict';
const $=id=>document.getElementById(id);
const JUST={S:1,r:256/243,R:9/8,g:32/27,G:5/4,M:4/3,'M+':45/32,P:3/2,d:128/81,D:5/3,n:16/9,N:15/8};
const noteFrequency=n=>136.18*JUST[n.swara]*2**n.octave;
const pilot=window.pilot={audio:$('audio'),current:[],candidate:null,ready:false,voice:null,ctx:null,token:0,stats:{voicesStarted:0},mode:'recording'};
const fmt=t=>`${Math.floor(t/60)}:${(t%60).toFixed(1).padStart(4,'0')}`;
function stopVoice(){if(pilot.voice){try{pilot.voice.osc.stop()}catch{}pilot.voice.osc.disconnect();pilot.voice.gain.disconnect();pilot.voice=null;}}
function activeNote(t){const notes=pilot.mode==='current'?pilot.current:pilot.candidate.notes;let lo=0,hi=notes.length;while(lo<hi){const mid=(lo+hi)>>1;if(notes[mid].t<=t)lo=mid+1;else hi=mid;}const n=notes[lo-1];return n && t<n.t+n.dur?n:null;}
pilot.seek=t=>{stopVoice();pilot.audio.currentTime=Math.max(0,Math.min(t,pilot.audio.duration||2687.38));};
async function play(){const token=++pilot.token;try{if(pilot.mode!=='recording'){pilot.ctx ||= new AudioContext();await pilot.ctx.resume();if(pilot.ctx.state!=='running')throw Error('Audio output could not start');}if(token!==pilot.token)return;await pilot.audio.play();if(token!==pilot.token)return;$('play').textContent='Pause';}catch(e){if(token===pilot.token){pilot.audio.pause();stopVoice();$('play').textContent='Play';$('status').textContent=e.message;}}}
function pause(){pilot.token++;pilot.audio.pause();stopVoice();$('play').textContent='Play';}
$('play').onclick=()=>pilot.audio.paused?play():pause();
$('mode').onchange=async()=>{const running=!pilot.audio.paused;pause();pilot.mode=$('mode').value;pilot.audio.muted=pilot.mode!=='recording';if(running)await play();};
let scrubbing=false;
function manualSeek(t){
 const w=pilot.candidate?.windows[Number($('phrase').value)];
 if(w && (t<w.start || t>=w.end))$('loop').checked=false;
 pilot.seek(t);
}
$('seek').onpointerdown=()=>{scrubbing=true;};
window.addEventListener('pointerup',()=>{scrubbing=false;});
$('seek').onpointercancel=()=>{scrubbing=false;};
$('seek').oninput=()=>manualSeek(Number($('seek').value));
$('seek').onchange=()=>{manualSeek(Number($('seek').value));scrubbing=false;};
$('back').onclick=()=>manualSeek(pilot.audio.currentTime-3);
$('phrase').onchange=()=>pilot.seek(pilot.candidate.windows[Number($('phrase').value)].start);
$('volume').oninput=()=>{pilot.audio.volume=Number($('volume').value);stopVoice();};
pilot.audio.onpause=()=>{stopVoice();$('play').textContent='Play';};
pilot.audio.onended=()=>{const w=pilot.candidate.windows[Number($('phrase').value)];pilot.seek($('loop').checked?w.start:0);play();};
function tick(){if(pilot.ready){let t=pilot.audio.currentTime;const w=pilot.candidate.windows[Number($('phrase').value)];if(!pilot.audio.paused && $('loop').checked && (t>=w.end || t<w.start)){pilot.seek(w.start);t=w.start;}
if(!scrubbing && !pilot.audio.seeking)$('seek').value=t;$('clock').textContent=fmt(t);const n=pilot.mode==='recording'?null:activeNote(t);
if(pilot.mode==='recording'){$('status').textContent='Original recording';stopVoice();}
else{$('status').textContent=n?`${n.label} · ${n.hz.toFixed(1)} Hz`:(pilot.mode==='candidate'?'Untranscribed — not singer silence':'No current note');
if(pilot.audio.paused || !n)stopVoice();else if(!pilot.voice || pilot.voice.note!==n){stopVoice();const c=pilot.ctx;if(c?.state==='running'){const now=c.currentTime,d=n.t+n.dur-t;const osc=c.createOscillator(),gain=c.createGain();osc.type='sine';osc.frequency.setValueAtTime(noteFrequency(n),now);const amp=Number($('volume').value)*.2;gain.gain.setValueAtTime(0,now);gain.gain.linearRampToValueAtTime(amp,now+Math.min(.008,d/3));gain.gain.setValueAtTime(amp,now+Math.max(d-.012,d/2));gain.gain.linearRampToValueAtTime(0,now+d);osc.connect(gain).connect(c.destination);osc.start(now);osc.stop(now+d);pilot.voice={osc,gain,note:n};pilot.stats.voicesStarted++;}}}}
requestAnimationFrame(tick);}
(async()=>{try{const responses=await Promise.all([fetch('../../data/pt-jasraj-side-a/performance.json'),fetch('candidate.json')]);if(responses.some(r=>!r.ok))throw Error('Could not load notation');const [current,candidate]=await Promise.all(responses.map(r=>r.json()));pilot.current=current.notes;pilot.candidate=candidate;candidate.windows.forEach((w,i)=>{const option=document.createElement('option');option.value=i;option.textContent=`${fmt(w.start)}–${fmt(w.end)} · ${w.title}`;$('phrase').append(option);});if(pilot.audio.readyState<1)await new Promise((resolve,reject)=>{pilot.audio.addEventListener('loadedmetadata',resolve,{once:true});pilot.audio.addEventListener('error',()=>reject(Error('Recording unavailable')),{once:true});});$('seek').max=pilot.audio.duration;pilot.audio.volume=.65;pilot.seek(candidate.windows[0].start);pilot.ready=true;$('play').disabled=false;tick();}catch(e){$('status').textContent=e.message;console.error(e);}})();
