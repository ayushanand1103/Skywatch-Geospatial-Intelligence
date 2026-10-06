import axios from 'axios';
import {create} from 'zustand';
export interface User {id:number;username:string;role:'viewer'|'analyst'|'admin'}
export interface Aircraft {type:'Feature';geometry:{type:'Point';coordinates:number[]};properties:{icao24:string;callsign:string|null;origin_country:string;altitude:number|null;velocity:number|null;heading:number|null;last_update:string}}
export interface Alert {id:number;type:string;severity:string;reason:string;aircraft_icao24:string;aircraft_callsign:string;is_active:boolean;is_acknowledged:boolean;detected_at:string;latitude:number;longitude:number}
export const api=axios.create({baseURL:'/api',timeout:60000});
export const useAuth=create<{token:string|null;user:User|null;set:(token:string,user:User)=>void;logout:()=>void}>((set)=>({token:sessionStorage.getItem('skywatch-token'),user:null,set:(token,user)=>{sessionStorage.setItem('skywatch-token',token);set({token,user})},logout:()=>{sessionStorage.removeItem('skywatch-token');set({token:null,user:null})}}));
api.interceptors.request.use(config=>{const token=useAuth.getState().token;if(token)config.headers.Authorization=`Bearer ${token}`;return config});
api.interceptors.response.use(r=>r,e=>{if(e.response?.status===401 && !e.config?.url?.includes('/auth/login'))useAuth.getState().logout();return Promise.reject(e)});
export function errorMessage(e:unknown){if(axios.isAxiosError(e)){const d=e.response?.data?.detail;return typeof d==='string'?d:Array.isArray(d)?d.map(x=>x.msg).join('. '):e.message}return 'Something went wrong. Please retry.'}
