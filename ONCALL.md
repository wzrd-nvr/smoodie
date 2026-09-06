# On-call policy

> **DRAFT — needs human sign-off.** Every threshold and window below was written
> by an agent reading the repository and the two GCP projects, not transcribed
> from an agreed team policy, because no such policy existed when this file was
> created. Numbers marked **(proposed)** are guesses with reasoning attached and
> should be confirmed or replaced before anyone relies on them. Nothing here
> takes effect automatically: no alert policy or notification channel exists in
> either project yet.

Humans only edit this file. Change it by pull request.

## Where things actually stand

- `smoodie-dev` is the only environment serving. Every push to `main` deploys to
  it, migrations first, then API, then web (`.github/workflows/deploy.yml`).
- `smoodie-prod` exists as a project with Artifact Registry and WIF. It has no
  Cloud SQL instance and no deploy path — that is issue #29 and issue #27.
- There are no users. Traffic is the maintainer and CI.

The practical consequence: the thresholds below describe what should happen
*once prod carries traffic*. Before then, "page" means "open a GitHub issue and
label it `oncall`", because there is nowhere else for a page to go.

## Paging criteria (proposed)

Page if ANY, sustained outside an in-flight deploy:

- Cloud Run 5xx rate > 2% of requests over 5 minutes **(proposed)**
- API `/health` reports `"database":"ok"` false, or fails to respond, twice in a
  row 60s apart — this endpoint already proves Cloud SQL reachability and the
  deploy smoke test relies on it
- p99 request latency > 2x the 7-day baseline for 10 minutes **(proposed —
  there is no baseline yet; it cannot be computed until prod has traffic)**
- Any failed migration step in `deploy.yml`. A migration runs before the new
  image serves, so a failure there leaves the schema and the running code
  disagreeing, which is the highest-consequence failure the pipeline has.

Otherwise: write it to the morning log, do not page.

## Deploy windows

- **dev:** none. Every merge to `main` deploys. This is deliberate and should
  stay that way while there are no users.
- **prod:** no deploy path exists yet. When it does (issue #27), it is gated on
  a GitHub Environment approval, and the proposed window is Mon–Thu, daylight
  hours for the maintainer, never Friday **(proposed)**.

## Routing

Single maintainer. There is no rotation and no second escalation hop, which is
itself a risk worth naming rather than papering over with a fictional team.

| Failure class | Owner | Escalate after |
|---|---|---|
| deploy-regression | @wzrd-nvr | — |
| error-spike | @wzrd-nvr | — |
| dependency-outage (Firebase, Cloud SQL, GCS, Pub/Sub) | @wzrd-nvr | — |
| pipeline-gap (events not reaching BigQuery) | @wzrd-nvr | — |

## Severity norms

Written against smoodie's actual core flows rather than generic wording:

- **sev1** — a user cannot sign in, cannot publish a recipe, or cannot load a
  recipe page. Also: the event pipeline is dropping writes, because that loss is
  permanent and silent, and the events are the phase-2 training corpus.
- **sev2** — degraded with a workaround: avatar upload fails but posting works;
  the feed is slow; an edit returns stale data but the database is correct.
- **sev3** — cosmetic, or internal-only.

## Incident records

Opened by a human as a GitHub issue labelled `type:bug` + `oncall`. The agent
never opens and never closes one.
