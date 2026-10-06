import {test,expect} from '@playwright/test';
test('ICAO trajectory lookup normalizes codes and handles missing history',async({page})=>{
 const requested:string[]=[];
 await page.addInitScript(()=>sessionStorage.setItem('skywatch-token','test'));
 await page.route('**/api/**',async r=>{const path=new URL(r.request().url()).pathname;let d:any={};
 if(path==='/api/auth/me')d={id:1,username:'test',role:'viewer'};
 if(path==='/api/aircraft')d={features:[]};if(path==='/api/alerts')d={alerts:[]};if(path==='/api/analytics/routes')d={routes:[]};if(path==='/api/alerts/hotspots')d={type:'FeatureCollection',features:[]};
 if(path==='/api/aircraft/resolve/ocn6eg')d={icao24:'3c66e5',callsign:'OCN6EG'};
 if(path.endsWith('/sessions')&&path.includes('ffffff')){await r.fulfill({status:404,json:{detail:'Aircraft not found'}});return}
 if(path.endsWith('/sessions'))d={sessions:[{id:1,start_time:'2026-10-07T08:00:00Z',end_time:'2026-10-07T09:00:00Z',point_count:2,has_trajectory:true},{id:2,start_time:'2026-10-06T08:00:00Z',end_time:'2026-10-06T09:00:00Z',point_count:2,has_trajectory:true}]};
 if(path.includes('/trajectory')){requested.push(r.request().url());if(path.includes('ffffff')){await r.fulfill({status:404,json:{detail:'Aircraft not found'}});return}d={type:'Feature',geometry:path.includes('000000')?null:{type:'LineString',coordinates:[[9,48],[10,49]]},properties:{count:2}}}
 await r.fulfill({json:d});});
 await page.route('https://tile.openstreetmap.org/**',r=>r.fulfill({contentType:'image/png',body:Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64')}));
 await page.goto('http://127.0.0.1:5173');const input=page.getByLabel('Aircraft trajectory by ICAO24 or callsign');const submit=page.getByRole('button',{name:'Show trajectory'});
 await input.fill('bad-code');await submit.click();await expect(page.locator('#trajectory-status')).toContainText('valid six-character');expect(requested).toHaveLength(0);
 await input.fill(' ABC123 ');await submit.click();await expect(page.locator('#trajectory-status')).toContainText('Trajectory for ABC123');expect(requested[0]).toContain('/abc123/trajectory?hours=720&session_id=1');await expect(input).toHaveValue('ABC123');
 await page.getByLabel('Flight session',{exact:true}).selectOption('2');await expect.poll(()=>requested[requested.length-1]).toContain('session_id=2');
 await page.getByRole('button',{name:'Clear',exact:true}).click();await expect(page.locator('#trajectory-status')).toContainText('Enter the unique');
 await input.fill('ocn6eg');await submit.click();await expect(page.locator('#trajectory-status')).toContainText('Trajectory for 3C66E5');await expect(input).toHaveValue('3C66E5');
 await input.fill('000000');await submit.click();await expect(page.locator('#trajectory-status')).toContainText('At least two different');
 await input.fill('ffffff');await submit.click();await expect(page.locator('#trajectory-status')).toHaveText('Aircraft not found');
});
