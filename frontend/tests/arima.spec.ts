import {test,expect} from '@playwright/test';

test('generates and displays an ARIMA active-aircraft forecast',async({page})=>{
 const requests:string[]=[];
 await page.addInitScript(()=>sessionStorage.setItem('skywatch-token','test'));
 await page.route('**/api/**',async route=>{const url=new URL(route.request().url());requests.push(url.pathname+url.search);let data:any={};
  if(url.pathname==='/api/auth/me')data={id:1,username:'test',role:'viewer'};
  if(url.pathname==='/api/aircraft')data={features:[]};if(url.pathname==='/api/alerts')data={alerts:[]};if(url.pathname==='/api/alerts/hotspots')data={type:'FeatureCollection',features:[]};if(url.pathname==='/api/alerts/stats')data={active_alerts:0,by_severity:{HIGH:0,MEDIUM:0,LOW:0}};if(url.pathname==='/api/analytics/routes')data={routes:[]};
  if(url.pathname==='/api/forecast/density')data={model:'ARIMA',status:'ok',message:'Active-aircraft density forecast generated with ARIMA.',metric:'distinct_active_aircraft_per_interval',order:[1,1,1],interval_minutes:15,scope:{h3_cell_id:null,bbox:[70,20,90,35]},history:[{time:'2026-10-08T08:00:00Z',aircraft_count:21},{time:'2026-10-08T08:15:00Z',aircraft_count:23}],forecast:[{time:'2026-10-08T08:30:00Z',predicted_aircraft_count:24.3},{time:'2026-10-08T08:45:00Z',predicted_aircraft_count:26.1}]};
  await route.fulfill({json:data});
 });
 await page.goto('http://127.0.0.1:5173');await page.getByRole('button',{name:'ARIMA Forecast',exact:true}).click();
 await page.getByLabel('Forecast area').selectOption('bbox');await page.getByLabel('Bounding box').fill('70,20,90,35');await page.getByRole('button',{name:'Generate forecast'}).click();
 await expect(page.getByText('Active-aircraft density forecast generated with ARIMA.')).toBeVisible();await expect(page.getByText('ARIMA fitted')).toBeVisible();await expect(page.getByRole('img',{name:/Historical and forecast/})).toBeVisible();await expect(page.getByText('24.3')).toBeVisible();
 expect(requests.some(request=>{const url=new URL(request,'http://skywatch');return url.pathname==='/api/forecast/density'&&url.searchParams.get('bbox')==='70,20,90,35'&&url.searchParams.get('steps')==='8'})).toBeTruthy();
});
