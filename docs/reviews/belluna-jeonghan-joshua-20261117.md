# Belluna: two occurrence adoption (2026-11-17)

Official artist schedule: https://www.seventeen-17.jp/posts/schedule/ztckpb

JEONGHAN X JOSHUA JOURNEY INTO [DREAMING] - JAPAN, Belluna Dome,
2026-11-21 and 2026-11-22, both START 17:00 JST (doors 15:00).
Only these two factual occurrences and checked official links are in scope.
No images, introductory prose, ticket-sale text or raw HTML are published;
no publisher licence or affiliation is claimed.

The existing `official_events` rows are retained without modification. Two
`artist_official` Venue Web records supply the missing start times through the
existing consolidation path. This is additional evidence for the existing
occurrences, not two additional venue DB rows. Venue source priority is unchanged.
The title names both artists; the existing canonical artist field remains
`ジョンハン`. No global artist dictionary or inference changes are included.

The venue acquisition URL is
https://bellunadome.seibulions.co.jp/schedule/202611/all/index.html .
The venue's detail URL is https://www.seventeen-17.jp/statics/dreaming .
Both are independently selected by the source review; the time evidence is the
artist schedule linked above. The new reviewed projection suppresses snippets,
raw names and unselected supplemental links. The official artist signal remains
internal supporting evidence with its source record identifier.

Fixed IDs allocated once in isolation:
- 2026-11-21: `evt_8123aa1eadad4c998065dcf17dfe326a`
- 2026-11-22: `evt_c9777eb584ea4218b7930518a4fac90c`

Existing IDs, observations, relations, source reviews and baseline are preserved.
New events require the exact reviewed map; the baseline is not expanded here.
At base `0b3898f329e3948226b5f72049cd083c6bda00cc`, local current-window
output is 991 → 993 and all-dates output 1148 → 1150, with zero existing
rows removed or changed. The official SQLite bytes are unchanged.

Confirmed Venue Web config is retained across normal inbox refreshes, and
repeated identical signal upserts do not change facts or identifiers. Future
source fact changes must pass normal fixed-ID/source review; they are not
pre-approved by this adoption.

This document records local preparation, not a completed Release or deployment.
The current adoption is a single coherent change. Only the two reviewed
signals are generated with the existing writer into an isolated copy of the
current SQLite DB; every other row and source table is verified unchanged.
The fixed IDs above, source reviews and generated recent LP are adopted together.
No broad inbox processing, general collection or schedule dispatch is required.
Recent LP keeps the previously accepted as-of date so this focused addition does
not age unrelated rows out. The existing Release workflow regenerates the
matching all-dates asset. Consumer exact-event policy, readoption and production
verification remain separate gates. Preserve the IDs; never rerun a new-ID
request to allocate replacements.

Local validation: 164 focused tests passed across Venue Web, source review,
fixed-ID registry, public projection, recent/all-dates builds, manifest/schema,
inbox/backlog and publication filter. The normal Venue Web updater fetched 1395
configured signals with zero changed/pruned on repeat. A copied official DB with
only a later retrieval timestamp still resolves the same two IDs at 17:00;
unrelated public rows remain equal. `git diff --check` and registry validation
passed. These are local tests, not remote CI or production acceptance.

Execution-base revalidation (2026-11-18 UTC): main
`3c1f22335f5a5597cd1723fc907828b35465ddc4`. Exactly two signals inserted
using the existing writer, with all previous SQLite rows and the source table
unchanged. Current-window rows 989 → 991 at the accepted as-of 2026-11-18;
all-dates rows 1148 → 1150. Existing published rows are fully unchanged.
No collection dispatch or scheduling configuration change is included.
