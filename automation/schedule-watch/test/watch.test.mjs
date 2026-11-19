import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {DatabaseSync} from "node:sqlite";
import test from "node:test";
import {slotsBetween} from "../src/slots.mjs";
import {matchRuns, slotState} from "../src/match.mjs";
import worker, {runWatch} from "../src/worker.mjs";

const at = Date.parse;
const hour = 3_600_000;
const time = (day, clock) => at(`2026-11-${day}T${clock}+09:00`);
const timing = JSON.parse(readFileSync(new URL("./timing.json", import.meta.url)));
const schema = readFileSync(new URL("../migrations/0001_init.sql", import.meta.url), "utf8");
const cron = {a:"0 10 * * *", b:"30 10 * * *", c:"37 5 */3 * *", d:"0 4 */3 * *"};
const target = id => ({id, label:`架空 ${id}`, repository:"sample-owner/sample-repo", workflow:`${id}.yml`, cron:cron[id]});
const run = (id, createdAt, extra={}) => ({id, createdAt, event:"schedule", branch:"main", ...extra});

function fixture(t, {status="active", reply=200, enabled=true, sends=true, realtime=true, records=[],
  readDelay=0, reservationDelay=0, transportFailures=0}={}) {
  const sql = new DatabaseSync(":memory:");
  t.after(() => sql.close());
  sql.exec(schema);
  const DB = {prepare(query) {
    const statement = sql.prepare(query);
    const bind = (...args) => ({
      first: async () => statement.get(...args) ?? null,
      all: async () => ({results:statement.all(...args)}),
      run: async () => ({meta:statement.run(...args)}),
    });
    return {...bind(), bind};
  }, async batch(statements) {
    sql.exec("BEGIN");
    try {
      const result = [];
      for (const statement of statements) result.push(await statement.run());
      sql.exec("COMMIT");
      if (reservationDelay && sql.prepare("SELECT count(*) AS n FROM outbox WHERE state='sending'").get().n)
        wall += reservationDelay;
      return result;
    } catch (error) {
      sql.exec("ROLLBACK");
      throw error;
    }
  }};
  const calls = [], messages = [];
  let workflowState = status;
  const env = {DB, WATCH_ENABLED:enabled, SEND_NOTICES:sends, REALTIME_NOTICES:realtime,
    WATCH_CONFIG:{targets:[{...target("a"),freshnessFields:["market"]}],
      freshness:{url:"https://freshness.example.invalid/state.json",fields:{market:"update"}}},
    GITHUB_READ_TOKEN:"fixture-only-read-token", SLACK_WEBHOOK_URL:"https://hooks.slack.com/services/TEST/ONLY/EXAMPLE"};
  const fetcher = async (url, options) => {
    const address = new URL(url);
    calls.push([address.hostname, options.method, options.headers]);
    if (address.hostname === "hooks.slack.com") {
      assert.ok(sql.prepare("SELECT count(*) AS n FROM outbox WHERE state='sending'").get().n>0);
      messages.push(JSON.parse(options.body).text);
      if (messages.length <= transportFailures) throw new Error("Synthetic transport failure");
      return new Response(reply === 200 ? "ok" : "fixture-only-read-token", {status:reply});
    }
    if (address.hostname === "freshness.example.invalid")
      return Response.json({update:"2026-11-20", other:"fixture-only-read-token"});
    assert.equal(address.hostname, "api.github.com");
    assert.equal(options.method, "GET");
    wall = now + readDelay;
    if (status === "unauthorized") return new Response("fixture-only-read-token",{status:401});
    if (address.pathname.endsWith("/runs")) {
      assert.equal(address.searchParams.get("event"),"schedule");
      assert.equal(address.searchParams.get("branch"),"main");
      return Response.json({workflow_runs:records.filter(r => (!r.workflow || address.pathname.endsWith("/" + r.workflow + ".yml/runs")) && r.createdAt <= now).map(r => ({
        id:r.id, created_at:new Date(r.createdAt).toISOString(), run_started_at:new Date(r.createdAt+3000).toISOString(),
        updated_at:new Date(r.createdAt+6000).toISOString(), event:r.event, head_branch:r.branch,
        status:"completed", conclusion:r.conclusion ?? "success", html_url:"fixture-only-read-token",
      }))});
    }
    return Response.json({state:workflowState, name:"fixture-only-read-token"});
  };
  let now, wall;
  return {sql, env, calls, messages, setWorkflowState(value) { workflowState = value; }, async tick(value) {
    now=wall=value; await runWatch(env,{now:value,clock:()=>wall,fetcher});
  }};
}

test("01 historical replay: all 30 were late and recovered at the recorded second", () => {
  const totals = {late:0, recovered:0, missed:0};
  for (const [id, expected, created, seconds] of timing.historical) {
    const plan = at(expected), creation = at(created);
    const [slot] = slotsBetween(cron[id],plan,plan);
    assert.equal(slot.plannedAt,plan);
    const observation = slotState(slot,null,plan+hour/2);
    totals.late += Number(observation === "late");
    const [match] = matchRuns([slot],[run(1,creation)],creation);
    totals.recovered += Number(slotState(slot,match,slot.nextAt) === "recovered");
    totals.missed += Number(slotState(slot,match,slot.nextAt) === "missed");
    assert.equal((match.createdAt-slot.plannedAt)/1000,seconds);
  }
  assert.deepEqual(totals,{late:30,recovered:30,missed:0});
});

test("02 at 21:58 there are three late slots and one recovered failure", () => {
  const now = time("19","21:58:39");
  const outcome = timing.snapshot.map(([id, expected, created]) => {
    const [slot] = slotsBetween(cron[id],at(expected),at(expected));
    const runs = created ? [run(1,at(created),{conclusion:"failure"})] : [];
    const [match] = matchRuns([slot],runs,now);
    return [slotState(slot,match,now),match?.conclusion ?? null];
  });
  assert.deepEqual(outcome,[["late",null],["late",null],["late",null],["recovered","failure"]]);
});

test("03 a missing slot goes from waiting to late to still missing to missed", async t => {
  const f=fixture(t,{realtime:false});
  const plan=time("19","19:00:00");
  const [slot]=slotsBetween(cron.a,plan,plan);
  assert.equal(slotState(slot,null,plan+hour/2-1),"waiting");
  assert.equal(slotState(slot,null,plan+hour/2),"late");
  assert.equal(slotState(slot,null,plan+12*hour-1),"late");
  assert.equal(slotState(slot,null,plan+12*hour),"still_missing");
  assert.equal(slotState(slot,null,slot.nextAt),"missed");
  await f.tick(plan+hour/2);
  await f.tick(time("20","08:00:00"));
  await f.tick(time("20","08:15:00"));
  await f.tick(time("20","19:00:00"));
  await f.tick(time("21","08:00:00"));
  await f.tick(time("21","08:15:00"));
  assert.equal(f.messages.filter(x=>/11-19 19:00.*まだ来ません/u.test(x)).length,1);
  assert.equal(f.messages.filter(x=>/11-19 19:00.*来ませんでした/u.test(x)).length,1);
  assert.equal(f.messages.length,2);
});

test("04 day-of-month cron resets on 31-day, 30-day and February boundaries", () => {
  for (const [end,next,expected] of [
    ["2026-01-31","2026-02-01",24],["2026-04-28","2026-05-01",72],
    ["2026-02-28","2026-03-01",24],["2028-02-28","2028-03-01",48],
  ]) {
    const [slot]=slotsBetween(cron.c,at(end),at(end)+24*hour-1);
    assert.equal(new Date(slot.nextAt).toISOString().slice(0,10),next);
    assert.equal((slot.nextAt-slot.plannedAt)/hour,expected);
  }
  assert.throws(()=>slotsBetween("0 10 * * 1",0,0),/cron/u);
});

test("05 replay of the same poll does not send twice, and the notice is stored before sending", async t => {
  const f=fixture(t);
  await f.tick(time("19","19:30:00"));
  await f.tick(time("19","19:30:00"));
  assert.equal(f.messages.length,1);
  assert.match(f.messages[0],/遅れています/u);
  assert.equal(f.sql.prepare("SELECT count(*) AS n FROM notice_items WHERE kind='late'").get().n,1);
});

test("06 failures use at most three attempts, and all attempts respect the ten-per-day cap", async t => {
  const f=fixture(t,{reply:503});
  for (const clock of ["19:30:00","19:30:00","19:45:00","20:00:00","20:15:00"])
    await f.tick(time("19",clock));
  assert.equal(f.messages.length,3);
  const g=fixture(t);
  g.env.WATCH_CONFIG.targets=Array.from({length:12},(_,i)=>({...target("a"),id:`t${i}`,workflow:`t${i}.yml`,cron:`${3*i} 10 * * *`}));
  for (let i=0;i<12;i++) await g.tick(time("19","19:30:00")+i*180_000);
  assert.equal(g.messages.length,10);
  await g.tick(time("20","08:00:00"));
  assert.match(g.messages.at(-1),/上限/u);
});

test("07 the quiet window starts at 22:00, and the morning digest reports the delayed run", async t => {
  const plan=time("19","21:30:00");
  const f=fixture(t,{records:[run(1,time("20","07:15:00"))]});
  f.env.WATCH_CONFIG.targets[0].cron="30 12 * * *";
  await f.tick(time("19","22:00:00"));
  await f.tick(time("20","06:59:59"));
  await f.tick(time("20","07:00:00"));
  assert.equal(f.messages.length,0);
  await f.tick(time("20","08:00:00"));
  await f.tick(time("20","08:15:00"));
  assert.equal(f.messages.length,1);
  assert.match(f.messages[0],/遅れて来ました.*9時間45分0秒/u);
  assert.match(f.messages[0],/market.*2026-11-20/u);
  await f.tick(time("21","08:00:00"));
  assert.equal(f.messages.filter(text=>/11-19 21:30.*遅れて来ました/u.test(text)).length,1);
});

test("08 a disabled workflow has no slot alerts and appears in the digest", async t => {
  const f=fixture(t,{status:"disabled_manually"});
  await f.tick(time("19","19:30:00"));
  assert.deepEqual(f.messages,[]);
  await f.tick(time("20","08:00:00"));
  assert.equal(f.messages.length,1);
  assert.match(f.messages[0],/止められています/u);
});

test("09 an unreadable GitHub endpoint reports only once per day and never marks a slot missing", async t => {
  const f=fixture(t,{status:"unauthorized"});
  await f.tick(time("19","19:30:00"));
  await f.tick(time("19","19:45:00"));
  assert.equal(f.messages.length,1);
  assert.match(f.messages[0],/GitHub を読めません/u);
  assert.equal(f.sql.prepare("SELECT count(*) AS n FROM slots").get().n,0);
});

test("10 one run belongs to only one slot and the earliest scheduled main run wins", () => {
  const start=time("19","19:00:00");
  const slots=slotsBetween(cron.a,start,start+24*hour);
  const runs=[run(4,start+25*hour),run(3,start+24*hour),run(2,start+6*hour),
    run(1,start+hour,{event:"workflow_dispatch"}),run(5,start+hour,{branch:"feature"})];
  assert.deepEqual(matchRuns(slots,runs,start+26*hour).map(r=>r?.id),[2,3]);
});

test("11 message and records omit secrets and remote text", async t => {
  const f=fixture(t,{records:[run(1,time("19","19:40:00"))]});
  await f.tick(time("19","19:30:00"));
  await f.tick(time("20","08:00:00"));
  assert.doesNotMatch(JSON.stringify(f.messages),/fixture-only-read-token|hooks\.slack\.com/u);
  const tables=f.sql.prepare("SELECT name FROM sqlite_schema WHERE type='table'").all();
  for (const {name} of tables)
    assert.doesNotMatch(JSON.stringify(f.sql.prepare(`SELECT * FROM "${name}"`).all()),/fixture-only-read-token|hooks\.slack\.com/u);
  assert.ok(f.calls.filter(x=>x[0]!=="api.github.com").every(x=>!x[2]?.Authorization));
});

test("12 default worker has only a scheduled entry and disabled settings touch nothing", async t => {
  const example = JSON.parse(readFileSync(new URL("../wrangler.jsonc.example",import.meta.url)));
  assert.equal(example.vars.WATCH_ENABLED,false);
  assert.equal(example.vars.SEND_NOTICES,false);
  assert.equal(example.observability.traces.enabled,false);
  assert.deepEqual(Object.keys(worker),["scheduled"]);
  const f=fixture(t,{enabled:false});
  await f.tick(time("19","19:30:00"));
  assert.deepEqual(f.calls,[]);
  await worker.scheduled({}, {WATCH_ENABLED:false});
  const g=fixture(t,{sends:false});
  await g.tick(time("19","19:30:00"));
  assert.ok(g.calls.some(x=>x[0]==="api.github.com"));
  assert.deepEqual(g.messages,[]);
});


test("explicit send rejection before quiet hours retries on the next eligible observation", async t => {
  const f=fixture(t,{reply:503});
  f.env.WATCH_CONFIG.targets[0].cron="15 12 * * *";
  await f.tick(time("19","21:45:00"));
  await f.tick(time("19","22:00:00"));
  await f.tick(time("20","07:00:00"));
  assert.equal(f.messages.length,2);
});

test("a later partial run listing does not announce a delay for an already observed run", async t => {
  const records=[run(1,time("19","19:20:00"))];
  const f=fixture(t,{records});
  await f.tick(time("19","19:20:00"));
  records.length=0;
  await f.tick(time("19","19:30:00"));
  assert.deepEqual(f.messages,[]);
});

test("configuration errors never display the configured webhook or token", async t => {
  const f=fixture(t);
  f.env.SLACK_WEBHOOK_URL="invalid-fixture-secret";
  await assert.rejects(f.tick(time("19","19:30:00")), error => {
    assert.doesNotMatch(JSON.stringify(error,{}) + String(error) + (error.input ?? ""),/invalid-fixture-secret/u);
    return true;
  });
  assert.deepEqual(f.calls,[]);
});


test("all 30 historical slots also pass the scheduled worker and outbox in order", async t => {
  const history=timing.historical.map(([id,expected,created,seconds],index) => ({
    target:id,expected:at(expected),created:at(created),seconds,id:index+1,
  }));
  const f=fixture(t,{records:history.map(row=>run(row.id,row.created,{workflow:row.target}))});
  f.env.WATCH_CONFIG.targets=["a","b","c"].map(target);
  const ticks=history.flatMap(row=>[row.expected+hour/2,row.created]).sort((a,b)=>a-b);
  for (const tick of ticks) await f.tick(tick);
  assert.equal(f.sql.prepare("SELECT count(*) AS n FROM notice_items WHERE kind='late'").get().n,30);
  assert.equal(f.messages.filter(text=>text.includes("遅れています") && !text.includes("朝のまとめ")).length,30);
  const record=f.sql.prepare("SELECT state,created_at FROM slots WHERE target_id=? AND planned_at=?");
  for (const row of history) {
    const actual=record.get(row.target,row.expected);
    assert.equal(actual.state,"recovered");
    assert.equal((actual.created_at-row.expected)/1000,row.seconds);
  }
});

test("a stopped workflow also suppresses an outstanding immediate retry", async t => {
  const f=fixture(t,{reply:503});
  f.env.WATCH_CONFIG.targets[0].cron="15 12 * * *";
  await f.tick(time("19","21:45:00"));
  f.setWorkflowState("disabled_inactivity");
  await f.tick(time("20","07:00:00"));
  assert.equal(f.messages.length,1);
});

test("freshness is recorded separately, including targets without a public freshness indicator", async t => {
  const f=fixture(t);
  f.env.WATCH_CONFIG.targets[0].freshnessFields=["market"];
  f.env.WATCH_CONFIG.targets.push(target("b"));
  await f.tick(time("20","08:00:00"));
  assert.match(f.messages[0],/market 2026-11-20/u);
  assert.match(f.messages[0],/架空 b.*対象外/u);
  assert.equal(f.sql.prepare("SELECT value FROM freshness WHERE field='target:b'").get().value,"対象外");
});

test("review 1: morning digests retry transport errors up to three attempts", async t => {
  const f=fixture(t,{transportFailures:2});
  for (const clock of ["08:00:00","08:00:00","08:15:00","08:30:00","08:45:00"])
    await f.tick(time("21",clock));
  assert.equal(f.messages.length,3);
  assert.equal(new Set(f.messages).size,1);
  const digest=f.sql.prepare("SELECT attempts,state FROM outbox WHERE kind='digest'").get();
  assert.deepEqual({...digest},{attempts:3,state:"sent"});
  const terminal=fixture(t,{transportFailures:9});
  for (const clock of ["08:00:00","08:15:00","08:30:00","08:45:00"])
    await terminal.tick(time("21",clock));
  assert.equal(terminal.messages.length,3);
  assert.equal(terminal.sql.prepare("SELECT state FROM outbox WHERE kind='digest'").get().state,"failed");
  const immediate=fixture(t,{transportFailures:2});
  await immediate.tick(time("21","19:30:00"));
  await immediate.tick(time("21","19:45:00"));
  assert.equal(immediate.messages.length,1);
  assert.equal(immediate.sql.prepare("SELECT state FROM outbox WHERE kind='realtime'").get().state,"uncertain");
});

test("review 2: crossing 22:00 during a poll defers sending and uses the next day's budget", async t => {
  for (const delays of [{readDelay:2000},{reservationDelay:2000}]) {
    await t.test(Object.keys(delays)[0],async subtest=>{
      const f=fixture(subtest,delays);
      await f.tick(time("19","21:59:59"));
      assert.equal(f.messages.length,0);
      const before=f.sql.prepare("SELECT attempts,state FROM outbox").get();
      assert.deepEqual({...before},{attempts:0,state:"pending"});
      assert.equal(f.sql.prepare("SELECT attempts FROM deliveries WHERE day='2026-11-19'").get()?.attempts ?? 0,0);
      await f.tick(time("20","07:00:00"));
      assert.equal(f.messages.length,1);
      assert.equal(f.sql.prepare("SELECT attempts FROM deliveries WHERE day='2026-11-20'").get().attempts,1);
    });
  }
});

test("review 3: recovery after the morning digest appears once the next morning", async t => {
  const f=fixture(t,{realtime:false,records:[run(111,time("21","09:10:00"),{conclusion:"failure"})]});
  await f.tick(time("20","19:30:00"));
  await f.tick(time("21","08:00:00"));
  assert.match(f.messages[0],/11-20 19:00.*まだ来ません/u);
  await f.tick(time("21","09:15:00"));
  assert.equal(f.sql.prepare("SELECT state FROM slots WHERE planned_at=?").get(time("20","19:00:00")).state,"recovered");
  await f.tick(time("22","08:00:00"));
  await f.tick(time("22","08:15:00"));
  await f.tick(time("23","08:00:00"));
  assert.equal(f.messages.filter(text=>/11-20 19:00.*遅れて来ました.*14時間10分0秒.*失敗/u.test(text)).length,1);
  assert.match(f.messages[1],/11-20 19:00.*遅れて来ました.*14時間10分0秒.*失敗/u);
});
