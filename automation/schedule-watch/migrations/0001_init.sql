CREATE TABLE workflow_states (
  target_id TEXT PRIMARY KEY,
  state TEXT NOT NULL,
  checked_day TEXT NOT NULL,
  checked_at INTEGER NOT NULL
);
CREATE TABLE slots (
  target_id TEXT NOT NULL,
  planned_at INTEGER NOT NULL,
  next_at INTEGER NOT NULL,
  observed_at INTEGER NOT NULL,
  state TEXT NOT NULL,
  run_id INTEGER,
  created_at INTEGER,
  started_at INTEGER,
  completed_at INTEGER,
  run_status TEXT,
  conclusion TEXT,
  PRIMARY KEY (target_id, planned_at)
);
CREATE INDEX slots_by_time ON slots(planned_at);
CREATE INDEX slots_by_state ON slots(state, next_at);
CREATE TABLE unmatched_runs (
  target_id TEXT NOT NULL,
  run_id INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (target_id, run_id)
);
CREATE INDEX unmatched_by_time ON unmatched_runs(created_at);
CREATE TABLE freshness (
  field TEXT NOT NULL,
  observed_at INTEGER NOT NULL,
  value TEXT NOT NULL,
  PRIMARY KEY (field, observed_at)
);
CREATE TABLE read_errors (
  day TEXT PRIMARY KEY
);
CREATE TABLE outbox (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  local_day TEXT NOT NULL,
  nonce TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  next_attempt INTEGER NOT NULL,
  state TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  claim TEXT
);
CREATE INDEX outbox_ready ON outbox(local_day, state, next_attempt);
CREATE TABLE notice_items (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  target_id TEXT,
  outbox_id TEXT NOT NULL REFERENCES outbox(id),
  line TEXT NOT NULL
);
CREATE INDEX notice_items_by_message ON notice_items(outbox_id);
CREATE TABLE deliveries (
  day TEXT PRIMARY KEY,
  attempts INTEGER NOT NULL DEFAULT 0,
  capped INTEGER NOT NULL DEFAULT 0
);
