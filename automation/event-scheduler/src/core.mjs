/** No network or credentials in this module. SQLite statements are atomic. */
export function latestSlot(ms) {
  if (!Number.isFinite(ms)) throw Error('invalid time');
  const date = new Date(ms);
  date.setUTCHours(4, 0, 0, 0);
  if (date.getTime() > ms) date.setUTCDate(date.getUTCDate() - 1);
  while ((date.getUTCDate() - 1) % 3 !== 0) date.setUTCDate(date.getUTCDate() - 1);
  return date.toISOString();
}
export class SqlStore {
  constructor(sql) {
    this.sql = sql;
    sql.exec(`CREATE TABLE IF NOT EXISTS slots (
      slot TEXT PRIMARY KEY, nonce TEXT NOT NULL, dispatch_state TEXT NOT NULL,
      run_id TEXT, admitted INTEGER NOT NULL DEFAULT 0, execution_state TEXT,
      created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)`);
  }
  get(slot) { return this.sql.exec('SELECT * FROM slots WHERE slot = ?', slot).toArray()[0] ?? null; }
  unresolved() { return this.sql.exec("SELECT * FROM slots WHERE execution_state IS NULL OR execution_state = 'running' ORDER BY slot").toArray(); }
  intent(slot, nonce, now) {
    return this.sql.exec("INSERT INTO slots(slot, nonce, dispatch_state, created_at, updated_at) VALUES (?, ?, 'intent', ?, ?) ON CONFLICT DO NOTHING RETURNING slot", slot, nonce, now, now).toArray().length === 1;
  }
  dispatchResult(slot, nonce, runId, now) {
    const row = this.get(slot);
    if (!row || row.nonce !== nonce) throw Error('slot mismatch');
    if (runId && row.run_id && row.run_id !== String(runId)) {
      this.sql.exec("UPDATE slots SET dispatch_state = 'conflict', execution_state = 'conflict', updated_at = ? WHERE slot = ?", now, slot);
      return this.get(slot);
    }
    this.sql.exec('UPDATE slots SET dispatch_state = ?, run_id = COALESCE(run_id, ?), updated_at = ? WHERE slot = ?', runId ? 'accepted' : 'uncertain', runId ? String(runId) : null, now, slot);
    return this.get(slot);
  }
  admit(slot, nonce, runId, attempt, event, now) {
    if (event !== 'workflow_dispatch' || attempt !== '1' || !/^\d+$/.test(runId)) return {allowed:false, reason:'event_or_attempt'};
    const row = this.get(slot);
    if (!row || row.nonce !== nonce || !['intent','uncertain','accepted'].includes(row.dispatch_state)) return {allowed:false, reason:'unknown_dispatch'};
    if (row.execution_state && row.execution_state !== 'running') return {allowed:false, reason:'terminal'};
    if (row.run_id && row.run_id !== runId) return {allowed:false, reason:'different_run'};
    this.sql.exec("UPDATE slots SET run_id = ?, admitted = 1, execution_state = 'running', updated_at = ? WHERE slot = ?", runId, now, slot);
    return {allowed:true, reason:'admitted'};
  }
  terminal(slot, status, now) {
    const row = this.get(slot);
    if (!row) throw Error('missing slot');
    this.sql.exec('UPDATE slots SET execution_state = ?, updated_at = ? WHERE slot = ?', row.admitted ? status : 'not_admitted', now, slot);
    return this.get(slot);
  }
}
export class Scheduler {
  constructor(store, github, config) { this.store=store; this.github=github; this.config=config; }
  async tick(now) {
    if (this.config.enabled !== true || !Number.isFinite(this.config.cutoverAt)) return {state:'disabled'};
    for (const row of this.store.unresolved()) {
      if (row.run_id) {
        try {
          const run=await this.github.run(row.run_id);
          if (run.status === 'completed') this.store.terminal(row.slot, run.conclusion ?? 'unknown', now);
        } catch { return {state:'reconciliation_unconfirmed', slot:row.slot}; }
      }
    }
    const slot=latestSlot(now), expected=Date.parse(slot);
    if (expected < this.config.cutoverAt || now-expected >= 4*3600000) return {state:'outside_window', slot};
    const existing=this.store.get(slot);
    if (existing) return existing;
    if (this.store.unresolved().length) return {state:'previous_slot_unresolved', slot};
    let safe;
    try { safe=await this.github.preflight(); } catch { safe=false; }
    if (!safe) return {state:'preflight_blocked', slot};
    // Re-check after async preflight: another tick may have acquired a slot.
    if (this.store.get(slot)) return this.store.get(slot);
    if (this.store.unresolved().length) return {state:'previous_slot_unresolved', slot};
    const nonce=this.config.nonce();
    if (!this.store.intent(slot, nonce, now)) return this.store.get(slot);
    try {
      const response=await this.github.dispatch(slot,nonce);
      if (!Number.isSafeInteger(response.workflow_run_id) || response.workflow_run_id <= 0) throw Error('missing run id');
      return this.store.dispatchResult(slot,nonce,response.workflow_run_id,now);
    } catch { return this.store.dispatchResult(slot,nonce,null,now); }
  }
}
