# Event calendar coverage and programme review

Issue: https://github.com/NemuKei/market-stats-viewer/issues/42

## Scope and source of truth

Use `venue_registry.csv` for stable venue identities, `venue_aliases.csv` for names,
and the existing Venue Web Discovery inbox for supplemental official observations.
Configured, fetched, registered, and published are four different states. The
104-row inventory is not a national census and does not prove fetch coverage.
The read-only inventory code is reused from Draft PR #21 at
`f30931bb96d0563c5e87235d79fbd32a0ae314cb`; none of that PR's writers, state,
expanded venue list or handoff automation is enabled here. Ticketjam inventory is
optional and not a publication source.

The persistent `mufg_stadium` ID denotes **味の素スタジアム**. **国立競技場 /
MUFGスタジアム** uses `national_stadium`. Correct the watch-list reference; do not
rename IDs or reinterpret historical records. Budokan and LaLa arena already
have registered IDs. Their direct collectors remain disabled; Budokan's strategy
is a placeholder and its purported `/schedule` redirects to the homepage.
Use actual artist/promoter official evidence for those gaps, not the third-party
Budokan calendar mentioned in the Issue.

## Collection fixes and review boundaries

- Unresolved official performers no longer discard a programme before ID review.
  The exact programme title is the legacy `artist_name` grouping label when no
  performer is supplied. `raw_artist_name` remains empty: this does not identify
  an inferred musician. Sports and unknown concerts use the same review path.
- A newly visible programme that overlaps a resolved subject stays in private
  `programme_review_candidates`. It cannot silently change source priority,
  split an existing key, merge different show times, or cancel another show.
  Resolve those entries against the actual programme/status before adoption.
- Makuhari pagination follows actual next-page links even if every item on one
  page is filtered out. The existing music-only category filter is unchanged;
  exhibitions such as Inter BEE require a deliberate scope/configuration choice.
- Ajinomoto's mixed facility calendar admits only explicit main-stadium labels.
  AGF, Aminovital and unlabelled items cannot be assigned to the main venue ID.
  Old mixed-facility rows are not deleted or approved by this parser change.
- Nagoya's archived/current/next-year tables are bound to their labelled year and
  `tabs-N` month. Missing/contradictory labels require review rather than an
  inference from today's month. Only the 開始 column supplies the start time;
  開場 and 終了 never replace an unknown start.
- Suita's obsolete `/schedule/index/year/.../month/.../` route returns 404.
  Use the official `schedule_YYYYMM.html` route and verify the response's labelled
  year/month. A redirected or contradictory page cannot relabel last month's
  matches as future fixtures.

These changes do not approve all pending rows. Existing fixed-ID review, source
selection, publication row hash, independent consumer source/link rules, and
legacy v5 retention remain in force. An ID alone is insufficient for publishing.
Do not globally replace existing LP fields or reclassify original source URLs.

## Existing workflow monitoring

The three existing official/News/Venue Web jobs run a read-only audit after LP
generation. It reuses the producer's real source/ID review path, records current
input hashes, and reports per-venue raw rows/days, registered IDs, public rows,
hold reasons, last window day, blank-day span, and same-day review groups.
Raw and public counts are different units and their difference is not a count
of proven missing events. Multi-day ranges are expanded within the bounded
reporting window. Different show times are possible legitimate performances.

`update_events_data --run-report "$RUNNER_TEMP/events-official-fetch.json"`
records counts only: failed/partial requests, unrequested plugins, empty results,
or fetched-but-completeness-unverified. No source text, request URLs or credentials
are recorded. Without this current-run report fetch status is **not measured**.
No runtime status is inferred from configuration or the DB's last update time.

The JSON goes to the Actions log and a counts-only table goes to Step Summary;
aggregate annotations call for review. Candidate details stay in memory or a
private pending preview, never in the public report. A monitoring failure is
visible but does not discard another valid collection update. The existing
repo-write concurrency and rebase/rebuild checks continue to own mutations.
The audit does not dispatch Actions, write DBs/IDs, or approve/cancel events.

```sh
uv run python -m scripts.audit_event_calendar_coverage --days 114 --output /tmp/coverage.json
uv run python -m scripts.event_identity_registry pending --reviewed-source-map data/reviewed_event_sources.json --reviewed-source-baseline data/reviewed_event_baseline.json --output /tmp/new-private-preview.json
```

Finite `coverage_expectation` notes live in the existing venue `config_json`:
the Saitama renovation has a sourced recheck deadline, **not an invented reopening
date**; Yoyogi's official source excludes the month after next, so supplementary
artist/promoter evidence is necessary. Expired closure notes no longer explain
a zero. No universal minimum event count is invented for disabled/unassessed venues.
Raw programmes during an expected closure are still flagged for facility/source
review: a closure exemption cannot silently certify conflicting observations.

## Supplemental programme drafts

`prepare_venue_programme_inbox` fetches the actual Osaka Marvelous 2026–27 team
calendar or LaLa arena calendar and creates a new private draft, never a live
inbox, DB or config. The team adapter accepts explicit home games at Asue only;
away fixtures are not labelled as the club's promoter programme. Each day and
explicit show time is separate. LaLa's displayed year/month is authoritative;
Reserved, cancellation/postponement notices and ambiguous layouts need review.
Entry times never become starts. Acquisition and detail URLs remain separate.
The existing 30-candidate limit fails without truncation; use smaller date windows.
Do not assume a calendar range is a daily performance list. COUNTDOWN JAPAN's
official organiser lists December 26, 27, 29, 30 and 31, explicitly excluding
December 28; create separate inbox observations for those actual dates. The
December 31 show ends at 29:00, meaning January 1 at 05:00. Keep the source
range candidate unreviewed rather than publishing a fabricated sixth show.

```sh
uv run python -m scripts.prepare_venue_programme_inbox --source osaka-marvelous --start 2026-11-07 --through 2027-01-31 --output /tmp/asue-review-draft.json
uv run python -m scripts.prepare_venue_programme_inbox --source lala-arena --start 2026-11-07 --through 2026-12-07 --output /tmp/lala-review-draft.json
```

Inspect the official evidence and source class, simulate `apply_inbox`, and use
the existing Git/inbox/ID/source publication review process. A prepared draft is
not permission to publish. These two adapters are not a league-wide collector;
the team season URL needs review when the season changes. New domains/source
classes and broader venue/category activation need their own concrete decisions.

## Existing-data maintenance

The first authorized repair is recorded in
[`maintenance/2026-11-07-official-refresh-repair.json`](maintenance/2026-11-07-official-refresh-repair.json).
It changes exactly six observed source rows, preserves all fixed IDs/history,
and rebinds four observations at registry revision 56. Three published rows
change facts (REBECCA's date interval and two Kuwata starts); MC TYSON's
explicitly cancelled performance is withdrawn. The Juliet row only changes its
internal binding and remains byte-for-byte identical publicly. The other 1,104
retained rows and both saved-day assets remain unchanged. Current consumer
source policy suffices; there is no new source/domain grant. Read the review
record together with the real source evidence before repeating maintenance.

The official update's discarded runner DB is unavailable. A fresh-source replay
reproduced the same failure; it is not an assertion that its bytes equal that
runner's discarded DB. Do not deploy the replay DB: its unrelated ordinary
observation timestamps also advanced. Only the reviewed six-row whitelist was
used for the limited repair.

The current Nagoya archive exposes at least 14 published occurrences misdated as
2026 instead of 2025, including TXT December 6–7 and EXILE December 27–28. Fixing
the parser alone does not repair retained DB rows. Prepare exact old/new source
row pairs and **correction** requests preserving each fixed ID, not cancellations,
deletions or fresh-ID registrations. Retain every previous observation/relation.
BIGBANG November 29 at Kyocera has one official 17:00 performance; the competing
15:00 signal uses the door time. Correct the same signal record and review a
merge retaining the existing official 17:00 ID. Distinct genuine show times elsewhere
must remain separate.

These maintenance drafts are separate from the default-compatible code. Accurate
Nagoya acquisition links require a proposed consumer grant pinned to the exact
14 IDs, facts and acquisition/detail URLs. The consumer's default domain policy
currently excludes those corrected source tuples. No domain-wide grant is needed.
The [link-button conditions](https://www.nagoya-dome.co.jp/linkinfo.php) concern
the supplied image button; this proposal uses ordinary text links and no images
or descriptive prose. Do not expand those button terms into an unverified legal
ban on text links, or claim a licence/individual consent. The conditional fact/link
decision belongs to the operator through the existing Git review.

Before adoption re-pin both mains and Release/DB/registry hashes. Apply only the
reviewed source-row whitelist transactionally to a fresh isolated copy, apply
the deterministic correction/merge requests once, and derive map/LP/policy from
that same registry revision. Rebase/regenerate on conflicting inputs. Never copy
a simulation DB, simulated approval or an unreviewed candidate registry to live.
Follow existing manifest-last Release distribution and consumer stage/readoption
history procedures; keep saved-day assets and history. Code push/merge, policy
adoption and production publication remain separate authorized operations.

## Recovery and remaining work

Use the existing Git, manifest-last Release upload and consumer stage/history
mechanisms. Before each write compare the expected main SHA, ID revision/hash,
source-row hashes and the two saved-day pins. Stop on a changed input and
regenerate from one generation. Main also starts the existing asset workflow;
a successful unrelated workflow does not resolve a failed official update.

Keep the previous accepted seven-asset Release and consumer JSON/history as a
recovery point. An incomplete asset upload must fail checksum/generation checks
and leave the last accepted consumer snapshot. Retry the same approved generation
after verifying the manifest; do not reuse a mixture. If a publication has been
accepted, preserve its ID observations and consumer history and repair forward.
Do not reset the registry to an older revision or resurrect a confirmed cancelled
show. A code rollback that restores the known bad calendar year/status parser
must not resume collection until the replacement is ready.

Ariake per-date/matinee splitting, league-wide preparation/publication and a
cron-minute change are not activated by this patch. Their isolated proposals
need their remaining identity/link decisions. Draft PR #21's additional state,
writers and handoffs are not enabled; this patch reuses only its read-only venue
inventory audit. This is not a national-completeness claim or closure of #42.
