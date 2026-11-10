import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { SqlStore, Scheduler, latestSlot } from '../src/core.mjs';

const now=Date.parse('2026-11-10T04:00:00Z');
function setup(overrides={}) {
 const db=new DatabaseSync(':memory:');
 const sql={exec(q,...p){const s=db.prepare(q);if(/^\s*(CREATE|UPDATE|INSERT)/i.test(q)&&!q.includes('RETURNING')){s.run(...p);return {toArray:()=>[]};}return {toArray:()=>s.all(...p)};}};
 const store=new SqlStore(sql); let posts=0;
 const github={preflight:async()=>true,dispatch:async()=>{posts++;return {workflow_run_id:100};},run:async()=>({status:'in_progress'}),...overrides};
 const scheduler=new Scheduler(store,github,{enabled:true,cutoverAt:now,nonce:()=> 'a'.repeat(32)});
 return {store,scheduler,github,posts:()=>posts};
}
test('calendar day step resets at month boundary',()=>{assert.equal(latestSlot(Date.parse('2026-11-01T04:00:00Z')),'2026-11-01T04:00:00.000Z');assert.equal(latestSlot(Date.parse('2026-11-01T03:59:00Z')),'2026-10-31T04:00:00.000Z');});
test('disabled by default and no credentials used',async()=>{const s=setup();s.scheduler.config.enabled=false;assert.equal((await s.scheduler.tick(now)).state,'disabled');assert.equal(s.posts(),0);});
test('no retroactive dispatch before cutover or after 4h',async()=>{const s=setup();assert.equal((await s.scheduler.tick(now-1)).state,'outside_window');assert.equal((await s.scheduler.tick(now+4*3600000)).state,'outside_window');assert.equal(s.posts(),0);});
test('concurrent ticks send exactly once',async()=>{const s=setup();await Promise.all(Array.from({length:10},()=>s.scheduler.tick(now)));assert.equal(s.posts(),1);});
test('ambiguous dispatch never automatically resends even after restart',async()=>{const s=setup({dispatch:async()=>{throw Error('timeout');}});assert.equal((await s.scheduler.tick(now)).dispatch_state,'uncertain');let sent=0;const restarted=new Scheduler(s.store,{...s.github,dispatch:async()=>{sent++;return {workflow_run_id:101};}},s.scheduler.config);await restarted.tick(now+300000);assert.equal(sent,0);});
test('preflight refusal sends nothing',async()=>{const s=setup({preflight:async()=>false});assert.equal((await s.scheduler.tick(now)).state,'preflight_blocked');assert.equal(s.posts(),0);});
test('legacy schedule event denied even with otherwise valid identity',async()=>{const s=setup();await s.scheduler.tick(now);assert.equal(s.store.admit(latestSlot(now),'a'.repeat(32),'100','1','schedule',now).allowed,false);});
test('new gate allows one owner, rejects competing run and rerun',async()=>{const s=setup();await s.scheduler.tick(now);const slot=latestSlot(now);assert.equal(s.store.admit(slot,'a'.repeat(32),'100','1','workflow_dispatch',now).allowed,true);assert.equal(s.store.admit(slot,'a'.repeat(32),'100','1','workflow_dispatch',now).allowed,true);assert.equal(s.store.admit(slot,'a'.repeat(32),'101','1','workflow_dispatch',now).allowed,false);assert.equal(s.store.admit(slot,'a'.repeat(32),'100','2','workflow_dispatch',now).allowed,false);});
test('wrong nonce denied',async()=>{const s=setup();await s.scheduler.tick(now);assert.equal(s.store.admit(latestSlot(now),'bad','100','1','workflow_dispatch',now).allowed,false);});
test('uncertain POST can be reconciled by authenticated run admission',async()=>{const s=setup({dispatch:async()=>{throw Error('timeout');}});await s.scheduler.tick(now);assert.equal(s.store.admit(latestSlot(now),'a'.repeat(32),'100','1','workflow_dispatch',now).allowed,true);s.github.run=async()=>({status:'completed',conclusion:'failure'});const r=await s.scheduler.tick(now+300000);assert.equal(r.execution_state,'failure');await s.scheduler.tick(now+600000);assert.equal(s.store.admit(latestSlot(now),'a'.repeat(32),'100','1','workflow_dispatch',now).allowed,false);});
test('success without admission is not collection success',async()=>{const s=setup({run:async()=>({status:'completed',conclusion:'success'})});await s.scheduler.tick(now);assert.equal((await s.scheduler.tick(now+1000)).execution_state,'not_admitted');});
test('failed slot is never auto rerun',async()=>{const s=setup({run:async()=>({status:'completed',conclusion:'failure'})});await s.scheduler.tick(now);s.store.admit(latestSlot(now),'a'.repeat(32),'100','1','workflow_dispatch',now);await s.scheduler.tick(now+1000);await s.scheduler.tick(now+2000);assert.equal(s.posts(),1);});
test('past active run blocks next slot',async()=>{const s=setup();await s.scheduler.tick(now);assert.equal((await s.scheduler.tick(Date.parse('2026-11-13T04:00:00Z'))).state,'previous_slot_unresolved');assert.equal(s.posts(),1);});
