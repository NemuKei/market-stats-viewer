# Preserved daily schedule: public distribution contract

This optional package transports an already reviewed set of **日別予定観測**.
It does not prove that a performance occurred, assign performance counts, collect
new history, register IDs, or restore a production database. The normal event LP
and collectors retain their existing contracts. The publication gate is disabled
unless explicitly configured; this implementation does not generate or publish
the real package.

## Package and privacy boundary

The existing external-events manifest keeps its schema, dataset, release tag,
repository, commit, generation time and existing asset entries. Two optional
entries are added together:

| Asset | Content |
| --- | --- |
| `public_schedule_days.json` | The approved public rows, display metadata, source-pair digests and aggregate policy counts |
| `public_schedule_baseline.json` | Exact bytes of the reviewed existing public v1 event snapshot |

Each manifest asset entry remains `{size_bytes, sha256}`. A half package is invalid.
With the gate disabled, the manifest builder ignores these files even if present.
An enabled gate requires both files and the separately reviewed public-asset,
baseline and adoption-set SHA-256 pins. No real pin values are committed here.

The frozen baseline is an existing public snapshot, not the private source LP or
DB. Its public v1 root is exactly `schemaVersion`, `generation`, `metadata`,
`coverage`, `events`; the ordinary public rows, ID values and order are preserved.
It must have valid generation, public allowlisted fields, policy counts, domestic
prefectures and date coverage. It retains `completeArchive: false` and unbounded
retained-history coverage. No new private metadata may be inserted.

Raw observations, private candidate rows, supporting record lists, the complete
identity registry, the review plan and event databases used as archive evidence
are not inputs to Git or Release publication. The producer reads private inputs
locally; only the public pair may be transferred to a distribution directory.
The existing public `source_record_id` display field stays in the public row
contract. It is distinct from private complete record lists and can be shortened
by the existing public exporter.

## Public day asset schema

The JSON object has exactly these nine fields:

| Field | Rule |
| --- | --- |
| `schema_version` | Integer `1` |
| `dataset` | `public_preserved_schedule_days` |
| `generated_at_utc` | Original private schedule generation, explicit UTC; normal refresh does not make this historical observation newer |
| `baseline_sha256` | SHA-256 of the exact frozen public baseline bytes |
| `provenance` | Original schedule asset SHA, registry header and approved-ID set SHA |
| `events` | Approved public rows in approved snapshot order; empty only with an explicit externally pinned publication selection |
| `schedule_metadata` | Exactly one display-metadata object for each published ID |
| `source_record_digests` | Exactly one nonempty sorted unique digest list for each published ID |
| `publication_policy` | Existing public policy names/fields and full private-day input count; explicit publication stops update published/excluded counts |

`provenance` has exactly:

```json
{
  "schedule_asset_sha256": "<original-private-schedule-sha256>",
  "identity_registry": {
    "schema_version": 2,
    "revision": 1,
    "sha256": "<reviewed-copied-registry-sha256>"
  },
  "approval_set_sha256": "<approved-day-id-set-sha256>"
}
```

The registry revision is the actual reviewed revision, not the example value.
Neither its entries nor its evidence journal are distributed.

Public rows use only the existing 23-field allowlist:

```text
event_uid source_record_id source_policy_rule_id source_policy_status
source_policy_reviewed_at source_domain kind kindLabel source_id source_name
title start_date end_date start_time published_at_utc updated_at_utc url
source_url venue_name pref_name artist_name event_category source_type
```

The producer preserves the exact reviewed public projection, including optional
fields and ordering. A daily row has `kind=official`,
`source_id=official_events`, `source_type=venue_official`, approved/conditional
policy status, one canonical day and a domestic prefecture. `start_time` and
`artist_name` are absent or empty; observed times belong to the separate metadata.
Cancelled/postponed titles and private fields are rejected. IDs are unique, and
the exact approved set must match the independently supplied adoption pin.

Each metadata object has exactly eleven fields:

```text
kind observedTimes hasUnknownTime performanceCount occurrenceCompleted
evidenceBasis urlGranularity lastObservedAtUtc historicalVenueNames
observedTitles venueNotes
```

The predicates are `kind=schedule_day`, `performanceCount=null`,
`occurrenceCompleted=unverified`,
`evidenceBasis=preserved_official_schedule`, `urlGranularity=calendar`.
`observedTimes` is a sorted unique list of observed clock times;
`hasUnknownTime` preserves missing-time evidence. A same-day observation with two
clock times remains one daily display bundle and does not assert two performances.
Original titles and venue notes stay available for unresolved differences. The
representative title must be an original observed title or its existing NFC /
whitespace-normalized public projection capped at 180 Unicode code points. The
full original remains unchanged in `observedTitles`. Dates/programs do not
merge merely because they share a calendar URL. Venue notes describe the original
venue category; they do not establish an individual performance venue.

For a source pair, the digest input is the full private values:

```python
hashlib.sha256(json.dumps(
    [source_id, record_id], ensure_ascii=False, separators=(",", ":")
).encode("utf-8")).hexdigest()
```

Digest lists are sorted and unique. Complete record IDs may be longer than the
public display `source_record_id`, so hashing that shortened display string is
not a valid membership check. The producer verifies complete private record
binding and every public row against the pinned exporter; the consumer pins the
resulting public bytes/provenance and uses complete ordinary LP source pairs for
overlap checks. A digest is an overlap key, not evidence of completed attendance.

The adoption-set digest uses the same UTF-8 compact JSON settings on the sorted
list of approved day IDs. SHA values are lowercase 64-character hex strings;
booleans are not accepted as schema versions, revisions or counts.

## Policy aggregate semantics

`publication_policy` has exactly the existing fields:

```text
status policyId policySchemaVersion reviewedAt defaultDeny inputCount
publishedCount excludedCount excludedByStatus allowedFields
```

Without a publication selection, the original day-only input/published/excluded aggregates are preserved. For
example, a fictional four-bundle source with three approved bundles and one
unknown retains `4 / 3 / 1`, even though only three rows are distributed. The
real approved and held sets are not regenerated or expanded by this builder.
An explicit selection that retains only one of those three approved bundles
produces `4 / 1 / 3`: the two publication stops are added to
`excludedByStatus.blocked`, while the original unknown count remains one. This
blocked aggregate includes explicit publication stops; it does not change any
source-policy status in the retained private inputs. The full source input count
and existing policy identity remain unchanged, including when every day is stopped.
`publishedCount == len(events)`,
`inputCount == publishedCount + excludedCount`, and the
blocked/unknown/invalid counts sum to `excludedCount`. Invalid private rows stop
production rather than becoming a silently omitted group. Only aggregate counts
and existing policy names are public; excluded rows, domains and reasons are not.

The consumer separately checks that its current policy reprojects all distributed
rows without excluding or changing any field. It must not overwrite the original
private-day aggregates with `N / N / 0`. A later policy approval of held domains
does not change this fixed asset or its pinned approved-ID set.

## Offline producer

`python -m scripts.build_public_schedule_days` uses the existing private asset
validator and the four hash-pinned consumer exporter/policy helpers. It does not
duplicate source-policy conversion or call collectors. A reviewed typed v2
snapshot is required as an explicit input. Every approved day row, representative
identity, complete active source binding, observed time and metadata object must
match the private source and that snapshot. There must be exactly one active
registry observation per private day; duplicate private source pairs are rejected.
These checks and full public-contract/aggregate validation run before any explicit
publication selection is applied, so stopping a row cannot hide an invalid full projection.

Example command, with placeholders replaced from a separate reviewed local plan:

```sh
python -m scripts.build_public_schedule_days \
  --private-asset /private/review/lp_schedule_days.json \
  --registry /private/review/preview-identity-registry.json \
  --approved-snapshot /private/review/events.json \
  --consumer-scripts /reviewed/SideBiz_HotelRM/02_Service/web_lp/scripts \
  --consumer-hashes /private/review/consumer-hashes.json \
  --source-policy /private/review/event-source-policy.json \
  --baseline /private/review/published-v1.json \
  --output /private/distribution/public_schedule_days.json \
  --baseline-output /private/distribution/public_schedule_baseline.json \
  --expected-asset-sha256 '<reviewed-private-asset-sha256>' \
  --expected-registry-sha256 '<reviewed-copied-registry-sha256>' \
  --expected-snapshot-sha256 '<reviewed-approved-snapshot-sha256>' \
  --expected-consumer-hashes-sha256 '<reviewed-helper-hash-map-sha256>' \
  --expected-policy-sha256 '<reviewed-policy-sha256>' \
  --expected-approval-sha256 '<reviewed-approved-id-set-sha256>'
```

The optional `--publication-selection /private/review/publication-selection.json`
accepts exactly this object, with integer schema version `1` and sorted unique
day IDs:

```json
{"schema_version":1,"approved_ids":["<reviewed-day-id>"]}
```

Its ID-set digest must match `--expected-approval-sha256`, supplied independently
from the reviewed selection. Every selected ID must already occur in the exact
approved day projection; unknown or held IDs, duplicate IDs, unsorted lists,
extra fields, boolean schema versions and mismatched pins stop production.
Without this option all approved days are published as before. Explicitly selecting
all approved IDs produces identical bytes. An explicit empty list stops every
day and requires the externally supplied digest of `[]`; an unpinned standalone
validator rejects an empty public asset. Empty assets still require empty metadata
and digest maps, correct full-input exclusion aggregates and a valid frozen baseline.
The selection changes only public rows, their display metadata, source-record
digests and publication aggregates. The original source, ID registry and reviewed
snapshot retain every ID and observation. Their SHA/generation provenance remains unchanged.

The output directory must already exist. The fixed output filenames share one
directory. The CLI captures bounded regular-file inputs and verifies their hashes
before executing captured helper code or writing output. The helper hash map is
itself pinned and contains exactly the existing four filenames. Duplicate JSON
keys and non-finite numbers are rejected. Baseline SHA must match the original
private header, and baseline output is the captured original bytes, not a JSON
reserialization. Parent traversal, symlink paths and in-place/hardlink input
aliases are rejected.

Both existing output files are compared before either is written. Different
existing bytes stop the command; identical re-runs keep bytes and modification
times unchanged. Source-record digest maps use stable ID order so separate
processes with different hash seeds generate identical reviewed bytes. Missing
outputs use atomic exclusive file creation. An I/O
failure can leave an incomplete new pair, which package validation refuses;
previous outputs are never overwritten. A changed reviewed package needs a new
output directory and a separate later approval to adopt/distribute it.

## Opt-in publication and consumer transition

Repository variables, all initially unset, control the existing publication job:

```text
PUBLIC_SCHEDULE_DAYS_ENABLED=true
PUBLIC_SCHEDULE_DAYS_SHA256=<reviewed-public-file-sha256>
PUBLIC_SCHEDULE_BASELINE_SHA256=<reviewed-baseline-file-sha256>
PUBLIC_SCHEDULE_APPROVAL_SHA256=<reviewed-approved-id-set-sha256>
```

Enabled manifest creation validates both files, their pins, baseline binding and
the complete public contract before any upload. `validate_external_events`
accepts `--require-public-schedule-days` and the same pins. Without the enable
flag the legacy package and explicit uploader asset list keep their behavior.
With it, both public assets are appended to that list before `manifest.json`.
The existing uploader implementation is unchanged. Sequential Release upload is
not a multi-file transaction: consumers must verify the whole pinned pair and
manifest, stage and validate a candidate, then retain the previous runtime on any
mismatch. Raw/private paths are never passed to the uploader.

First consumer adoption starts from the latest verified ordinary v1 runtime and
adds the pinned approved day set while preserving every existing row and its
fields. The frozen baseline supplies reviewed identity evidence; it never resets
the latest ordinary runtime to old data. Later normal updates retain the existing typed v2 day
IDs/fields and original schedule observation generation, while independently
updating the ordinary source generation. Moving from a private preserved-source
path to this public transport changes only transport provenance; original source
SHA/generation and policy aggregates remain. The current runtime stays active
until candidate validation and promotion succeed. Removing configuration stops
future package use; restoring an earlier runtime or Release requires a separate
reviewed rollback and is not performed by these scripts.

Adopting a new public selection, including an empty selection, requires a separate
reviewed consumer transition. It does not authorize a normal update to silently
remove previously published day IDs, rewrite ordinary rows or discard private ID history.

## Verification

`tests/test_public_schedule_days.py` uses fictional observations and temporary
files only. It covers multiple observed times, shared URLs with different
programs, held-domain policy expansion, original field/time preservation, privacy
allowlists, false performance claims, source-pair digests, pair/pin/manifest
failures, exact baseline copy, idempotence, and input/output preservation on CLI
failures. It also covers explicit subset/all/empty selections, malformed or
unreviewed membership, validation of omitted rows, full-input aggregate preservation
and immutable re-runs without changing the private inputs.
Its `write_cli_fixture(root, consumer_scripts=..., source_policy=...)`
helper accepts the actual captured consumer helpers and a synthetic policy for
an independent producer-to-consumer smoke. The existing manifest, all-dates LP,
package validation and publication workflow focused regression tests also run.
