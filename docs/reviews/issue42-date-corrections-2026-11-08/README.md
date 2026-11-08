# Issue #42: source-labelled date and start-time corrections

This set corrects existing public occurrences. It does not automatically adopt
other archive rows, add a new tour, change cron, or allocate new event IDs.

## Evidence and exact scope

The venue's [dated archive](https://www.nagoya-dome.co.jp/enjoy/index.php),
observed 2026-11-08 07:27 UTC, explicitly places these 14 occurrences in **2025**.
The old public rows incorrectly placed the same title, month/day, start time
and artist detail link in 2026. `target-facts.json` records all fixed IDs and
source-record replacements. The programme name alone is not the year evidence.

|Programme|Correct dates in 2025|Start|
|---|---|---|
|TWICE THIS IS FOR|August 23 / 24|17:30 / 16:30|
|INI XQUARE MASTERPIECE|September 13 / 14 / 15|18:00 / 16:00 / 16:00|
|Mrs. GREEN APPLE BABEL no TOH|October 25 / 26|18:00 / 16:00|
|SEVENTEEN NEW_|November 27 / 29 / 30|18:00|
|TOMORROW X TOGETHER ACT:TOMORROW|December 6 / 7|17:00 / 16:00|
|EXILE LIVE TOUR 2025|December 27 / 28|16:00|

For BIGBANG, both the [venue calendar](https://www.kyoceradome-osaka.jp/schedule/?monthId=11&yearId=2026)
and [artist's dated cards](https://ygex.jp/bigbang/20th-anniv/live/tour.php?id=1003004&fdate=2026-11-27&ldate=2026-11-29)
show **2026-11-29 doors 15:00 / start 17:00** at Kyocera. The wrong 15:00 signal
is corrected in place. Merge it into fixed ID `6d094ea0c8861d6a55ef`; retire
`57de0b817607c6e40c40`, retaining every old observation and relation. Distinct
real same-day start times are not merged by this change.

The corrected Nagoya rows retain their 14 fixed IDs. The identity registry moves
from revision 71 to 86 through fourteen corrections and one merge; its 1,145
total IDs remain. The public SQLite asset replaces the fourteen wrong raw rows
transactionally, so they are not left in another public distribution surface.
Unrelated 2,346 raw rows are identical; total raw rows remain 2,360.

## Cause and recurring-operation controls

The corrected year parser already exists. The old wrong-year rows survived
because the source history filter omits the real 2025 rows and missing records
are deliberately retained rather than treated as cancellations. A counts-only
archive-year conflict check now runs **before** that filter and reaches the
existing coverage summary. Fourteen public mistakes are verified. Another 142
raw year-conflict candidates remain for review; the count alone does not prove
all are mistakes and this set does not rewrite them.

Nagoya opts into the existing private collection / reviewed public SQLite
projection using `publication_review: true`. One shared predicate protects
collection targets, monthly artist inference, and publication. Required venues
come from the Git-reviewed CSV as well as the candidate DB; even a failed or
empty fetch with stale DB metadata cannot evade the gate. CSV is included in
the existing input-hash concurrency check. No new approval service is added.
Unreviewed new/changed gated rows stay private; unchanged old public rows and
other venues' normal updates continue.

The BIGBANG draft parser reads the explicit `開演` in its own full-date venue
card. Regression cases reject door-only/undated/duplicate cards and preserve
two legitimate same-day performances. The generic merger does not guess that
two start times represent a reschedule.

An additional timestamp compatibility fix accepts aware ISO timestamps such as
`+00:00`, rather than falling back to collection time on each refresh. Sixteen
previously published league entries explicitly retain their original stored
first-collection time through `published_at_utc`; their actual verification time,
source method and published facts are unchanged. No announcement time is claimed.

## Publication boundary and compatibility

The consumer adds exactly fourteen **event scopes** for the corrected Nagoya
observations and their exact acquisition/detail links. Domain rules, old event
scopes and the required-URL schema remain unchanged. Existing domains already
cover the BIGBANG survivor. This is a conditional operator judgment for dated
facts and text links, not an assertion of individual permission or a legal
conclusion. Images, logo buttons and source introductory prose are not included.
The [site information](https://www.nagoya-dome.co.jp/howto.php) and
[link-button guidelines](https://www.nagoya-dome.co.jp/linkinfo.php) were read;
the latter's image-button conditions are not extended to ordinary text links.

Recent LP rows: 1,015 → 1,000. All-dates occurrences: 1,132 → 1,131. The fourteen
correct historical occurrences move out of the normal 90-day list. Of the
all-dates rows, 1,116 unrelated rows match in every field. Consumer runtime is
2,149 → 2,148, including its 1,017 saved-day records; 2,133 unrelated runtime rows
and all saved-day data match. Historical `availableFrom` becomes 2025-08-23
instead of 2026-02-01 as a direct consequence of correcting these same IDs.
This is an intentional range change, not an unreviewed archive import.

The saved-day assets, inbox and old immutable adoption archives remain byte
identical. Local real-data CLI staging, adoption, repeat and ordinary refresh
were exercised. Its deliberately placeholder manifest/request are **test only**:
they must never be used as a real Release or production approval.

## Adopt, resume and recover

1. Recheck producer `440631ebf7c19cab5fa936da53e9384223cdf1be`, consumer
   `4b0d05cde49963289751b5e3a1603b168c3d38e6`, current Release, registry 71,
   source hashes and absence of concurrent repository writers. If any basis
   changes, regenerate the set and repeat the differences; do not replay onto
   a new generation automatically.
2. Merge only the explicit producer files after CI/review. The completed data
   already contains all fifteen existing-ID requests. Do **not** rerun ID
   registration in production or allocate replacements.
3. Verify the auto-built Release's seven assets, actual source commit, DB facts,
   identity revision and unchanged saved assets. A queued or failed run is not a
   completed publication. If it fails, keep the old consumer runtime and repair
   or retry that exact generation; do not roll the registry backward.
4. Regenerate the consumer review candidate/request against that **actual**
   Release and current runtime, retaining the same 14 event scopes. Verify old
   history and exact 1,017 saved rows. Commit policy, request, candidate and the
   prior policy through the normal Git review, then dispatch the existing
   explicit readoption workflow with its exact request hash.
5. Before dispatch/retry inspect already queued/running/completed runs and the
   current history head. After a timeout, inspect acceptance before retrying.
   A completed adoption is idempotent; do not create a second adoption merely
   because the client connection was lost.
6. Check actual public JSON bytes against the accepted runtime, all 15 target
   IDs, absence of the retired duplicate, JUMP/Bruno/previous 27 additions,
   saved rows and ordinary-refresh preservation. Confirm the Pages check and
   displayed search results independently of a workflow's top-level status.

If producer succeeds and consumer fails, the previous consumer stays published;
resume the verified request after diagnosing the failed stage. If deployment
fails after a runtime commit, redeploy that accepted commit and immutable history.
For a data defect after adoption, retain registry/history and prepare a forward
correction from the last good facts. Never restore an older whole registry or
private collection DB. Emergency site restoration must restore the matching
runtime, policy, immutable history and dependent JSON assets together, then use
a new reviewed forward adoption before resuming normal updates. Do not restore
only one file from another generation. Private replay DBs and test manifests
are never production inputs.

Issue #42 remains open: Yoyogi/Budokan review backlog, league automation and
scheduler delay are separate. No claim of national completeness is made.
