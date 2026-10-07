import {test,expect} from '@playwright/test';

test('calculates and displays a Kalman ETA',async({page})=>{
 await page.addInitScript(()=>sessionStorage.setItem('skywatch-token','test'));
 await page.route('**/api/**',async route=>{const path=new URL(route.request().url()).pathname;let data:any={};
  if(path==='/api/auth/me')data={id:1,username:'test',role:'viewer'};
  if(path==='/api/aircraft')data={features:[]};if(path==='/api/alerts')data={alerts:[]};if(path==='/api/alerts/hotspots')data={type:'FeatureCollection',features:[]};if(path==='/api/alerts/stats')data={active_alerts:0,by_severity:{HIGH:0,MEDIUM:0,LOW:0}};if(path==='/api/analytics/routes')data={routes:[]};
  if(path==='/api/aircraft/abc123/eta')data={icao24:'abc123',callsign:'TEST101',observations:8,last_observation:'2026-10-07T10:00:00Z',estimated_position:{longitude:77,latitude:28},destination:{longitude:78,latitude:29},filtered_speed_mps:200,filtered_heading:45,distance_km:150,closing_speed_mps:180,eta_seconds:833,eta:'2026-10-07T10:13:53Z',position_uncertainty_m:120,eta_confidence:{score:93,level:'HIGH',reason:'Based on 8 observations, 120m position uncertainty, and 180.0 m/s closing speed.'},status:'approaching',method:'constant_velocity_kalman'};
  await route.fulfill({json:data});
 });
 await page.route('https://tile.openstreetmap.org/**',r=>r.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64')}));
 await page.goto('http://127.0.0.1:5173');await page.getByRole('button',{name:'ETA Predictor',exact:true}).click();
 await page.getByLabel('ICAO24 or callsign').fill('ABC123');await page.getByLabel('Destination latitude').fill('29');await page.getByLabel('Destination longitude').fill('78');await page.getByRole('button',{name:'Calculate ETA'}).click();
 await expect(page.getByText('ETA calculated from filtered motion.')).toBeVisible();await expect(page.getByText('720 km/h')).toBeVisible();await expect(page.getByText('8 observations',{exact:true})).toBeVisible();await expect(page.getByText('HIGH (93%)')).toBeVisible();await expect(page.getByText(/120m position uncertainty/)).toBeVisible();await expect(page.getByText('Constant-velocity Kalman filter')).toBeVisible();
});
