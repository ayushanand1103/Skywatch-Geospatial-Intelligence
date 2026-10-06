import {useEffect,useRef,useState} from 'react';
import * as maplibregl from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
maplibregl.setWorkerUrl(workerUrl);
import {Aircraft} from './api';
interface HotspotAlert {id:number;icao24:string|null;callsign:string|null;type:string;severity:string;reason:string;detected_at:string}
function hotspotDetails(properties:any){
 const container=document.createElement('div');container.className='hotspot-details';
 const heading=document.createElement('h3');heading.textContent='Anomaly aircraft';container.append(heading);
 const summary=document.createElement('p');summary.textContent=`${properties.count} active alerts / ${properties.aircraft_count} aircraft`;container.append(summary);
 const alerts:HotspotAlert[]=typeof properties.alerts==='string'?JSON.parse(properties.alerts):properties.alerts||[];
 const groups=new Map<string,HotspotAlert[]>();
 for(const alert of alerts){const key=alert.icao24||alert.callsign||`unknown-${alert.id}`;groups.set(key,[...(groups.get(key)||[]),alert])}
 for(const group of groups.values()){
 const section=document.createElement('section');
 const name=document.createElement('h4');name.textContent=group[0].callsign?.trim()||group[0].icao24?.toUpperCase()||'Unknown aircraft';section.append(name);
 if(group[0].icao24){const id=document.createElement('p');id.textContent=`ICAO: ${group[0].icao24.toUpperCase()}`;section.append(id)}
 for(const alert of group){
 const title=document.createElement('strong');title.textContent=`${alert.severity} / ${alert.type.replaceAll('_',' ')}`;
 const reason=document.createElement('p');reason.textContent=alert.reason;
 const time=document.createElement('small');time.textContent=new Date(alert.detected_at).toLocaleString();
 const detail=document.createElement('div');detail.className='hotspot-alert';detail.append(title,reason,time);section.append(detail);
 }
 container.append(section);
 }
 if(!alerts.length){const empty=document.createElement('p');empty.textContent='Aircraft details are unavailable. Refresh to load the latest hotspot data.';container.append(empty)}
 return container;
}
export default function MapView({aircraft,selected,onSelect,heatmap,trajectory,hotspots}:{aircraft:Aircraft[];selected:Aircraft|null;onSelect:(a:Aircraft)=>void;heatmap:boolean;trajectory:any;hotspots:any}){
 const popup=useRef<maplibregl.Popup|null>(null);const element=useRef<HTMLDivElement>(null),map=useRef<maplibregl.Map|null>(null);const [ready,setReady]=useState(false),[error,setError]=useState('');const data=useRef(aircraft);const callback=useRef(onSelect);data.current=aircraft;callback.current=onSelect;
 useEffect(()=>{if(!element.current)return;let m:maplibregl.Map;try{m=new maplibregl.Map({container:element.current,center:[9,48],zoom:3.6,style:{version:8,sources:{base:{type:'raster',tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:'&copy; OpenStreetMap contributors'}},layers:[{id:'base',type:'raster',source:'base',paint:{'raster-saturation':-0.8,'raster-brightness-max':0.45,'raster-contrast':0.25}}]}});map.current=m;m.on('error',()=>setError('Map tiles unavailable. Check your internet connection.'));m.addControl(new maplibregl.NavigationControl(),'bottom-right');m.on('style.load',()=>{m.addSource('aircraft',{type:'geojson',data:{type:'FeatureCollection',features:[]}});m.addLayer({id:'density',type:'heatmap',source:'aircraft',paint:{'heatmap-radius':32,'heatmap-opacity':0.6}});m.addLayer({id:'aircraft',type:'circle',source:'aircraft',paint:{'circle-radius':['interpolate',['linear'],['zoom'],2,3,8,7],'circle-color':'#c5e882','circle-stroke-color':'#151c17','circle-stroke-width':2}});m.addSource('hotspots',{type:'geojson',data:{type:'FeatureCollection',features:[]}});m.addLayer({id:'hotspots',type:'circle',source:'hotspots',paint:{'circle-radius':['interpolate',['linear'],['get','count'],1,12,10,28,50,55,200,85],'circle-color':'#ef935c','circle-opacity':0.2,'circle-stroke-color':'#ef935c','circle-stroke-width':2}});m.on('click','hotspots',e=>{const f=e.features?.[0];if(!f)return;popup.current?.remove();popup.current=new maplibregl.Popup({className:'anomaly-popup',maxWidth:'340px'}).setLngLat(e.lngLat).setDOMContent(hotspotDetails(f.properties)).addTo(m)});m.on('mouseenter','hotspots',()=>{m.getCanvas().style.cursor='pointer'});m.on('mouseleave','hotspots',()=>{m.getCanvas().style.cursor=''});m.addSource('trajectory',{type:'geojson',data:{type:'FeatureCollection',features:[]}});m.addLayer({id:'trajectory-outline',type:'line',source:'trajectory',paint:{'line-color':'#101318','line-width':9}});m.addLayer({id:'trajectory',type:'line',source:'trajectory',paint:{'line-color':'#55e5ff','line-width':5}});m.addSource('trajectory-endpoints',{type:'geojson',data:{type:'FeatureCollection',features:[]}});m.addLayer({id:'trajectory-endpoints',type:'circle',source:'trajectory-endpoints',paint:{'circle-radius':7,'circle-color':['case',['==',['get','endpoint'],'start'],'#c5e882','#55e5ff'],'circle-stroke-color':'#101318','circle-stroke-width':2}});// A larger hit area makes small aircraft dots easy to select on touch screens.
 m.addLayer({id:'aircraft-hit',type:'circle',source:'aircraft',paint:{'circle-radius':16,'circle-opacity':0}});
 m.on('click','aircraft-hit',e=>{
 if(m.queryRenderedFeatures(e.point,{layers:['hotspots']}).length)return;
 popup.current?.remove();
 const candidates=e.features||[];
 const nearest=candidates.reduce<Aircraft|null>((best,f)=>{
 const a=data.current.find(x=>x.properties.icao24===f.properties?.icao24);
 if(!a)return best;
 const point=m.project(a.geometry.coordinates.slice(0,2) as [number,number]);
 if(!best)return a;
 const previous=m.project(best.geometry.coordinates.slice(0,2) as [number,number]);
 return Math.hypot(point.x-e.point.x,point.y-e.point.y)<Math.hypot(previous.x-e.point.x,previous.y-e.point.y)?a:best;
 },null);
 if(nearest)callback.current(nearest);
 });
 m.on('mouseenter','aircraft-hit',()=>{m.getCanvas().style.cursor='pointer'});m.on('mouseleave','aircraft-hit',()=>{m.getCanvas().style.cursor=''});setReady(true)});}catch{setError('The map could not start. Check WebGL support in your browser.')}return()=>{popup.current?.remove();m?.remove();map.current=null;setReady(false)}},[]);
 useEffect(()=>{if(!ready||!map.current)return;(map.current.getSource('aircraft') as maplibregl.GeoJSONSource).setData({type:'FeatureCollection',features:aircraft} as any);map.current.setLayoutProperty('density','visibility',heatmap?'visible':'none')},[ready,aircraft,heatmap]);
 useEffect(()=>{if(!ready||!map.current)return;map.current.setPaintProperty('aircraft','circle-color',['case',['==',['get','icao24'],selected?.properties.icao24||''],'#ffbd69','#c5e882']);map.current.setPaintProperty('aircraft','circle-stroke-width',['case',['==',['get','icao24'],selected?.properties.icao24||''],3,2])},[ready,selected]);
 useEffect(()=>{if(ready&&selected)map.current?.flyTo({center:selected.geometry.coordinates.slice(0,2) as [number,number],zoom:6,duration:1200})},[ready,selected]);
 useEffect(()=>{if(!ready||!map.current)return;(map.current.getSource('trajectory') as maplibregl.GeoJSONSource).setData(trajectory?.geometry?trajectory:{type:'FeatureCollection',features:[]});const coords=trajectory?.geometry?.coordinates;(map.current.getSource('trajectory-endpoints') as maplibregl.GeoJSONSource).setData({type:'FeatureCollection',features:coords?.length>=2?[{type:'Feature',geometry:{type:'Point',coordinates:coords[0]},properties:{endpoint:'start'}},{type:'Feature',geometry:{type:'Point',coordinates:coords[coords.length-1]},properties:{endpoint:'end'}}]:[]});if(coords?.length>=2){const bounds=new maplibregl.LngLatBounds();coords.forEach((c:number[])=>bounds.extend([c[0],c[1]]));map.current.fitBounds(bounds,{padding:{top:60,bottom:70,left:Math.min(330,map.current.getContainer().clientWidth/3),right:40},maxZoom:12,duration:900})}},[ready,trajectory]);
 useEffect(()=>{popup.current?.remove();if(ready)(map.current?.getSource('hotspots') as maplibregl.GeoJSONSource)?.setData(hotspots||{type:'FeatureCollection',features:[]})},[ready,hotspots]);
 return <><div className="map" ref={element}/>{error&&<div className="map-error">{error}</div>}</>;
}

