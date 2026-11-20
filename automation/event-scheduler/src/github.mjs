import { REPO, WORKFLOW, LEGACY_WORKFLOW, appJWT, boundedJSON } from './security.mjs';
const root=`https://api.github.com/repos/${REPO}`;
export class GitHub {
  constructor(config, fetcher=(...args)=>globalThis.fetch(...args), tokenProvider=null) {this.config=config;this.fetcher=fetcher;this.tokenProvider=tokenProvider;}
  async request(url, options={}, authenticated=true) {
    const headers={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2026-03-10','User-Agent':'deltahelm-event-scheduler'};
    if(authenticated)headers.Authorization=`Bearer ${await (this.tokenProvider ? this.tokenProvider() : this.installationToken())}`;
    if(options.body)headers['Content-Type']='application/json';
    const response=await this.fetcher(url,{...options,headers,redirect:'manual',signal:AbortSignal.timeout(15000)});
    return boundedJSON(response);
  }
  async installationToken() {
    if(!/^\d+$/.test(this.config.GITHUB_INSTALLATION_ID ?? ''))throw Error('installation configuration');
    const response=await this.fetcher(`https://api.github.com/app/installations/${this.config.GITHUB_INSTALLATION_ID}/access_tokens`,{
      method:'POST',redirect:'manual',signal:AbortSignal.timeout(15000),
      headers:{Authorization:`Bearer ${await appJWT(this.config)}`,Accept:'application/vnd.github+json','Content-Type':'application/json','X-GitHub-Api-Version':'2026-03-10','User-Agent':'deltahelm-event-scheduler'},
      body:JSON.stringify({repositories:['market-stats-viewer'],permissions:{actions:'write',metadata:'read'}}),
    });
    const data=await boundedJSON(response);
    if(typeof data.token!=='string')throw Error('missing installation token');
    return data.token;
  }
  async gateMatches(ref='main') {
    if(!/^[0-9a-f]{40}$/.test(this.config.GATE_BLOB_SHA ?? ''))return false;
    const file=await this.request(`${root}/contents/.github/workflows/${WORKFLOW}?ref=${encodeURIComponent(ref)}`,{},false);
    if(file.sha!==this.config.GATE_BLOB_SHA || typeof file.content!=='string')return false;
    const content=atob(file.content.replace(/\s/g,''));
    return !/^\s*schedule\s*:/m.test(content) && content.includes('scheduler_admission');
  }
  async preflight() {
    if(!await this.gateMatches())return false;
    const legacy=await this.request(`${root}/actions/workflows/${LEGACY_WORKFLOW}`);
    if(legacy.state!=='disabled_manually')return false;
    for(const workflow of [LEGACY_WORKFLOW,WORKFLOW]) for(const status of ['queued','in_progress','pending','requested','waiting']) {
      const data=await this.request(`${root}/actions/workflows/${workflow}/runs?branch=main&status=${status}&per_page=1`);
      if(!Number.isInteger(data.total_count) || data.total_count!==0)return false;
    }
    return true;
  }
  async dispatch(slot,nonce) {
    return this.request(`${root}/actions/workflows/${WORKFLOW}/dispatches`,{method:'POST',body:JSON.stringify({ref:'main',inputs:{expected_at:slot,dispatch_nonce:nonce}})});
  }
  async run(id) {
    if(!/^\d+$/.test(id))throw Error('bad run id');
    const data=await this.request(`${root}/actions/runs/${id}`);
    if(data.path!==`.github/workflows/${WORKFLOW}` || data.head_branch!=='main' || String(data.id)!==id)throw Error('run mismatch');
    return data;
  }
}
