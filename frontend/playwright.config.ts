import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tests',use:{headless:true,viewport:{width:1440,height:1000}},timeout:60000});
