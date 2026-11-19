import {day,hour,jstDate,jstStart,jstTime,minute} from "./slots.mjs";

const states = {
  waiting:"待っています", late:"遅れています", recovered:"遅れて来ました",
  still_missing:"まだ来ません", missed:"来ませんでした", on_time:"予定どおり",
};
const results = {success:"成功", failure:"失敗", skipped:"スキップ", cancelled:"取り消し", timed_out:"時間切れ"};
export const stmt = (db, sql, ...bindings) => db.prepare(sql).bind(...bindings);
export const all = async (db, sql, ...bindings) => (await stmt(db,sql,...bindings).all()).results;

export const daytime = now => now - jstStart(now) >= 7 * hour && now - jstStart(now) < 22 * hour;
export const morning = now => now - jstStart(now) >= 8 * hour && now - jstStart(now) < 9 * hour;
const duration = elapsed => {
  const seconds = Math.max(0, Math.floor(elapsed/1000));
  return `${Math.floor(seconds/3600)}時間${Math.floor(seconds/60)%60}分${seconds%60}秒`;
};
const runLink = (target,id) => id ? ` https://github.com/${target.repository}/actions/runs/${id}` : "";
export function slotLine(target, slot, now) {
  const headline = `${target.label} ${jstTime(slot.planned_at)} 予定 JST — ${states[slot.state]}`;
  const elapsed = slot.created_at === null ? now - slot.planned_at : slot.created_at - slot.planned_at;
  const timing = slot.state === "on_time" ? "" : ` (${duration(elapsed)})`;
  const result = results[slot.conclusion] ?? slot.conclusion ?? slot.run_status;
  return headline + timing + (result ? ` ・${result}` : "") + runLink(target,slot.run_id);
}

export async function enqueue(db, id, kind, now, items) {
  if (!items.length) return;
  const nonce = crypto.randomUUID();
  await db.batch([
    stmt(db,"INSERT OR IGNORE INTO outbox (id,kind,local_day,nonce,created_at,next_attempt) VALUES (?,?,?,?,?,?)",
      id,kind,jstDate(now),nonce,now,now),
    ...items.map(item => stmt(db,`INSERT OR IGNORE INTO notice_items (id,kind,target_id,outbox_id,line)
      SELECT ?,?,?,?,? WHERE EXISTS (SELECT 1 FROM outbox WHERE id=? AND nonce=?)`,
      item.id,item.kind,item.targetId ?? null,id,item.line,id,nonce)),
    stmt(db,`DELETE FROM outbox WHERE id=? AND nonce=? AND NOT EXISTS
      (SELECT 1 FROM notice_items WHERE outbox_id=?)`,id,nonce,id),
  ]);
}

export async function digestItems(db, targets, now) {
  const today = jstStart(now), yesterday = today - day, dayKey = jstDate(now);
  const items = [{id:`heading:${dayKey}`,kind:"digest",line:`定時処理の朝のまとめ（${jstDate(yesterday)} JST）`}];
  const byId = new Map(targets.map(target => [target.id,target]));
  const cached = new Map((await all(db,"SELECT target_id,state FROM workflow_states")).map(row=>[row.target_id,row.state]));
  const rows = await all(db,`SELECT * FROM slots WHERE (planned_at>=? AND planned_at<?)
    OR (state='missed' AND next_at>=? AND next_at<=?)
    OR (state='still_missing' AND planned_at+?<=?) ORDER BY
    CASE state WHEN 'missed' THEN 0 WHEN 'still_missing' THEN 1 ELSE 2 END, planned_at,target_id`,
    yesterday,today,yesterday,now,12*hour,now);
  for (const row of rows) {
    const target = byId.get(row.target_id);
    if (!target || cached.get(row.target_id) !== "active") continue;
    const once = row.state === "missed" || row.state === "still_missing";
    const kind = once ? row.state : "digest";
    items.push({id:`${kind}:${once ? "" : dayKey}:${target.id}:${row.planned_at}`,kind,line:slotLine(target,row,now)});
  }
  for (const target of targets) {
    const state = cached.get(target.id);
    if (state && state !== "active")
      items.push({id:`disabled:${dayKey}:${target.id}`,kind:"digest",line:`${target.label} は止められています。`});
  }
  const unmatched = await all(db,"SELECT * FROM unmatched_runs WHERE created_at>=? AND created_at<? ORDER BY created_at,run_id",yesterday,today);
  for (const row of unmatched) {
    const target = byId.get(row.target_id);
    if (target) items.push({id:`unmatched:${target.id}:${row.run_id}`,kind:"digest",
      line:`${target.label} ${jstTime(row.created_at)} 予定に無い実行` + runLink(target,row.run_id)});
  }
  const fresh = await all(db,`SELECT f.field, f.value FROM freshness f JOIN
    (SELECT field,max(observed_at) AS observed_at FROM freshness WHERE observed_at>=? GROUP BY field) last
    ON f.field=last.field AND f.observed_at=last.observed_at ORDER BY f.field`,today);
  for (const row of fresh) {
    const label = row.field.startsWith("target:") ? byId.get(row.field.slice(7))?.label : row.field;
    if (label) items.push({id:`fresh:${dayKey}:${row.field}`,kind:"digest",line:`公開の鮮度 ${label} ${row.value}`});
  }
  const errors = await all(db,"SELECT day FROM read_errors WHERE day IN (?,?) ORDER BY day",jstDate(yesterday),dayKey);
  const unread = errors.at(-1);
  if (unread) items.push({id:`read-error:${unread.day}`,kind:"read_error",line:"見張りが GitHub を読めません。"});
  const cap = await stmt(db,"SELECT capped FROM deliveries WHERE day=?",jstDate(yesterday)).first();
  if (cap?.capped) items.push({id:`cap:${dayKey}`,kind:"digest",line:"前日は知らせの上限に当たりました。"});
  return items;
}

export async function deliver(db, fetcher, webhook, realtime, now) {
  if (!daytime(now)) return;
  const today = jstDate(now);
  const pending = await all(db,`SELECT id FROM outbox WHERE state='pending' AND next_attempt<=?
    AND ((kind='digest' AND local_day=?) OR (kind='realtime' AND ?=1
      AND (local_day=? OR (attempts>0 AND created_at>=?))))
    ORDER BY CASE kind WHEN 'digest' THEN 0 ELSE 1 END,created_at,id LIMIT 11`,
    now,today,Number(realtime),today,now-day);
  for (const {id} of pending) {
    const items = await all(db,`SELECT line FROM notice_items WHERE outbox_id=? AND (kind<>'late' OR
      EXISTS (SELECT 1 FROM workflow_states WHERE target_id=notice_items.target_id AND state='active')) ORDER BY rowid`,id);
    if (!items.length) {
      await stmt(db,"UPDATE outbox SET state='suppressed' WHERE id=? AND state='pending'",id).run();
      continue;
    }
    const claim = crypto.randomUUID();
    const [,reservation] = await db.batch([
      stmt(db,"INSERT OR IGNORE INTO deliveries(day) VALUES (?)",today),
      stmt(db,`UPDATE outbox SET state='sending',attempts=attempts+1,claim=?
        WHERE id=? AND state='pending' AND next_attempt<=? AND attempts<3
        AND (SELECT attempts FROM deliveries WHERE day=?)<10`,claim,id,now,today),
      stmt(db,`UPDATE deliveries SET attempts=attempts+1 WHERE day=? AND EXISTS
        (SELECT 1 FROM outbox WHERE id=? AND claim=?)`,today,id,claim),
      stmt(db,`UPDATE deliveries SET capped=1 WHERE day=? AND attempts>=10 AND EXISTS
        (SELECT 1 FROM outbox WHERE id=? AND state='pending')`,today,id),
      stmt(db,`UPDATE outbox SET state='capped' WHERE id=? AND state='pending'
        AND (SELECT capped FROM deliveries WHERE day=?)=1`,id,today),
    ]);
    if (Number(reservation.meta.changes) !== 1) continue;
    let state;
    try {
      const response = await fetcher(webhook,{method:"POST",redirect:"error",signal:AbortSignal.timeout(8_000),
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({text:items.map(item=>item.line).join("\n"),mrkdwn:false,unfurl_links:false,unfurl_media:false})});
      state = response.ok ? "sent" : "pending";
      await response.body?.cancel();
    } catch {
      // A network failure may have happened after Slack accepted the POST.
      state = "uncertain";
    }
    await stmt(db,`UPDATE outbox SET claim=NULL,next_attempt=?,
      state=CASE WHEN ?='pending' AND attempts>=3 THEN 'failed' ELSE ? END WHERE id=? AND claim=?`,
      now+15*minute,state,state,id,claim).run();
  }
}
