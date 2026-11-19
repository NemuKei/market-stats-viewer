const statuses = new Set(["requested","queued","pending","waiting","in_progress","completed"]);
const conclusions = new Set(["success","failure","cancelled","skipped","timed_out","action_required","neutral","stale","startup_failure"]);
const workflowStates = new Set(["active","disabled_manually","disabled_inactivity","disabled_fork"]);
const isoTime = value => typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(value) &&
  Number.isFinite(Date.parse(value)) ? Date.parse(value) : null;

export async function getJson(fetcher, url, headers = {}) {
  const response = await fetcher(url, {method:"GET", headers, redirect:"error", signal:AbortSignal.timeout(8_000)});
  if (!response.ok || !response.body) throw new Error("Could not read observation");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let bytes = 0, text = "";
  try {
    for (;;) {
      const {done,value} = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > 2_000_000) {
        await reader.cancel();
        throw new Error("Observation response too large");
      }
      text += decoder.decode(value, {stream:true});
    }
    return JSON.parse(text + decoder.decode());
  } finally {
    reader.releaseLock();
  }
}

export function githubReader(fetcher, token) {
  const headers = {Accept:"application/vnd.github+json", Authorization:`Bearer ${token}`,
    "User-Agent":"schedule-watch", "X-GitHub-Api-Version":"2022-11-28"};
  const endpoint = target => `https://api.github.com/repos/${target.repository}/actions/workflows/${encodeURIComponent(target.workflow)}`;
  return {
    async state(target) {
      const {state} = await getJson(fetcher, endpoint(target), headers);
      if (!workflowStates.has(state)) throw new Error("Unknown workflow state");
      return state;
    },
    async runs(target, from, now) {
      const runs = [];
      for (let page = 1; page <= 10; page++) {
        const url = new URL(endpoint(target) + "/runs");
        url.search = new URLSearchParams({branch:"main",event:"schedule",per_page:"100",page:String(page),
          created:`${new Date(from).toISOString()}..${new Date(now).toISOString()}`});
        const {workflow_runs:items,total_count:total} = await getJson(fetcher, url, headers);
        if (!Array.isArray(items) || items.length > 100 || total > 1000) throw new Error("Invalid workflow runs response");
        for (const item of items) {
          if (item.event !== "schedule" || item.head_branch !== "main") continue;
          const createdAt = isoTime(item.created_at);
          if (createdAt === null || !Number.isSafeInteger(item.id) || item.id <= 0) throw new Error("Invalid workflow run");
          if (createdAt < from || createdAt > now) continue;
          const status = statuses.has(item.status) ? item.status : null;
          runs.push({id:item.id, createdAt, event:"schedule", branch:"main", startedAt:isoTime(item.run_started_at),
            completedAt:status === "completed" ? isoTime(item.updated_at) : null, status,
            conclusion:conclusions.has(item.conclusion) ? item.conclusion : null});
        }
        if (items.length < 100 || total === page * 100) return runs;
      }
      throw new Error("Workflow runs exceed query coverage");
    },
  };
}
