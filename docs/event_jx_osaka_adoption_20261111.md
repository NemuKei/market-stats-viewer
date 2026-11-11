# JX Osaka: two occurrence adoption (2026-11-11)

Issue #42 remains the coverage issue; this adoption does not fix its monthly-calendar collector gap.

Official facts: JX 2026 TOUR CONCERT CORE, Asue Arena Osaka, 2026-11-14 and 2026-11-15, each OPEN 16:00 / START 17:00. Rechecked venue and artist sources on 2026-11-11.

- https://www.yahataya-park.jp/osaka_arena/schedule/schedule1.html
- https://www.jaefans.com/information/schedule/schedule/2617
- https://www.jaefans.com/information/schedule/schedule/2618

Only the two already detected venue_web_discovery candidates are registered. November 14 retains its eplus ticket_official source; November 15 retains its jaefans artist_official source. The older Kstyle news candidates (different artist label, absent normalized time) remain unadopted. No global alias, parser change or database change.

Existing new-ID review and preserve_source publication review are used. The reviewed projection intentionally excludes snippets, raw titles and capacity for these new rows; no existing rows are projected differently. Both 90-day and all-dates builds add exactly these two IDs with zero removed or changed existing rows. Baseline is unchanged, so the new rows continue to require their reviewed map and exact source binding; subsequent drift is not automatically approved.

User explicitly approved these two occurrences for registration, distribution and production publication. CI, Release and production verification are separate subsequent gates, not claimed complete by this document.

Fixed IDs:
- 2026-11-14 17:00: `evt_cd7098c9a7594a998d4a22d5ce8611a3`
- 2026-11-15 17:00: `evt_33f4414526c546b9a6812ceac6a82a2d`
