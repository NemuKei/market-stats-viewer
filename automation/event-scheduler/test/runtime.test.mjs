import test from 'node:test';
import assert from 'node:assert/strict';
import { Miniflare, createFetchMock } from 'miniflare';
import { build } from 'esbuild';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { generateKeyPair, exportPKCS8, exportJWK, SignJWT } from 'jose';
const now=Date.parse('2026-11-10T04:00:00Z');
const root='https://api.github.com';
const repo='/repos/NemuKei/market-stats-viewer';
async function fixture(ambiguous=false, enabled=true) {
 const source=(await build({entryPoints:['src/worker.mjs'],bundle:true,write:false,format:'esm',external:['cloudflare:workers']})).outputFiles[0].text;
 const {privateKey,publicKey}=await generateKeyPair('RS256',{extractable:true});
 const mock=createFetchMock();mock.disableNetConnect();let dispatches=0;
 const api=mock.get(root);
 api.intercept({path:/\/contents\//}).reply(200,{sha:'a'.repeat(40),content:btoa('on:\n  workflow_dispatch:\n# scheduler_admission')}).persist();
 api.intercept({path:/\/runs\?/}).reply(200,{total_count:0,workflow_runs:[]}).persist();
 api.intercept({path:'/app/installations/1/access_tokens',method:'POST'}).reply(201,{token:'synthetic'}).persist();
 api.intercept({path:`${repo}/actions/workflows/update_events_official.yml`}).reply(200,{state:'disabled_manually'}).persist();
 const d=api.intercept({path:`${repo}/actions/workflows/update_events_official_external.yml/dispatches`,method:'POST'});
 if(ambiguous)d.reply(500,()=>{dispatches++;return {};}).persist();
 else d.reply(200,()=>{dispatches++;return {workflow_run_id:100};}).persist();
 api.intercept({path:`${repo}/actions/runs/100`}).reply(200,{id:100,path:'.github/workflows/update_events_official_external.yml',head_branch:'main',status:'in_progress'}).persist();
 const jwk=await exportJWK(publicKey);jwk.kid='test';
 mock.get('https://token.actions.githubusercontent.com').intercept({path:'/.well-known/jwks'}).reply(200,{keys:[jwk]}).persist();
 const persist=await mkdtemp(join(tmpdir(),'official-do-'));
 const options={modules:true,script:source,compatibilityDate:'2026-08-06',durableObjects:{COORDINATOR:{className:'OfficialScheduleCoordinator',useSQLite:true}},durableObjectsPersist:persist,fetchMock:mock,bindings:{ENABLED:String(enabled),CUTOVER_DRAINED:'true',CUTOVER_AT:'2026-11-10T04:00:00Z',GATE_BLOB_SHA:'a'.repeat(40),AUDIENCE:'https://scheduler.example.test',REPOSITORY_ID:'123',GITHUB_APP_ID:'1',GITHUB_INSTALLATION_ID:'1',GITHUB_APP_PRIVATE_KEY:await exportPKCS8(privateKey)}};
 let mf=new Miniflare(options);
 async function stub(){const ns=await mf.getDurableObjectNamespace('COORDINATOR');return ns.get(ns.idFromName('official'));}
 async function token(id='100',event='workflow_dispatch'){return new SignJWT({repository:'NemuKei/market-stats-viewer',repository_id:'123',ref:'refs/heads/main',workflow_ref:'NemuKei/market-stats-viewer/.github/workflows/update_events_official_external.yml@refs/heads/main',workflow_sha:'b'.repeat(40),event_name:event,run_id:id,run_attempt:'1'}).setProtectedHeader({alg:'RS256',kid:'test'}).setIssuer('https://token.actions.githubusercontent.com').setAudience(options.bindings.AUDIENCE).setSubject('repo:NemuKei/market-stats-viewer:ref:refs/heads/main').setIssuedAt().setExpirationTime('5m').sign(privateKey);}
 return {stub,token,dispatches:()=>dispatches,async restart(){await mf.dispose();mf=new Miniflare(options);},async close(){await mf.dispose();await mock.close();await rm(persist,{recursive:true,force:true});}};
}
test('workerd SQLite persists admission across restart, duplicates denied',async()=>{const f=await fixture();try{const d=await f.stub();const result=await d.tick(now);const r={run_id:result.run_id,slot:result.slot,nonce:result.nonce};assert.equal(r.run_id,'100',JSON.stringify(r));assert.equal(f.dispatches(),1);assert.equal((await d.admit(await f.token(),{expected_at:r.slot,dispatch_nonce:r.nonce})).allowed,true);await f.restart();const d2=await f.stub();await d2.tick(now+300000);assert.equal(f.dispatches(),1);assert.equal((await d2.admit(await f.token('101'),{expected_at:r.slot,dispatch_nonce:r.nonce})).allowed,false);}finally{await f.close();}});
test('workerd ambiguous POST persists and is not resent after restart',async()=>{const f=await fixture(true);try{const first=await (await f.stub()).tick(now);assert.equal(first.dispatch_state,'uncertain',JSON.stringify(first));await f.restart();assert.equal((await (await f.stub()).tick(now+300000)).dispatch_state,'uncertain');assert.equal(f.dispatches(),1);}finally{await f.close();}});
test('workerd disabled mode never contacts GitHub',async()=>{const f=await fixture(false,false);try{assert.equal((await (await f.stub()).tick(now)).state,'disabled');assert.equal(f.dispatches(),0);}finally{await f.close();}});
