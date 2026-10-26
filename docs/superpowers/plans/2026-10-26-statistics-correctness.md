# TA / TCD Statistics Correctness Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans or subagent-driven-development for the bounded tasks below. The user requested GitHub Issues and a PR; implement and verify the proposed changes on the PR branch.

**Goal:** Make TA totals/rankings and TCD LOS trustworthy while separating their calculation rules from Streamlit.

**Architecture:** Keep the existing Streamlit entry point, SQLite schema, and update commands. Add small calculation modules under stats/ and make the parser and UI consume the same TA row policy. TCD calculations require complete period data and presentation resolves the selected source unit from source metadata.

**Tech Stack:** Existing Python >=3.11,<3.13, pandas 2.2.3, Streamlit 1.41.1, openpyxl, pytest, Ruff; frozen uv.lock.

**Spec:** docs/spec_ta_data.md, docs/spec_ta_update_pipeline.md, docs/spec_tcd_data.md, docs/spec_app.md.

## Global Constraints

- Consumer outcome: company-only totals, complete-period LOS, explicit source units, repeatable regression checks.
- Do not update data/**, DB schema, dependencies, credentials, runtime configuration, Release assets or the external LP in this PR.
- Data repair is implemented as parser-version-aware reprocessing on a future normal update after merge; existing stored TA aggregates are filtered on read in the UI. Classification or parsing failure in any collected TA source stops before saving, preserving the previous DB and metadata.
- lp_impact=none: event datasets, public IDs, source priority and event publication are outside this statistics PR.
- Keep one PR branch. Root integrates app.py and CI; TA and TCD edits have disjoint ownership.
- Use fixtures and temporary DBs; no live collection or workflow dispatch.

## Review Focus

- Spaced aggregate labels must be removed while company group labels such as JTB（6社計） remain.
- The all-segments KPI/ranking must use total only; a missing total must not become a fabricated zero.
- A missing bin in either TCD series must hold the whole period's LOS/share indicators.
- Duplicate bins, invalid values or mixed periods must not silently produce an average.
- Source units must match selected source URL and content digest; missing, stale or mixed units must not be guessed.

## Task 1: TA row and aggregation policy

**Files:** stats/ta.py; scripts/update_ta_data.py; tests/test_stats_ta.py; tests/test_update_ta_data.py; TA specs.

**Interfaces:** is_ta_summary_company(value) -> bool; filter_ta_company_rows(df) -> DataFrame; select_ta_amount_rows(df, segment=None) -> DataFrame. None selects total; explicit segments select only themselves. Each function preserves its input.

- [x] Reproduce the parser's spaced-total bug with a small real workbook before editing production code.
- [x] Test company/group label preservation, company-only filtering and total-only selection with literal expected amounts.
- [x] Share the row policy between parser and UI-facing helpers.
- [x] Add TA EXTRACTOR_VERSION metadata. Reprocess unchanged inputs when the version is old or output is missing; verify repeated successful runs remain no-ops.
- [x] Stop before saving if a collected TA source has an unknown year/period, unsupported format, parse exception or no company rows. Verify old DB and metadata bytes remain unchanged for known and replacement URLs.
- [x] Run focused tests and update the corresponding TA specifications.

## Task 2: TCD completeness and units

**Files:** stats/tcd.py; tests/test_stats_tcd.py; docs/spec_tcd_data.md.

**Interfaces:** TCD_SEGMENT_LABELS; TCD_NIGHTS_BIN_ORDER; is_complete_tcd_period(df) -> bool; estimate_tcd_los_by_segment(df, upper_open_bin_nights=8.5) -> DataFrame; resolve_tcd_source_unit(df, meta) -> str | None.

- [x] Reproduce the current LOS result for an incomplete period before extracting the calculation.
- [x] Validate exactly two series and eight unique bins each, finite nonnegative values and one period/release.
- [x] Preserve complete-period calculation values; return no indicators for an incomplete period.
- [x] Resolve a single supported unit (千泊 or 泊) from matching URL/digest metadata; reject absent, stale, conflicting or mixed units.
- [x] Run focused tests and record the presentation contract in the TCD specification.

## Task 3: Streamlit integration and automatic checks

**Files:** app.py; tests/test_stats_views.py; make_release_zip.py; tests/test_release_package.py; .github/workflows/test.yml; docs/spec_app.md; README.md. Remove two pre-existing unused imports in tests/test_update_events_data.py to enable the existing Ruff command.

- [x] Add UI tests with temporary DBs: TA all-segments equals company totals and excludes aggregate labels; incomplete TCD displays a reason and no LOS metrics; complete TCD displays the verified source unit.
- [x] Observe the TA and TCD regression assertions fail against the current app.
- [x] Import the new modules, filter TA rows on load, use total-only KPI/ranking inputs, and remove the duplicated TCD calculation from app.py.
- [x] Show TCD hold reasons and source units without zero-filling unknown values. Unknown unit permits inspecting original rows but does not create a cross-series comparison or LOS.
- [x] Add a read-only PR/main test workflow for Python 3.11 and 3.12, frozen dependencies, Ruff and pytest; do not run data collection or publishing.
- [x] Include the new stats package in release ZIP selection, with a regression check.
- [x] Run focused tests, full pytest, Ruff, seven-entry AppTest smoke and git diff --check.
- [x] Verify data/** and dependency files match the base, obtain an independent review, and prepare the branch for a draft PR linked to focused Issue #25 and parent review Issue #24.

## Alternatives considered

- A UI-only arithmetic patch would leave parser contamination and future reprocessing unresolved.
- A full page/source rewrite would enlarge the review surface without being needed for these defects.
- The selected bounded fix shares the affected rules, protects current presentation and gives the normal updater a versioned repair path.

## Rollout and rollback

The draft PR proposes code/spec/test changes only. After review and merge, the UI filters legacy aggregate rows immediately and future authorized TA updates can regenerate company-only rows. Data publication and verification remain separate from PR creation. Reverting the PR restores the previous code; no irreversible data migration is included.

## Verification record (2026-10-26)

- Base: fdd9456599b94cd193cb50f499d0815f030adb07.
- Focused TA/TCD/UI/package tests: 148 passed. Tests first reproduced spaced totals, incomplete TCD periods, unit omissions, unsafe TA partial replacement and missing ZIP runtime modules.
- Full suite on Python 3.12.14 with frozen dependencies: 580 passed and 96 subtests passed. The test temporary root was outside a Git worktree so archive-preview safety checks used an actual archive location.
- Ruff and git diff --check passed. One existing Streamlit/Altair deprecation warning remains in tests.
- AppTest: all seven navigation entries completed without exceptions against the bundled DB. TA 2025 / 2026-03 displays 404,845,156 (千円), rounding the company total 404,845,155.544 rather than adding aggregate and segment totals.
- The 41 selected TCD periods resolve their source units; eight historical incomplete quarters are rejected for whole-period indicator calculation.
- Independent review found a missing ZIP include and a TCD documentation mismatch; both were resolved. No outstanding implementation defects were identified in that review.
- data/**, pyproject.toml and uv.lock match the base. Live retrieval, real-data regeneration, Release publication and external LP updates were not run. Python 3.11 validation is delegated to the proposed CI matrix.
- Residual boundary: TA collection/classification/parsing failures preserve the prior output, but atomic DB-plus-metadata writes remain R05 in Issue #24. Unsupported sources can intentionally stop future updates until corrected.
