# Capability bindings

Skills name capabilities — "metrics", "logs", "errors". This file is the only
place that says which tool provides one. A vendor name inside a skill is a bug:
it makes the skill unportable and it goes stale silently.

Two GCP projects, both `us-central1`: `smoodie-dev` (939870663311) and
`smoodie-prod` (305368155388). Dev is the only environment currently serving.

| Capability | Tool | Access |
|---|---|---|
| metrics | Cloud Monitoring, per project | read (`monitoring.googleapis.com/v3`) |
| logs | Cloud Logging, per project | read (`gcloud logging read`) |
| traces | Cloud Trace (API enabled, app not instrumented) | none in practice |
| errors | **none** | — |
| code host | GitHub `wzrd-nvr/smoodie` | read + open PR |
| pager | **none** | — |
| alert channels | **none** | — |
| feature flags | **none** | — |
| event warehouse | BigQuery `smoodie_analytics.events` (smoodie-dev) | read (`bq query`) |
| deploy history | GitHub Actions `deploy.yml`, Cloud Run revisions | read |
| database | Cloud SQL Postgres 16, `smoodie-dev:us-central1:smoodie-dev` | read via proxy; **no agent writes** |

## Gaps

What the agent cannot see, and what that costs:

- **No error tracker.** Uncaught exceptions reach Cloud Logging as Cloud Run
  stderr stack traces. There is no grouping, no fingerprint, and no event count,
  so the autofix thresholds in `policy/errors.md` cannot be evaluated
  mechanically — a human has to hand an error group over. This is the single
  largest gap in the layout.
- **No alert policies and no notification channels** exist in either project
  (verified empty via the Monitoring API). Nothing pages, so nothing arrives
  unprompted; triage today is always human-initiated.
- **No request correlation.** The API does not emit a request id or propagate
  the Cloud Run trace header, so a log line cannot be tied to the request that
  produced it. `policy/errors.md` names this as the first thing to fix.
- **The event warehouse is wired but not fed.** Schema, subscription and views
  exist and were verified end to end with hand-published messages; the outbox
  publisher that would fill the table from real traffic is issue #23. Until it
  lands, BigQuery answers questions about the pipeline, not about users.
- **No preview environments.** One deployed environment (dev), updated on every
  push to `main`. A smoke test therefore only ever describes `main`, never a
  pull request — see the `smoke` target in the `Makefile`.
