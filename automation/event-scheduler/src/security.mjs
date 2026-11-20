import { createRemoteJWKSet, jwtVerify, SignJWT, importPKCS8 } from 'jose';
export const REPO='NemuKei/market-stats-viewer';
export const LEGACY_WORKFLOW='update_events_official.yml';
export const WORKFLOW='update_events_official_external.yml';
const issuer='https://token.actions.githubusercontent.com';
const jwks=createRemoteJWKSet(new URL(`${issuer}/.well-known/jwks`));
export async function verifyIdentity(token, config, keys=jwks) {
  if (!config.AUDIENCE?.startsWith('https://') || !/^\d+$/.test(config.REPOSITORY_ID ?? '')) throw Error('configuration');
  const {payload:p}=await jwtVerify(token,keys,{issuer,audience:config.AUDIENCE,algorithms:['RS256'],maxTokenAge:'10m',clockTolerance:5});
  if (p.repository!==REPO || p.repository_id!==config.REPOSITORY_ID || p.ref!=='refs/heads/main'
    || p.sub!==`repo:${REPO}:ref:refs/heads/main`
    || p.workflow_ref!==`${REPO}/.github/workflows/${WORKFLOW}@refs/heads/main`
    || !/^[0-9a-f]{40}$/.test(p.workflow_sha ?? '') || p.event_name!=='workflow_dispatch'
    || p.run_attempt!=='1' || !/^\d+$/.test(p.run_id ?? '')) throw Error('identity scope');
  return p;
}
export async function appJWT(config) {
  if (!/^\d+$/.test(config.GITHUB_APP_ID ?? '')) throw Error('app configuration');
  const key=await importPKCS8(config.GITHUB_APP_PRIVATE_KEY,'RS256');
  const now=Math.floor(Date.now()/1000);
  return new SignJWT({}).setProtectedHeader({alg:'RS256'}).setIssuer(config.GITHUB_APP_ID).setIssuedAt(now-30).setExpirationTime(now+300).sign(key);
}
export async function boundedJSON(response, limit=262144) {
  if (!response.ok) throw Error(`HTTP ${response.status}`);
  const reader=response.body?.getReader();
  if (!reader) throw Error('missing body');
  let size=0;const chunks=[];
  for (;;) {const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>limit){await reader.cancel();throw Error('response too large');}chunks.push(value);}
  const out=new Uint8Array(size);let offset=0;for(const c of chunks){out.set(c,offset);offset+=c.byteLength;}
  return JSON.parse(new TextDecoder().decode(out));
}
