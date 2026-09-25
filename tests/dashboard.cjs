const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const center = fs.existsSync(path.join(__dirname, '../index.html'));
const html = fs.readFileSync(path.join(__dirname, center ? '../index.html' : '../docs/index.html'), 'utf8');
const source = html.match(/<script>([\s\S]*?)<\/script>/)[1].replace(/^load\(\);|^refreshAll\(\);/gm, '');
const elements = {};
const errors = [];
const attack = '<img src=x onerror="alert(1)">';
const fixture = {generated_at:new Date().toISOString(), last_scan_ts:null, alerts:[{ticker:attack,signal_label:attack,timestamp:'2026-09-01T12:00:00Z'}], threshold_changes:[attack], stats:{by_signal_type:{[attack]:{total:1,rated:0}}}};
const context = vm.createContext({document:{querySelector:id=>elements[id] ||= {style:{},innerHTML:'',textContent:''},getElementById:id=>elements[id] ||= {style:{},innerHTML:'',textContent:''}}, fetch:async()=>({ok:true,json:async()=>fixture}), setInterval:()=>{},setTimeout:()=>{},Date,console:{log:()=>{},error:(...args)=>errors.push(args)}});
(async()=>{
 vm.runInContext(source,context);
 if(center){
  assert.equal(vm.runInContext('statusFromAge(null, 60)',context),'err');
  assert.equal(vm.runInContext('statusFromAge(new Date(Date.now()+3600000).toISOString(), 60)',context),'err');
  assert.equal(vm.runInContext('pnlStr(-12.5)',context),'-$12.50');
  context.attack=attack;
  assert(!vm.runInContext('esc(attack)',context).includes('<img'));
  assert(vm.runInContext('esc(attack)',context).includes('&quot;'));
  vm.runInContext('render()',context);
 } else {
  await vm.runInContext('load()',context);
  assert.equal(errors.length,0,JSON.stringify(errors));
  const status=elements.stxt || elements['status-text'];
  assert.match(status.textContent,/unknown/i);
  vm.runInContext('setStatus(new Date(Date.now()+3600000).toISOString())',context);
  assert.match(status.textContent,/unknown/i);
  vm.runInContext('setStatus("2020-01-01T00:00:00Z")',context);
  assert.match(status.textContent,/stale/i);
  const rendered=Object.values(elements).map(e=>e.innerHTML).join('');
  assert(!rendered.includes('<img'), 'Untrusted data must be escaped');
  if(html.includes('alerts-body') && html.includes('change-log')) assert(rendered.includes('&lt;img'));
 }
 console.log('Dashboard reliability checks passed');
})().catch(err=>{console.error(err);process.exitCode=1;});
