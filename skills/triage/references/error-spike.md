# error-spike

Symptom: a growing volume of errors with no correlated deploy.

There is no error tracker (see `STACK.md`), so there is no grouping and no event
count. Everything here is done against Cloud Logging directly, and the first job
is usually to establish what the group even *is*.

Checks:

1. **Search `lessons.md` first.** Recurrence of a previously resolved failure is
   more common than a new one, and the entry usually names the fix.
2. **Pull the actual lines.**
   `gcloud logging read 'resource.type="cloud_run_revision"
   resource.labels.service_name="smoodie-api" severity>=ERROR'
   --project smoodie-dev --limit 50 --format=json`
   Segment by revision, endpoint, and status code. A spike concentrated in one
   revision is a deploy question — go to `deploy-regression.md`.
3. **Distinguish "throwing" from "refusing".** A 401 or 422 in volume is usually
   a contract change, not a crash. This system returns deliberate 4xx for
   recipe-validation failures, and a spike of those means the composer and the
   API disagree about the schema — check whether the discriminated union is
   still tagged, since a wrapper once silently discarded the discriminator and
   made every invalid recipe report errors from both branches at once.
4. **Check the boring causes before the interesting ones**: Cloud SQL connection
   exhaustion (the instance is `db-f1-micro`, shared-core, and small), a Firebase
   IAM role that was changed, or an expired session cookie population after a
   revocation.
5. **If the symptom is opaque, improve the signal.** A generic 401 hid a Firebase
   permission error here until the underlying exception was logged. Proposing a
   logging change is a legitimate outcome of triage, not a failure to diagnose.
6. If the group meets the thresholds in `policy/errors.md`, hand to `skills/fix`.
   If the thresholds cannot be evaluated — and today they usually cannot — say
   that plainly rather than assuming they were met.

Provenance: (seed, unverified)
