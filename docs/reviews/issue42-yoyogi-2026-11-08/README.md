# Issue #42: eight Yoyogi first-arena programmes and private league observation

## Verified dates and source scope

The actual venue [calendar](https://www.jpnsport.go.jp/yoyogi/event/tabid/59/Default.aspx)
and its twelve current detail pages were fetched successfully in one recorded
observation on 2026-11-08. Only these eight dates are adopted:

|Date in 2026|Programme|Labelled start|Category|
|---|---|---|---|
|November 8|NMIXX JAPAN DEBUT SHOWCASE|17:30|コンサート|
|November 10 / 11|羊文学 TOUR 2026|19:00|コンサート|
|November 14 / 15|U18 日清食品トップリーグ バスケットボール競技大会|Not stated|その他|
|November 22 / 23|ANI-ROCK FES. 僕のヒーローアカデミア PLUS ULTRA LIVE|16:00|コンサート|
|November 29|JKJO全日本ジュニア／JKC全国高等学校空手道選手権大会|Not stated|その他|

The record unit is a dated source programme, not an inferred number of basketball
games, tournament bouts or individual performers. When the source does not give an
artist list, the existing programme-label convention is retained. Five source
starts are explicit; three stay null. No door time is adopted as a start. Category
decisions use the actual named music/sport programmes, not the presence of a clock.
Only dated facts and observed venue calendar/detail links are published. Images,
source introductions and external artist/contact links are absent.

`target-facts.json` pins all eight fixed IDs, native source records and the actual
selected links. `source-observations.json` records response time/body hashes, not
source HTML. The existing consumer `jpnsport.go.jp` / `venue_official` fact-only
policy covers these exact rows and both public URLs; its bytes remain unchanged.
This is the existing conditional publication judgment, not an assertion of an
individual licence or a legal conclusion.

## Cause and minimal durable change

Collection already had these dates, but the IDs were unregistered. The parser
also read only the calendar and missed starts in each programme's detail page.
Its old URL-derived source key treated `etype=1` (current-month display) and
`etype=2` (next-month display) as separate raw records for the same native event.

The opt-in detail parser uses the source's native event ID and explicit date,
retaining the observed acquisition URL separately from its detail URL. Every
different URL is individually validated/fetched before equal native facts are
combined. Repeated fact labels, conflicting dates/titles/starts, multiple clocks,
unknown hosts/facilities or redirects stop that venue for review. No new normal
event is silently merged on a same-day guess. Unreviewed link changes remain
per-row holds through the existing source map/baseline and SQLite projection.

The existing CSV publication-review flag and Actions gate protect Yoyogi together
with Ariake and Nagoya, including monthly artist inference and failed-fetch cases
whose DB venue metadata remains old. No new approval service or journal is added.
The parser's default path remains unchanged for non-opted-in data.

## Explicit data migration and identity history

The input basis is producer main `f38e639d28eee671190016f709b1c512da09dc94`, its
actual seven-asset Release, registry revision 86, and consumer main
`98df4d0e3062842b33ff1dcc94244e234ef5b798` / runtime 2,148.

Sixteen old raw rows form eight same-title/date/native-ID pairs. Both old records
in each pair have **zero references in every stored ID observation**, including
inactive history. Their unknown starts and normalized titles/source URLs are
checked in `source-migration.json`. They are replaced transactionally by eight
canonical source rows; other **2,344 raw rows** match in every field. Raw row count
is 2,360 → 2,352. No registered predecessor is deleted or reset.

Eight new fixed IDs are allocated **once** in the isolated completed set. Registry
86 → 87, total IDs 1,145 → 1,153. Every old event/observation/relation remains.
`ID-request.json` and the pinned resulting IDs must be adopted together with the
map, baseline and LP. Do not execute new-ID allocation again in production.
If input hashes change, retain the allocated IDs and revalidate/rebind explicitly
against the new generation; never silently allocate another eight.

Existing 1,131 all-dates LP rows match in every field; eight are added. Recent LP
1,000 → 1,008; all-dates 1,131 → 1,139. The full consumer runtime is 2,148 → 2,156.
All old runtime rows, all 1,017 saved days, policy bytes and immutable history remain.
Coverage still begins 2025-08-23. Event signals, web-discovery config and inbox are
unchanged; unreviewed older calendar programmes remain held.

## Verification and normal operation

Python: 1,006 tests plus 96 subtests; Ruff succeeds. Independent review identified
and resolved repeated detail-label and alternate-URL cache issues before adoption.
Recorded actual HTML passed through the real collection CLI, private inference,
three-venue SQLite projection, normal LP and full LP. It made exactly the thirteen
recorded URL requests; no URL borrowed another response body. Four unregistered
earlier programmes stayed private; all old public LP rows were unchanged. The
eight new facts/links and fixed IDs remained; two may get ordinary observation
timestamp refreshes. A separate changed-link test retained all eight old public
links and DB bytes. Repeat projection is idempotent.

The actual consumer ordinary-update CLI was exercised locally: all 2,148 old rows
and saved/history bytes remain, eight are added, and repetition is byte-identical.
No consumer policy expansion or new snapshot readoption request is needed for
normal new reviewed IDs under an unchanged policy. Local placeholder manifests
remain test-only; the real completed Release must be verified before dispatch.

## Private league diagnostics

The existing daily Venue Web Discovery workflow prepares private J.LEAGUE,
B.LEAGUE and League One drafts through the existing parsers/schema. The selection
is five registered venues and the next ninety days; no cron changes. Only counts
and health states reach logs/summary. Draft files remain outside checkout/Git,
with no public artifact upload or public inbox/config/ID/DB write. Summary paths
reject symlinks, traversal and hardlink aliases and are checked again on the opened
append-only file descriptor. HTTP access denial stops the host rather than trying
another endpoint. Empty results stay unverified; another valid update can continue.

A real fifteen-page run observed eight candidate records: seven exact confirmed
observations and one **already published** rugby fixture with a different official
URL. It is counted as another source, not a new match. No new league game is added
by this set. SV League access remains a separate normal-browser review. This
monitor observes coverage; it does not prove completeness or fix scheduler delay.

## Publish, retry and recover

1. Recheck main/Release/DB/registry/source hashes and queued repository writers.
   On any changed basis, stop and rebuild/revalidate the completed set. Preserve
   the eight already allocated IDs. Apply only the explicit reviewed files.
2. Merge producer code/data after CI; inspect the manifest-last Release run, all
   seven asset hashes, actual commit, registry 87, target rows and saved-day pins.
   Queued/failed/partly uploaded assets are not a completed Release.
3. Run the existing **ordinary** consumer publication after checking there is no
   already queued/running run. Verify public JSON against the exact actual-Release
   candidate, all old 2,148 rows, new eight, saved days, unchanged history and Pages.
4. If a client response is lost, inspect actual run/main/live state before retry.
   A successful ordinary refresh is idempotent. Do not allocate new IDs or create
   an unnecessary readoption request to recover the response.
5. If Release fails, the old consumer stays accepted; repair/retry that exact
   producer generation. If a runtime commit succeeds but Pages fails, redeploy
   that accepted commit and matching JSON/history. Keep ID history and repair data
   forward; do not roll the registry backward. A confirmed defect requiring the
   eight dates' withdrawal uses the established explicit forward-review procedure.
   Emergency static restoration must keep runtime, policy, saved data and immutable
   history together, with ordinary updates paused until the forward fix is ready.

No private collection DB, raw source HTML or local fake manifest is deployed.
NiziU, Nogizaka46, hide and other artist-source publication decisions remain
separate. The old official-collector failure is not resolved merely by another
workflow's success; the next scheduled collection must still be checked. Issue
#42 remains open and no national-completeness claim is made.
