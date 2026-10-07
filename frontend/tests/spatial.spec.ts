import {test,expect} from '@playwright/test';
const aircraft={type:'Feature',geometry:{type:'Point',coordinates:[77.21,28.61]},properties:{icao24:'abc123',callsign:'TEST101',origin_country:'India',altitude:5000,velocity:200,heading:90,last_update:'2026-10-07T10:00:00Z'}};
const polygon={type:'Polygon',coordinates:[[[77,28],[78,28],[78,29],[77,29],[77,28]]]};
async function setup(page:any,role='admin'){
 const requests:string[]=[];let custom=false;
 await page.addInitScript(()=>sessionStorage.setItem('skywatch-token','test'));
 await page.route('**/api/**',async(r:any)=>{const u=new URL(r.request().url());const path=u.pathname;requests.push(r.request().method()+' '+path+u.search);let d:any={};
 if(path==='/api/auth/me')d={id:1,username:'test',role};
 if(path==='/api/aircraft')d={features:[]};if(path==='/api/alerts')d={alerts:[]};if(path==='/api/alerts/hotspots')d={type:'FeatureCollection',features:[]};if(path==='/api/analytics/routes')d={routes:[]};if(path==='/api/alerts/stats')d={active_alerts:7,by_severity:{HIGH:2,MEDIUM:3,LOW:2}};
 if(path==='/api/aircraft/near')d={count:1,aircraft:[{...aircraft.properties,coordinates:aircraft.geometry.coordinates,distance_km:2}]};
 if(path==='/api/aircraft/viewport')d={count:1,features:[aircraft]};
 if(path==='/api/heatmap/density')d={cells:[{h3_cell:'test-cell',count:12,avg_altitude:5000,avg_velocity:200,boundary:polygon.coordinates[0].slice(0,4)}]};
 if(path==='/api/geofences'&&r.request().method()==='POST'){custom=true;d={type:'Feature',geometry:polygon,properties:{id:1,name:'My zone',builtin:false}}}
 else if(path==='/api/geofences')d={features:[{type:'Feature',geometry:polygon,properties:{id:'builtin-0',name:'Example zone',builtin:true}},...(custom?[{type:'Feature',geometry:polygon,properties:{id:1,name:'My zone',builtin:false}}]:[])]};
 if(path.endsWith('/aircraft')&&path.includes('/geofences/'))d={count:1,features:[aircraft]};
 if(path==='/api/geofences/1/deactivate')custom=false;
 if(path==='/api/aircraft/live')d={count:1,total_tracked:10,timestamp:'2026-10-07T10:00:00Z',aircraft:[{...aircraft.properties,longitude:77.21,latitude:28.61}]};
 await r.fulfill({json:d});});
 await page.route('https://tile.openstreetmap.org/**',(r:any)=>r.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64')}));
 await page.goto('http://127.0.0.1:5173');return requests;
}
test('spatial pages query radius, viewport, density, geofences and live feed',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));const requests=await setup(page);
 await page.getByRole('button',{name:'Spatial Explorer',exact:true}).click();await page.getByRole('button',{name:'Search radius',exact:true}).click();await expect(page.getByText('TEST101',{exact:true})).toBeVisible();expect(requests.some(r=>r.includes('/near?')&&r.includes('radius_km=50'))).toBeTruthy();
 await page.getByRole('button',{name:'Map viewport',exact:true}).click();await expect.poll(()=>requests.some(r=>r.includes('/viewport?'))).toBeTruthy();
 await page.getByRole('button',{name:'Density',exact:true}).click();await page.getByRole('button',{name:'Analyze density'}).click();await expect(page.getByRole('cell',{name:'test-cell'})).toBeVisible();await expect(page.getByRole('cell',{name:'720 km/h'})).toBeVisible();
 await page.getByRole('button',{name:'Geofences',exact:true}).click();await page.getByLabel('Choose a zone').selectOption('builtin-0');await expect(page.getByText('TEST101',{exact:true})).toBeVisible();await page.getByLabel('Zone name').fill('My zone');await page.getByRole('button',{name:'Save zone'}).click();await expect(page.getByLabel('Choose a zone')).toHaveValue('1');await page.getByRole('button',{name:'Deactivate zone'}).click();await expect(page.getByRole('status').last()).toContainText('deactivated');
 await page.getByRole('button',{name:'Live Feed',exact:true}).click();await page.getByRole('button',{name:'Fetch live snapshot'}).click();await expect(page.getByText('TEST101',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Spatial Explorer',exact:true}).click();await page.setViewportSize({width:390,height:844});await expect(page.getByLabel('Radius (km)')).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await page.screenshot({path:'tests/spatial-mobile.png',fullPage:true});expect(errors).toEqual([]);
});
test('viewer can inspect zones but cannot change them',async({page})=>{await setup(page,'viewer');await page.getByRole('button',{name:'Geofences',exact:true}).click();await expect(page.getByText('Analyst or admin access is required')).toBeVisible();await expect(page.getByRole('button',{name:'Save zone'})).toHaveCount(0)});
