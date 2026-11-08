# Reviewed public SQLite foundation (disabled by default)

LP source review does not by itself protect the publicly distributed SQLite DB.
This opt-in path collects into a private DB outside Git and copies reviewed
facts and independently reviewed acquisition/detail links into the public DB.
It reuses the existing fixed-ID registry, source map, publication hashes and Git
review, without another approval ledger or reviewer authentication mechanism.

## Initial deployment

EVENTS_SQLITE_REVIEW_GATED_VENUES is empty and Ariake dated_sessions remains
false. This deployment changes no event, ID, source map, publication policy,
schedule, SQLite schema or legacy public field. Activation and data adoption
require a separately reviewed, coherent data change.

## Opt-in operation

- Collect a private copy with --db-path and --skip-artist-inference. Dated
  collection rejects public-checkout targets and aliases of the public DB.
- Infer privately with explicit --db-path and --output. Run reviewed_events_db
  before any public Git commit. Require active fixed IDs, exact observations,
  source choices and reviewed publication hashes; ID registration alone is not
  approval. Stale/missing choices hold a row; malformed map/registry stops.
- Project approved facts and both reviewed URLs into the existing SQLite columns.
  New description, performers and capacity are NULL. Keep held old rows verbatim
  and other venues' normal updates. Missing source rows do not imply cancellation.
- A same-identity/source withdrawal changes only old status metadata. Ambiguous
  withdrawals stop. An old review cannot reinstate a cancelled/postponed event;
  reinstatement needs an explicit Git-reviewed data correction.
- Generate public CSV with --skip-events-sync. The common inference writer also
  protects dated venues in the canonical public DB and its aliases, including
  the monthly artist workflow. Private inference continues normally.
- Every dated venue in the candidate DB must be explicitly gated. Gated venue
  metadata retains its prior public value and needs separate review. The Git CSV
  is the collector configuration, rather than retained DB metadata.

## Concurrency and recovery

The projector reuses registry_lock(output), checks input/output hashes, rejects
non-checkpointed WALs and aliases, and replaces only a complete temporary DB.
This is not a general CAS against arbitrary writers: retain Actions repo-write
concurrency and exclude simultaneous manual writes. Verify that no writer is
running before recovering a stale lock after interruption.

The opt-in workflow pins its starting main SHA and never rebases its projection
onto a different generation. A changed remote or rejected push stops it; collect
and review again from the new tip. The default legacy path retains its existing
rebase behavior.

For this disabled deployment, revert code/workflow changes if needed; data and
ID history are unchanged. After future data adoption, preserve adopted IDs,
saved days and acceptance history, and use the existing correction and coherent
asset-distribution procedures rather than reverting the registry wholesale.

Before activation, review public SQLite consumer impact: held observations will
no longer be distributed for the chosen venue and reviewed changes have NULL
prose fields. Preserve unrelated legacy rows. Never upload private collection
DBs, HTML, synthetic fixtures or simulated approvals to Git or Release.
