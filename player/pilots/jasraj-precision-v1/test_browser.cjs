const {chromium}=require('./test-tools/node_modules/playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--autoplay-policy=no-user-gesture-required']});
 const page=await browser.newPage(); const errors=[]; page.on('pageerror',e=>errors.push(e.message));
 try {
 await page.goto('http://127.0.0.1:8765/pilots/jasraj-precision-v1/index.html');
 await page.waitForFunction(()=>window.pilot?.ready,{timeout:10000});
 const loaded=await page.evaluate(()=>({current:pilot.current.length,candidate:pilot.candidate.notes.length})); assert.equal(loaded.current,11921);assert(loaded.candidate>0);
 await page.click('#play'); await page.waitForFunction(()=>pilot.audio.currentTime>5.1);
 let t=await page.evaluate(()=>pilot.audio.currentTime); assert(t>5.1);
 await page.selectOption('#mode','candidate'); await page.waitForTimeout(150);
 let t2=await page.evaluate(()=>pilot.audio.currentTime); assert(t2>=t && t2<t+1);assert(await page.evaluate(()=>pilot.audio.muted));
 const n=await page.evaluate(()=>pilot.candidate.notes.find(n=>n.dur>=.15));assert(n);
 await page.evaluate(n=>pilot.seek(n.t+.02),n); await page.waitForTimeout(45);
 assert(await page.evaluate(()=>pilot.stats.voicesStarted>0));
 const pitch=await page.evaluate(()=>{const v=pilot.voice;const ratios={S:1,r:256/243,R:9/8,g:32/27,G:5/4,M:4/3,'M+':45/32,P:3/2,d:128/81,D:5/3,n:16/9,N:15/8};return {actual:v.osc.frequency.value,expected:136.18*ratios[v.note.swara]*2**v.note.octave};});assert(Math.abs(pitch.actual-pitch.expected)<.001,'Synth must render the labelled swara, identically for both note tracks');
 await page.click('#play'); assert(await page.evaluate(()=>pilot.audio.paused)); assert.equal(await page.evaluate(()=>pilot.voice),null);
 await page.evaluate(()=>pilot.seek(100)); await page.click('#play');await page.waitForTimeout(80);
 assert.equal(await page.evaluate(()=>pilot.voice),null);assert((await page.textContent('#status')).includes('Untranscribed'));
 await page.click('#play'); await page.selectOption('#phrase','0');await page.check('#loop');await page.evaluate(()=>pilot.seek(19.95));await page.click('#play');await page.waitForTimeout(220);
 assert((await page.evaluate(()=>pilot.audio.currentTime))<6);
 await page.selectOption('#mode','current');await page.waitForTimeout(80);assert(await page.evaluate(()=>!pilot.audio.paused));
 await page.selectOption('#mode','recording');await page.waitForTimeout(80);assert.equal(await page.evaluate(()=>pilot.audio.muted),false);assert.equal(await page.evaluate(()=>pilot.voice),null);
 assert.deepEqual(errors,[]);console.log(JSON.stringify({loaded,transportAdvanced:true,modePreservedTime:true,synthStarted:true,pauseStopsSynth:true,gapsSilent:true,phraseLoop:true,recordingUnmuted:true,pageErrors:errors},null,2));
 await page.screenshot({path:'audition-screenshot.png'});
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
