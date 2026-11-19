import {day,jstDate,jstStart,parseCron,slotsBetween} from "./slots.mjs";
import {delayThreshold,matchRuns,scheduledRuns,slotState} from "./match.mjs";
import {getJson,githubReader} from "./github.mjs";
import {daytime,deliver,digestItems,enqueue,morning,slotLine,stmt} from "./notify.mjs";

function httpsUrl(value) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error("Invalid watch URL");
  }
  if (url.protocol !== "https:" || url.username || url.password || url.hash) throw new Error("Invalid watch URL");
  return url;
}
function readConfig(value) {
  let config;
  try {
    config = typeof value === "string" ? JSON.parse(value) : value;
  } catch {
    throw new Error("Invalid watch configuration");
  }
  const targets = config?.targets;
  if (!Array.isArray(targets) || !targets.length || targets.length > 12) throw new Error("Invalid watch targets");
  const ids = new Set();
  for (const target of targets) {
    if (typeof target.id !== "string" || !/^[a-z0-9_-]{1,48}$/.test(target.id) || ids.has(target.id) ||
        typeof target.label !== "string" || !target.label.trim() || target.label.length > 80 || /[\r\n<>]/.test(target.label) ||
        typeof target.repository !== "string" || !/^[a-z0-9_-]+\/[a-z0-9_-][a-z0-9_.-]*$/i.test(target.repository) ||
        typeof target.workflow !== "string" || !/^([a-z0-9_-][a-z0-9_.-]*\.ya?ml|[1-9]\d*)$/i.test(target.workflow))
      throw new Error("Invalid watch target");
    if (target.freshnessFields !== undefined && (!Array.isArray(target.freshnessFields) ||
        !target.freshnessFields.every(field => typeof field === "string" && /^[a-z0-9_-]{1,48}$/.test(field) &&
          typeof config.freshness?.fields?.[field] === "string"))) throw new Error("Invalid freshness fields");
    ids.add(target.id);
    parseCron(target.cron);
  }
  return config;
}

async function observeTarget(db, github, target, now) {
  const today = jstDate(now);
  const cached = await stmt(db,"SELECT state,checked_day FROM workflow_states WHERE target_id=?",target.id).first();
  let state, slots, runs;
  try {
    state = cached?.checked_day === today ? cached.state : await github.state(target);
    if (state === "active") {
      const yesterday = jstStart(now) - day;
      slots = slotsBetween(target.cron,yesterday-32*day,now).filter(slot=>slot.nextAt>=yesterday);
      runs = slots.length ? await github.runs(target,slots[0].plannedAt,now) : [];
    }
  } catch {
    await stmt(db,"INSERT OR IGNORE INTO read_errors(day) VALUES (?)",today).run();
    return {unread:true};
  }
  if (cached?.checked_day !== today) {
    await stmt(db,`INSERT INTO workflow_states VALUES (?,?,?,?) ON CONFLICT(target_id)
      DO UPDATE SET state=excluded.state,checked_day=excluded.checked_day,checked_at=excluded.checked_at
      WHERE excluded.checked_at>=workflow_states.checked_at`,target.id,state,today,now).run();
  }
  if (state !== "active" || !slots.length) return {};
  const matches = matchRuns(slots,runs,now);
  const rows = slots.map((slot,index) => {
    const run = matches[index];
    return {planned_at:slot.plannedAt,next_at:slot.nextAt,state:slotState(slot,run,now),run_id:run?.id ?? null,
      created_at:run?.createdAt ?? null,started_at:run?.startedAt ?? null,completed_at:run?.completedAt ?? null,
      run_status:run?.status ?? null,conclusion:run?.conclusion ?? null};
  });
  const matched = new Set(matches.filter(Boolean).map(run=>run.id));
  const extras = scheduledRuns(runs,now).filter(run=>!matched.has(run.id));
  await db.batch([
    ...rows.map(row=>stmt(db,`INSERT INTO slots VALUES (?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(target_id,planned_at) DO UPDATE SET observed_at=excluded.observed_at,state=excluded.state,
      next_at=excluded.next_at,run_id=excluded.run_id,created_at=excluded.created_at,started_at=excluded.started_at,
      completed_at=excluded.completed_at,run_status=excluded.run_status,conclusion=excluded.conclusion
      WHERE excluded.observed_at>=slots.observed_at AND (slots.run_id IS NULL OR
        excluded.created_at<slots.created_at OR (excluded.created_at=slots.created_at AND excluded.run_id<=slots.run_id))`,
      target.id,row.planned_at,row.next_at,now,row.state,row.run_id,row.created_at,row.started_at,row.completed_at,row.run_status,row.conclusion)),
    ...extras.map(run=>stmt(db,"INSERT OR IGNORE INTO unmatched_runs VALUES (?,?,?)",target.id,run.id,run.createdAt)),
  ]);
  const current = rows.at(-1);
  if (current.state !== "late" || !daytime(current.planned_at+delayThreshold)) return {};
  const recorded = await stmt(db,"SELECT * FROM slots WHERE target_id=? AND planned_at=?",target.id,current.planned_at).first();
  return {late:recorded?.state === "late" ? recorded : null};
}

async function observeFreshness(db, fetcher, config, targets, now) {
  const reading = (field,value) => stmt(db,"INSERT OR IGNORE INTO freshness VALUES (?,?,?)",field,now,value);
  const fields = new Set(targets.flatMap(target=>target.freshnessFields ?? []));
  const readings = targets.filter(target=>!target.freshnessFields?.length).map(target=>reading("target:"+target.id,"対象外"));
  let body;
  if (fields.size) {
    try {
      body = await getJson(fetcher,httpsUrl(config.url));
    } catch {
      // Freshness is evidence only. Keep recording which targets have no indicator.
    }
  }
  for (const field of fields) {
    const value = config.fields[field].split(".").reduce((obj,key)=>Object.hasOwn(obj ?? {},key) ? obj[key] : undefined,body);
    if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z|[+-]\d{2}:\d{2}))?$/.test(value) &&
        Number.isFinite(Date.parse(value))) readings.push(reading(field,value));
  }
  if (readings.length) await db.batch(readings);
}

const enabled = value => value === true || value === "true";
export async function runWatch(env, {now,fetcher=fetch}) {
  if (!enabled(env.WATCH_ENABLED)) return;
  const {targets,freshness} = readConfig(env.WATCH_CONFIG);
  const {DB:db} = env;
  const send = enabled(env.SEND_NOTICES);
  const realtime = enabled(env.REALTIME_NOTICES);
  let webhook;
  if (send) {
    webhook = httpsUrl(env.SLACK_WEBHOOK_URL);
    if (webhook.host !== "hooks.slack.com" || !/^\/services\/[\w-]+\/[\w-]+\/[\w-]+$/.test(webhook.pathname) || webhook.search)
      throw new Error("Invalid notice destination");
  }
  const github = githubReader(fetcher,env.GITHUB_READ_TOKEN ?? "");
  const items = [];
  const today = jstDate(now);
  for (const target of targets) {
    const result = await observeTarget(db,github,target,now);
    if (result.unread) items.push({id:`read-error:${today}`,kind:"read_error",line:"見張りが GitHub を読めません。"});
    if (result.late) items.push({id:`late:${target.id}:${result.late.planned_at}`,kind:"late",targetId:target.id,
      line:slotLine(target,result.late,now)});
  }
  await observeFreshness(db,fetcher,freshness,targets,now);
  if (!send) return;
  if (morning(now)) await enqueue(db,`digest:${today}`,"digest",now,await digestItems(db,targets,now));
  if (realtime && daytime(now)) await enqueue(db,`realtime:${now}`,"realtime",now,items);
  await deliver(db,fetcher,webhook,realtime,now);
}

export default {
  async scheduled(controller,env) {
    await runWatch(env,{now:Date.now()});
  },
};
