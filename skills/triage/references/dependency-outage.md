# dependency-outage

Symptom: timeouts or 5xx that trace to something smoodie does not run, with a
clean deploy history.

Every dependency here is Google-operated, which makes the vendor status page
less useful than it sounds — a regional Cloud SQL or IAM problem frequently does
not appear there. Prefer direct probes.

| Dependency | What breaks when it does | Direct probe |
|---|---|---|
| Cloud SQL (`smoodie-dev:us-central1:smoodie-dev`) | every authenticated request; posts and profiles both | `/health` returns `"database"` other than `"ok"` |
| Firebase Auth / Identity Platform | login and session-cookie exchange; existing cookies keep working until they expire | `POST /v1/auth/session` with a fresh ID token |
| Cloud Storage (media bucket) | avatar and photo uploads; a recipe cannot be published without a photo, so this blocks publishing too | issue a signed URL and PUT to it |
| Pub/Sub → BigQuery | nothing user-visible; events stop landing, permanently and silently | see `pipeline-gap.md` |

Checks:

1. Probe the dependency directly before believing a status page.
2. **Establish blast radius from the flows, not the services.** Publishing a
   recipe requires the database *and* the bucket, so a bucket failure looks like
   a posting failure rather than an upload failure.
3. Distinguish an outage from a permission change. IAM edits present exactly like
   an outage and are far more likely in a project this young; a Firebase
   `INSUFFICIENT_PERMISSION` here was a missing role, not a Google incident.
4. There is no circuit breaker and no degraded mode in this system, so there is
   no flag to propose. The realistic proposals are: wait, fix the permission, or
   draft the status line for a human to post.

Provenance: (seed, unverified)
