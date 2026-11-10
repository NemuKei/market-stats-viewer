import { DurableObject } from 'cloudflare:workers';
import { SqlStore, Scheduler } from './core.mjs';
import { GitHub } from './github.mjs';
import { verifyIdentity, boundedJSON } from './security.mjs';
function enabled(env) { return env.ENABLED==='true' && env.CUTOVER_DRAINED==='true'; }
export class OfficialScheduleCoordinator extends DurableObject {
 constructor(ctx,env) {super(ctx,env);this.store=new SqlStore(ctx.storage.sql);}
 async tick(now=Date.now()) {
  const scheduler=new Scheduler(this.store,new GitHub(this.env),{
   enabled:enabled(this.env),cutoverAt:Date.parse(this.env.CUTOVER_AT ?? ''),nonce:()=>crypto.randomUUID().replaceAll('-',''),
  });
  return scheduler.tick(now);
 }
 async admit(token,body) {
  if(!enabled(this.env))return {allowed:false,reason:'disabled'};
  const identity=await verifyIdentity(token,this.env);
  if(!await new GitHub(this.env).gateMatches(identity.workflow_sha))return {allowed:false,reason:'gate_version'};
  if(typeof body.expected_at!=='string' || typeof body.dispatch_nonce!=='string' || body.dispatch_nonce.length>128)return {allowed:false,reason:'bad_request'};
  return this.store.admit(body.expected_at,body.dispatch_nonce,identity.run_id,identity.run_attempt,identity.event_name,Date.now());
 }
}
export default {
 async scheduled(controller,env) {
  const report=await env.COORDINATOR.getByName('official').tick(Date.now());
  // No secrets, JWT, nonce, raw responses, or private key in logs.
  console.log(JSON.stringify({kind:'official_schedule',scheduled_at:controller.scheduledTime,observed_at:Date.now(),state:report.state??report.dispatch_state,slot:report.slot,run_id:report.run_id,execution_state:report.execution_state}));
 },
 async fetch(request,env) {
  if(new URL(request.url).pathname!=='/admit'||request.method!=='POST')return new Response('Not found',{status:404});
  if(!enabled(env))return new Response('Disabled',{status:503});
  const auth=request.headers.get('Authorization')??'';
  if(!auth.startsWith('Bearer ')||auth.length>16384)return new Response('Unauthorized',{status:401});
  try {
   const body=await boundedJSON(new Response(request.body),4096);
   const result=await env.COORDINATOR.getByName('official').admit(auth.slice(7),body);
   return Response.json(result,{status:result.allowed?200:409,headers:{'Cache-Control':'no-store'}});
  }catch{return new Response('Admission failed',{status:401,headers:{'Cache-Control':'no-store'}});}
 }
};
