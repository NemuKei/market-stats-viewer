# Official ticket candidate collection, first stage

## Intent and scope

Issue #53's next stage: gather observed dates from reviewed official page routes,
without inventing missing dates or bypassing the reviewed-ledger contract. Begin
with the NiziU WithU round already published. Artist, promoter and primary ticket
sources are the intended route classes; only NiziU is implemented initially.
This is **not** automatic discovery of every artist, automatic publication,
account login, ticket purchasing or personal lottery-result lookup.

An unconstrained general date scraper was rejected because pages contain multiple
rounds and shows. Replacing the reviewed ledger automatically was rejected because
changed eligibility/show applicability requires review. The chosen narrow route
uses exact unique section boundaries and known show IDs. Unknown syntax fails
closed, never falls back to fuzzy artist-name or date matching.

## Pipeline

`config/ticket_sources.json` contains code-reviewed public URLs, official source
classification, unique start/end section labels, round IDs and individual event
IDs. Both the config and hostname allowlist need review when extending routes.
The collector rejects missing event IDs. Source text may not change these rules.

`python -m scripts.collect_ticket_candidates --sources config/ticket_sources.json --events data/lp_events.json --output /tmp/new-ticket-review.json --checked-at-utc 2026-11-10T05:00:00Z`

The output path must be new and outside the checkout. Optional `--previous`
accepts a prior candidate snapshot and appends changed observations while preserving
all older observations. Fetch/parse failure and zero extracted facts never erase
previous observations. The public ledger and its `last_verified_at_utc` are not
updated by collecting candidates, even if unchanged.

Only explicit Japanese dates and times on labeled lines within the configured
round are recognized. An end date in the same syntactic range can share the
explicit first year; backwards/cross-year ambiguity is held, never rolled into
the next year. Date-only stays date-only. Unknown lines stay unverified rather
than unannounced. Multiple matches, in-section correction/cancellation/extension text,
unsupported formats or ambiguous boundaries are held for review.

Page-wide status/applicability keywords also flag the observed candidate for additional review, without losing correctly scoped dates. Changed page hashes retain a new observation even if extracted dates are unchanged.

Evidence comprises the source URL/class/name, observation time, exact page hash,
parsed fact hash and structured date facts. Article text/images are not retained.
The structured values have `observed_requires_review`, **not** `confirmed`.
To publish, independently review the source and show applicability, then update
the reviewed ledger with its existing history/revision rules.

## Network and operational behavior

Ordinary unauthenticated HTTPS only, fixed hostname allowlist, no redirects,
no retry, max 2 MB and 20-second timeout. Read robots.txt first; failure/disallow
stops collection. HTTP 401/403/429 stops the host for the run. No browser/proxy
fallback, credentials or alternate endpoints. Restricted/failed sources produce
explicit diagnostic statuses, never a misleading successful collection.

The daily 05:23 UTC read-only workflow retains a per-run candidate artifact for
30 days and reports status codes. It never commits, publishes Release, or touches
live settings. Run success means the diagnostic finished, not extraction success.
A branch-scoped Actions cache restores the previous candidate snapshot for strict schema/hash validation and `--previous` comparison. Changed observations are appended, never replaced. Cache eviction can break continuity; the summary explicitly reports missing history rather than claiming no changes. Per-run artifacts remain for 30 days.
GitHub scheduled runs can be delayed; this is not a strict-time guarantee.

## Verification and remaining rollout

Tests cover date-only/time/range, unknown and malformed date, implicit cross-year,
multiple rounds, missing boundaries, cancellation text, empty vs failed, immutable
prior observations, unresolved events and network destination rejection. A local
fixture read of the previously verified NiziU page extracts the two known
application milestones and leaves results/payment unverified. A normal unauthenticated live fetch at 2026-11-10T04:55:50Z also produced one NiziU candidate with the correct application period. General applicability notices correctly keep it under review. The scheduled workflow has not been run; it requires publication/merge first.

Remaining: authorize/publish the new collector workflow, run it, review live results,
add official source adapters and any desired notifications. Automated promotion
is deliberately excluded; do not call this all-artist automated operation.
