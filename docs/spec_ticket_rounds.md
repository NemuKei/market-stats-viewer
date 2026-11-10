# Ticket rounds: isolated preview contract v1

## Scope

Ticket application/result/payment facts are separate from event rows and saved
schedule days. The optional asset is `ticket_rounds.json`; consumer publication
path is `/data/event_ticket_rounds.json`. No production ledger or real ticket
facts are supplied in this change. Synthetic fixtures are not announcements.
No live setting, collector, Release, DB or published event data is changed.
The release workflow gains an opt-in path, disabled unless the repository
variable TICKET_ROUNDS_ENABLED is explicitly true. No variable is changed here.

## Reviewed ledger and generation

Ledger exact keys: `schema_version: 1`, `rounds`, `links`, `review`, `history`.
Review exact keys: `status: reviewed`, `facts_sha256`, `reviewed_at_utc`.
The hash is SHA-256 of UTF-8 JSON `{rounds,links}`, sorted keys, no whitespace,
non-ASCII preserved. It detects changes after review, not proof of truth,
authentication or permission. Human review must verify official public content,
applicability to each individual show, cancellation/postponement, and all facts.
Do not use login-only pages, personal lottery results, article text or images.

`python -m scripts.build_ticket_rounds --ledger REVIEWED.json --events lp_events_all.json --output PREVIEW/ticket_rounds.json --generated-at-utc UTC`

Validation completes before atomic output replacement. Inputs cannot be output.
No network, DB, registry or event write occurs. Existing public generation is
preserved on validation failure. Explicit `--include-ticket-rounds` on
`build_external_events_manifest` validates the optional file against the exact
LP bytes and adds its hash and size. Merely finding a file does not publish it.
Existing manifest behavior is unchanged when the option is absent.

## Public contract

Root exact keys: `schema_version`, `generated_at_utc`,
`event_generation_sha256` (SHA-256 of exact all-dates LP bytes), `rounds`, `links`.

Round exact keys: `ticket_round_id`, `title`, `sale_method` (lottery/first_come/
unknown), `round_type` (fan_club/general/upgrade/other), `eligibility_label`,
`status` (active/postponed/cancelled), positive integer `revision`,
`first_seen_at_utc`, `last_verified_at_utc`, `milestones`.
IDs are reviewed opaque stable identifiers, never derived from changing dates
or URLs. Corrections keep ID and increment revision. The ledger retains prior reviewed snapshots in append-only `history`. Full-chain
validation rejects removed round IDs, first-seen changes, backward verification
or review timestamps, and changed facts/links without exactly one revision
increment. New IDs begin at revision 1. History is not included in the public
asset. Git-reviewed history is the audit record, not an authenticated signature.

Milestone exact keys: `kind` (application_open/application_close/results/
payment_deadline), `knowledge_status` (confirmed/unannounced/unverified/
not_applicable/conflict), `precision` (date/time/range/null), `date`, `time`,
`end_date`, `end_time`, `timezone` (Asia/Tokyo), `source`.
One of each kind per round. Dates YYYY-MM-DD and times HH:MM. Date-only has null
time, not midnight. Ranges have matching precision at both ends. Unknown states
have null dates, times and precision. Missing text is unverified, never evidence
of unannounced. Confirmed/unannounced requires official source. First-come
results must be not_applicable. One source record: HTTPS `url`, `name`,
`source_class` (venue_official/artist_official/promoter_official/ticket_official),
`checked_at_utc`. Classification is a review assertion, not automatic trust in
an arbitrary hostname. Source check <= round verification <= generation.

Links exact keys: `ticket_round_id`, `event_uid`. Every round has at least one
link. Each link must resolve to an existing individual LP `event_key`; duplicate
pairs, duplicate IDs, unresolved IDs and saved-day associations are rejected.
One round can cover two performances without inflating event counts. Event
merge/split needs renewed explicit applicability review, never title matching.

## Consumer safety and staged rollout

Consumer validates exact field sets, HTTPS URLs, dates and event-generation
binding before rendering. Missing/bad/stale sidecar suppresses ticket details
only, not the existing event calendar. No implicit interpretation as empty,
cancelled or removed facts. Check ticket and event acceptance independently.

Before production: review ledger/history and official source facts, review
matching generation/hash, validate consumer accepted-snapshot integration, test
combined adoption and rollback, then obtain deployment approval. The opt-in
producer path builds from lp_events_all, validates it in manifest generation
and final validation, and uploads only a successful sidecar. Failure emits a
separate warning and omits it from the new manifest; an old leftover release
asset is not authority to use stale tickets. This change is
not a claim that any live data or scheduled collector supports ticket rounds.

Tests cover one round/two shows, unknown states, date-only and range precision,
first-come results, malformed/source/private fields, broken links, review hash,
generation mismatch, optional manifest and input immutability. Tests also cover review history across revisions; deployed generation
promotion remains a preproduction acceptance gate.

Generation binding uses `lp_events_all.json`, not the rolling `lp_events.json`.
Consumer refresh verifies the all-dates asset and records its SHA in
`metadata.sourceAssetSha256`. The manifest option requires that exact asset.
