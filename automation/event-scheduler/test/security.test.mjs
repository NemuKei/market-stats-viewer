import test from 'node:test';
import assert from 'node:assert/strict';
import { generateKeyPair, exportJWK, SignJWT, createLocalJWKSet } from 'jose';
import { verifyIdentity } from '../src/security.mjs';
import { GitHub } from '../src/github.mjs';
const {privateKey,publicKey}=await generateKeyPair('RS256');
const jwk=await exportJWK(publicKey);jwk.kid='test';const keys=createLocalJWKSet({keys:[jwk]});
const config={AUDIENCE:'https://scheduler.example.test',REPOSITORY_ID:'123',GATE_BLOB_SHA:'a'.repeat(40)};
const valid={repository:'NemuKei/market-stats-viewer',repository_id:'123',ref:'refs/heads/main',workflow_ref:'NemuKei/market-stats-viewer/.github/workflows/update_events_official_external.yml@refs/heads/main',workflow_sha:'b'.repeat(40),event_name:'workflow_dispatch',run_id:'100',run_attempt:'1'};
async function jwt(changes={},aud=config.AUDIENCE){return new SignJWT({...valid,...changes}).setProtectedHeader({alg:'RS256',kid:'test'}).setIssuer('https://token.actions.githubusercontent.com').setAudience(aud).setSubject('repo:NemuKei/market-stats-viewer:ref:refs/heads/main').setIssuedAt().setExpirationTime('5m').sign(privateKey);}
test('valid scoped signed identity is accepted',async()=>assert.equal((await verifyIdentity(await jwt(),config,keys)).run_id,'100'));
for(const [name,change] of Object.entries({repo:{repository:'evil/repo'},id:{repository_id:'124'},ref:{ref:'refs/heads/other'},workflow:{workflow_ref:'NemuKei/market-stats-viewer/.github/workflows/evil.yml@refs/heads/main'},legacy:{event_name:'schedule'},rerun:{run_attempt:'2'}}))test(`reject ${name}`,async()=>assert.rejects(()=>jwt(change).then(t=>verifyIdentity(t,config,keys))));
test('wrong audience rejected',async()=>assert.rejects(()=>jwt({},'wrong').then(t=>verifyIdentity(t,config,keys))));
test('signature tampering rejected',async()=>{const t=await jwt();await assert.rejects(()=>verifyIdentity(t.slice(0,-10)+'AAAAAAAAAA',config,keys));});
test('preflight rejects legacy schedule definition',async()=>{const g=new GitHub(config,async()=>Response.json({sha:config.GATE_BLOB_SHA,content:btoa('on:\n  schedule:\n    - cron: x')}),async()=> 'synthetic');assert.equal(await g.preflight(),false);});
test('preflight rejects any active legacy run',async()=>{const g=new GitHub(config,async(url)=>Response.json(url.includes('/contents/')?{sha:config.GATE_BLOB_SHA,content:btoa('on:\n  workflow_dispatch:\n# scheduler_admission')}: url.endsWith('/update_events_official.yml') ? {state:'disabled_manually'} : {total_count:1,workflow_runs:[{status:'queued',event:'schedule'}]}),async()=> 'synthetic');assert.equal(await g.preflight(),false);});
test('dispatch is fixed to named workflow and main with slot nonce',async()=>{let seen;const g=new GitHub(config,async(url,init)=>{seen={url,init};return Response.json({workflow_run_id:100});},async()=> 'synthetic');await g.dispatch('2026-11-10T04:00:00.000Z','nonce');assert.match(seen.url,/\/update_events_official_external.yml\/dispatches$/);assert.deepEqual(JSON.parse(seen.init.body),{ref:'main',inputs:{expected_at:'2026-11-10T04:00:00.000Z',dispatch_nonce:'nonce'}});assert.equal(seen.init.redirect,'manual');assert.equal(seen.init.headers['X-GitHub-Api-Version'],'2026-03-10');});

test('preflight rejects old workflow not explicitly disabled',async()=>{const g=new GitHub(config,async(url)=>Response.json(url.includes('/contents/')?{sha:config.GATE_BLOB_SHA,content:btoa('on:\n workflow_dispatch:\n# scheduler_admission')}:{state:'active'}),async()=> 'synthetic');assert.equal(await g.preflight(),false);});
