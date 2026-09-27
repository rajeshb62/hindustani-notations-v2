const {chromium}=require('./test-tools/node_modules/playwright');
const assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--autoplay-policy=no-user-gesture-required']});try{const page=await browser.newPage();await page.goto('http://127.0.0.1:8765/pilots/jasraj-precision-v1/index.html');await page.waitForFunction(()=>window.pilot?.ready);
for(const mode of ['recording','current','candidate']){
 await page.selectOption('#mode',mode);await page.selectOption('#phrase','0');await page.check('#loop');
 if(await page.evaluate(()=>pilot.audio.paused))await page.click('#play');
 await page.locator('#seek').evaluate(el=>{el.value='2631';el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));});
 await page.waitForTimeout(350);
 const state=await page.evaluate(()=>({time:pilot.audio.currentTime,loop:document.getElementById('loop').checked,mode:pilot.mode}));
 assert(state.time>=2631 && state.time<2633,JSON.stringify(state));assert.equal(state.loop,false);assert.equal(state.mode,mode);
}
await page.selectOption('#phrase','1');await page.check('#loop');await page.waitForTimeout(250);assert((await page.evaluate(()=>pilot.audio.currentTime))>=30);assert((await page.evaluate(()=>pilot.audio.currentTime))<43);
console.log('PASS: manual later seek survives in recording/current/candidate; outside seek disables loop; excerpt selection and looping retained');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
