# Error contract

## What an error should carry

| Field | Today | Notes |
|---|---|---|
| `release` (git sha) | **missing** | Cloud Run revisions are tagged with the sha by `deploy.yml`, but the app does not know its own version, so a log line cannot name the release that produced it. |
| `env` | present | `SMOODIE_ENV` is set on every Cloud Run service. |
| `service` | present | Cloud Run resource labels distinguish `smoodie-api` from `smoodie-web`. |
| `request_id` / trace id | **missing** | Cloud Run sets `X-Cloud-Trace-Context` on every inbound request; nothing reads it. Without this, two log lines from the same request cannot be correlated. |
| `user_cohort` | **missing** | Must never be a raw user id or email. Firebase uid is PII-adjacent and must not be logged. |
| fingerprint for grouping | **missing** | Requires an error tracker; see `STACK.md` gaps. |

Closing the first three is prerequisite work for everything below. Until then,
triage reads raw Cloud Logging output and correlates by timestamp, which is slow
and occasionally wrong.

## Autofix trigger

Hand an error group to `skills/fix` only when ALL of:

- at least 10 events
- first seen less than 7 days ago — fresh, not legacy noise
- stack traces converge on a single code path
- not labelled `needs-product-decision`
- not in `infra/terraform/**` — infrastructure changes go through
  `infra-plan.yml` and a human at the Terraform CLI, never an autofix

Everything else gets a triage SITREP and stops there.

**These thresholds are currently unevaluable.** There is no error tracker, so
nothing produces an event count or a fingerprint. In practice a human hands over
a specific failure, and the agent's job is to say plainly that the trigger
conditions could not be checked rather than to assume they were met. Keep the
thresholds written down anyway: they are what the tracker has to be able to
answer when one is chosen.

## Things this codebase has already proven about its own errors

Each of these is a real failure from the build, and each one shaped a rule:

- **A green test suite is not evidence about production.** Signed URLs named the
  wrong bucket for an entire deploy because the tests use a fake object store
  and structurally could not observe the missing environment variable. Verify a
  fix against the deployed dev service, not only against the suite.
- **The absence of an error is not the absence of a failure.** A Pub/Sub
  subscription silently discarded every message aimed at a `JSON`-typed BigQuery
  column: no error, no dead letter, no delivery. When something is missing rather
  than broken, look for a silent drop before looking for an exception.
- **Adding a log line is a legitimate first move.** A Firebase permission failure
  surfaced only as a generic 401 until the underlying exception was logged; the
  root cause was one IAM role. If the symptom is opaque, improving the signal
  beats guessing at causes.

## Customer-facing loop

alert → SITREP → status line (a human posts it) → fix PR link → resolution note.
The agent drafts the status line and never publishes it.
