import {test,expect} from '@playwright/test';
test('tap hotspot to show all aircraft and readable alert details',async({page})=>{
 await page.addInitScript(()=>sessionStorage.setItem('skywatch-token','test'));
 await page.route('**/api/**',async r=>{
 const path=new URL(r.request().url()).pathname;let d:any={};
 if(path==='/api/auth/me')d={id:1,username:'test',role:'viewer'};
 if(path==='/api/aircraft')d={features:[]};if(path==='/api/alerts')d={alerts:[]};if(path==='/api/analytics/routes')d={routes:[]};
 if(path==='/api/alerts/hotspots')d={type:'FeatureCollection',features:[{type:'Feature',geometry:{type:'Point',coordinates:[9,48]},properties:{count:3,aircraft_count:2,alerts:[1,2,3].map(id=>({id,icao24:id<3?'abc123':'def456',callsign:id<3?'TEST101':'TEST202',type:'LOW_ALTITUDE',severity:'HIGH',reason:`Alert reason ${id}`,detected_at:'2026-10-07T10:00:00Z'}))}}]};
 await r.fulfill({json:d});
 });
 await page.route('https://tile.openstreetmap.org/**',r=>r.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64')}));
 await page.goto('http://127.0.0.1:5173');const canvas=page.locator('.maplibregl-canvas');await expect(canvas).toBeVisible();
 await expect(async()=>{const box=await canvas.boundingBox();await canvas.click({position:{x:box!.width/2,y:box!.height/2}});await expect(page.locator('.hotspot-details')).toBeVisible()}).toPass({timeout:15000});
 await expect(page.locator('.hotspot-details h4')).toHaveText(['TEST101','TEST202']);await expect(page.locator('.hotspot-alert')).toHaveCount(3);
 await expect(page.locator('.hotspot-details')).toContainText('Alert reason 3');await expect(page.locator('.hotspot-details')).toHaveCSS('color','rgb(255, 255, 255)');
 await expect(page.locator('.anomaly-popup .maplibregl-popup-content')).toHaveCSS('background-color','rgb(28, 34, 42)');
});
