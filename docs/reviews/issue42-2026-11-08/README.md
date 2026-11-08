# Issue 42: dated Ariake programmes and official league fixtures

This change covers the 27 occurrences in `target-facts.json`: 11 Ariake
programmes and 16 league fixtures. Six existing fixed IDs are inherited and
corrected; 21 new IDs are allocated once in registry revisions 60–71. Existing
relations and unrelated registry entries are preserved. Do not re-run `new`
registration during deployment: adopt this completed registry/map/baseline set.

## Sources and publication decisions

Ariake dates and per-day starts come from the venue's public monthly event
pages. Acquisition URLs remain separate from artist/tour detail links. The SLS
organizer page establishes November 14 and Ariake; individual round starts are
not presented as a whole-event start. B.LEAGUE arena pages identify the main
facility and fixture dates; each game-detail link is separately pinned in an
exact occurrence scope. Unknown starts remain unknown.

The two Urayasu fixtures are new observations of its club-owned national
stadium page, not relabelled League One observations. Osaka Bluteon's two
fixtures use its November 6 club announcement. Suntory's four fixtures were
observed in the ordinary public browser on November 8. Their extractor remains
`browser`; ordinary automated HTTP returned 403 and is not claimed successful.
The official season and dated rows were checked against SV.LEAGUE facts.

These are conditional, occurrence-limited decisions to publish dates, planned
starts, venue, participants/title and selected official links. They assert no
individual licence or affiliation. Images and introductory text are excluded.
Source snippets remain empty in reviewed public LP rows. Club sources retain
`promoter_official`, rather than being misclassified as venue sources.

- [B.LEAGUE site conditions](https://www.bleague.jp/site/): inbound links are
  generally permitted; notification is requested if possible. No notification
  or individual permission is asserted.
- [Bluteon conditions](https://www.osaka-bluteon.com/terms/terms-of-use.html):
  identify the linked page accurately; the consumer displays the publisher and
  fixture guidance.
- [Urayasu conditions](https://urayasu-d-rocks.com/terms/): no blanket reuse
  permission is inferred.
- [Suntory conditions](https://www.suntory.co.jp/guide/): identify the company
  website. The consumer names Suntory Holdings and links to the actual schedule.

## Collection and compatibility

Only Ariake enables `dated_sessions`. Its collection DB is private to the job;
the public SQLite projection uses Git-reviewed ID/source/publication decisions.
Ten raw rows change (five replacements and five additions); 25 other newly
collected differences remain private. Public rows have no new description,
performer prose or capacity. Unrelated 2,350 raw rows remain identical. Absence
does not mean cancellation. New unreviewed candidates are held individually.

The league preparation helper only drafts the existing inbox format. It does
not register IDs, alter policies or publish, and is not a new scheduled writer.
The tracked automation inbox is unchanged. Sixteen reviewed confirmations are
appended to the existing configuration; the 1,438 prior signal rows are exact.

Verified locally: public SQLite 2,355→2,360; recent LP 994→1,015; all-dates LP
1,111→1,132. All 1,105 unrelated LP rows match in every field. The public saved
schedule asset and baseline are byte-identical. Artist CSV adds only five rows
and preserves the previous 699. Repeated collection/projection/generation keeps
the same fixed IDs and facts. Schema versions, ordinary crons and Draft PR 21
remain unchanged. The public SQLite projection is now explicitly enabled for
Ariake, so future reviewed and held data stay separated.

## Deployment, retry and recovery

1. Recheck both main heads and completed Release hashes before merging. This
   candidate is based on producer `765237b3e7e70ba4240c5da45c1fd71a30afd191`
   and registry revision 59. Its DBs match that Release; the preceding automatic
   News update changed only generation metadata. If relevant input changes,
   stop and regenerate/review against the current cohort before merging.
2. Merge only the explicit file manifest. Never copy a private collector DB,
   HTML, browser cache, test fixture or a whole preparation directory.
3. Verify all seven Release assets, manifest source commit and registry revision
   71 after producer publication. A partial Release is not a valid cohort.
   Retry the same source generation if required; do not allocate fresh IDs.
4. Prepare consumer readoption from that actual completed Release, exact policy,
   accepted runtime and immutable saved-day history. Verify 21 added occurrences,
   six corrected occurrences, 2,122 unchanged runtime rows and 1,017 saved days.
   Saved-day added/withdrawn/corrected IDs remain empty. Record the canonical
   candidate and request hash, then run the existing publication workflow.
5. Until explicit adoption succeeds, consumer refresh failures preserve the
   accepted event state. Re-check status before retrying a dispatch; do not run
   two independent adoptions. Repeating the same accepted request is a no-op.
6. A failed Release upload is repaired with the same coherent source generation;
   a failed consumer build is retried with the same pinned request/candidate.
   After acceptance, preserve the new fixed IDs, accepted saved-day history and
   checkpoint. Roll back faulty display code or disable new source decisions,
   then use explicit correction/readoption; do not revert away registry/history.
   Keep a known-good complete served snapshot available while repairing.

The collector's full live rerun and the next scheduled runs are distinct checks;
local replay does not claim those runs succeeded. Schedule diagnostics report
creation delay and execution duration without changing cron times.
