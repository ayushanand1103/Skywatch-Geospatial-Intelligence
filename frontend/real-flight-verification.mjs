import {chromium} from '@playwright/test';
const browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}});
try{
 const username=`verify_${Date.now()}`,password=`verify-${Date.now()}-flight`;
 const registration=await page.request.post('http://127.0.0.1:8000/api/auth/register',{data:{username,password}});if(!registration.ok())throw Error('Test account registration failed');
 const login=await page.request.post('http://127.0.0.1:8000/api/auth/login',{form:{username,password}});const {access_token}=await login.json();
 await page.addInitScript(token=>sessionStorage.setItem('skywatch-token',token),access_token);
 await page.goto('http://127.0.0.1:5173');
 await page.waitForFunction(()=>{const el=document.querySelector('.map');if(!el)return false;const key=Object.keys(el).find(k=>k.startsWith('__reactFiber'));let fiber=el[key];while(fiber){let hook=fiber.memoizedState;while(hook){const ref=hook.memoizedState;if(ref?.current?.getSource&&ref.current.getSource('aircraft')){window.__verificationMap=ref.current;return true}hook=hook.next}fiber=fiber.return}return false},null,{timeout:30000});
 const headers={Authorization:`Bearer ${access_token}`};const response=await page.request.get('http://127.0.0.1:8000/api/aircraft',{headers});const data=await response.json();let chosen;
 for(const a of data.features){const r=await page.request.get(`http://127.0.0.1:8000/api/aircraft/${a.properties.icao24}/sessions?hours=720`,{headers});const s=await r.json();if(s.sessions?.[0]?.has_trajectory){chosen=a;break}}
 if(!chosen)throw Error(`No aircraft with visible current position and movement history among ${data.features.length} aircraft`);
 console.log('Testing real aircraft:',chosen.properties.icao24,chosen.properties.callsign);
 await page.getByRole('button',{name:'Anomaly hotspots on'}).click();
 await page.evaluate(a=>window.__verificationMap.jumpTo({center:a.geometry.coordinates.slice(0,2),zoom:9}),chosen);
 await page.waitForTimeout(1200);
 const point=await page.evaluate(a=>{const p=window.__verificationMap.project(a.geometry.coordinates.slice(0,2));return {x:p.x,y:p.y}},chosen);
 await page.locator('.maplibregl-canvas').click({position:point});
 await page.getByRole('region',{name:'Flight information'}).waitFor();
 await page.waitForFunction(()=>document.querySelector('#trajectory-status')?.textContent?.startsWith('Trajectory for'),null,{timeout:15000});await page.waitForTimeout(1500);
 const result=await page.evaluate(()=>{const m=window.__verificationMap;return {details:document.querySelector('.asset-card')?.textContent,status:document.querySelector('#trajectory-status')?.textContent,lineFeatures:m.queryRenderedFeatures({layers:['trajectory']}).length,endpoints:m.queryRenderedFeatures({layers:['trajectory-endpoints']}).length}});
 console.log(JSON.stringify(result));if(!result.lineFeatures)throw Error('Trajectory is not visibly rendered');
 await page.screenshot({path:'tests/real-flight-verification.png',fullPage:true});console.log('PASS: real dot click, details, session, and rendered trajectory');
}finally{await browser.close()}
