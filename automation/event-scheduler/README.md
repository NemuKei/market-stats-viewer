# Official event scheduler: local prototype, NOT deployed

This directory is deliberately not wired into active workflows. No wrangler deployment configuration, secrets, account changes, cron changes, or dispatches were created. `templates/update_events_official_external.yml.example` is a review artifact, not an enabled workflow.

## Minimal proposed infrastructure

- A **new isolated** Cloudflare Worker with exactly one Cron Trigger (`*/5 * * * *`). Do not modify unrelated existing production workers.
- One SQLite Durable Object binding `COORDINATOR`, class `OfficialScheduleCoordinator`; single object name `official` serializes all schedule slots.
- Bundle `src/worker.mjs` using esbuild, external `cloudflare:workers`; compatibility validated locally at `2026-08-06` only. Installed workerd rejects `2026-11-10`. Revalidate against the deployment runtime before enabling.
- Preserve existing calendar meaning: days 1,4,7,... each month at 04:00 UTC. This is not a strict 72-hour interval. Dispatch may occur in the following four hours only. No automatic catch-up outside that window.
- GitHub App installed only on `NemuKei/market-stats-viewer`: Actions write + Metadata read. No Contents write. Actions permission remains repository-wide, not workflow-scoped; code pins workflow and main. App private key stored only in an approved Cloudflare secret; never in source, logs or Actions inputs.
- GitHub Actions `id-token: write` on this official workflow is an additional permission. The workflow obtains a signed short-lived OIDC token for the Worker audience and passes it only to `/admit`.

## Required config, all absent from live environment

`ENABLED` must equal `true`; `CUTOVER_DRAINED` must equal `true`; otherwise no dispatch/admission.
`CUTOVER_AT` is the earliest permitted expected UTC slot.
`GATE_BLOB_SHA` pins the exact Git blob hash of the reviewed workflow after adoption.
`AUDIENCE` is the exact HTTPS Worker origin (no trailing slash).
`REPOSITORY_ID` is the verified numeric GitHub repository ID, not a name assumption.
`GITHUB_APP_ID`, `GITHUB_INSTALLATION_ID`, secret `GITHUB_APP_PRIVATE_KEY` (PKCS8 RSA).
Repository variable `EVENT_SCHEDULER_ORIGIN` must equal `AUDIENCE`.

## Safety contract and cutover

1. Review and separately authorize new permissions, credentials, infrastructure, budget and production deployment. Local tests are not authorization.
2. Adopt the reviewed admission script and **new path** `update_events_official_external.yml` template. Never reuse the old scheduled workflow path. Keep the external Worker disabled. Record the exact new workflow blob SHA.
3. Explicitly disable the old `update_events_official.yml` workflow (requires approval) and inspect all outstanding old-definition runs. Wait for terminal state or obtain cancellation approval. Removing a cron or seeing an empty active list is NOT sufficient: previously scheduled but not yet created events can carry old definitions. Verify disabling actually prevents late old-definition execution. **Production enablement is blocked until this boundary is verified.**
4. Preflight requires old workflow state `disabled_manually`, pins the new workflow blob without cron, and checks both paths for queued/in-progress/pending/requested/waiting runs. Pin config and separately approve drained/enabled for a future slot. Old-definition safety still depends on GitHub honoring workflow disable; this cannot be validated in local mocks.
5. For each slot, persist intent+random nonce **before** the single dispatch POST. HTTP error, timeout, malformed body, and connection uncertainty become `uncertain`; never auto-resend. Current GitHub API `2026-03-10` successful dispatch is expected to return 200 + `workflow_run_id`.
6. All new-version runs must pass signed OIDC checks (issuer, audience, numeric repo ID, repo name, main, workflow path, exact workflow blob, run ID and attempt 1) plus slot/nonce ownership. Native schedule and manual rerun are denied. Repeated admission for the same run/attempt is idempotent; a second run cannot own the slot.
7. An unresolved older slot blocks later slots. Operator recovery is intentionally not implemented. Inspect GitHub and the persisted state before any future explicitly authorized recovery. Do not clear records or retry uncertain slots casually.
8. A completed workflow without admission is `not_admitted`, never collection success. A run success does not verify Build LP events data correctness, commit, downstream Release, matching manifest or public JSON. Existing read-only downstream verification remains necessary.

## Monitoring limits

Scheduled logs contain only status/slot/run ID and observed/expected scheduling timestamps; no nonce/token or raw error bodies. State distinguishes preflight blocked, ambiguous dispatch, missing admission, running and terminal conclusion. External notifications/alert rules have NOT been provisioned. A running Worker is not evidence that alerts reach the user. Configure and test an approved delivery route before promising monitoring. `scripts/audit_workflow_timing.py` independently distinguishes expected time, run creation and runner start.

## Cost and permissions before launch

This proposal needs one Cron Trigger. Check the account's existing trigger count against the current plan limit before activation (Free cap was 5 when researched). Five-minute ticks imply 288/day or 8,640 per 30 days, plus admission requests and Durable Object storage/compute. **Zero incremental cost is not verified.** Confirm the actual account plan, remaining shared quota, DO limits and an explicit budget; no paid upgrade is part of this prototype. Cloudflare Paid starts USD 5/month per the documentation checked for this design. Cron changes can take up to 15 minutes to propagate and do not promise second-level punctuality.

Activation needs approved Cloudflare Worker/DO/Cron deployment access, secret write, GitHub App creation/installation+private key handling, workflow OIDC permission change, repo variable/main workflow change, and explicit production cutover. Existing read-only connectors do not grant the Worker runtime credentials.

## Local verification

`npm ci --cache /tmp/event-scheduler-npm` then `npm test` (Node 22+, Node 24 tested).
Tests use synthetic keys and mocked HTTP with real network disabled; no production API calls.
29 Node tests include real workerd SQLite persistence/restart and uncertain dispatch; Python admission and timing tests run from repo root. Dependencies are locked in package-lock.json. No live auth or actual Cloudflare/GitHub interoperability has been tested.
