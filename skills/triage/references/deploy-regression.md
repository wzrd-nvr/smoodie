# deploy-regression

Symptom: errors, 5xx, or a behaviour change within ~30 minutes of a merge to
`main`. Every merge deploys to dev automatically, so "recent deploy" is the
default explanation and has to be ruled in or out first, not last.

The pipeline is: build both images → run migrations as a Cloud Run job → deploy
API → deploy web → smoke test. Failures cluster differently at each stage.

Checks, in order:

1. **Find the deploy.** `gh run list --workflow=deploy.yml --limit 5`. Note
   whether it succeeded, and which step failed if not. The smoke test asserts
   `"database":"ok"` from `/health` and that the web root renders — a green
   deploy means both of those held at deploy time.
2. **Did the migration stage run?** Migrations execute *before* the new image
   serves, so a migration that failed leaves the old code running against the
   old schema (recoverable), while a migration that succeeded before a failed
   deploy leaves the new schema under the old code (not). Check the
   `smoodie-migrate` Cloud Run job execution, not just the workflow step.
3. **Compare Cloud Run revisions.** `gcloud run revisions list --service
   smoodie-api --region us-central1 --project smoodie-dev`. The revision suffix
   maps to the commit sha the workflow built.
4. **Diff the commit range** and list the files touched that intersect the
   failing code path.
5. **Rule out configuration.** A missing or wrong environment variable produces
   a clean deploy and wrong behaviour, and has done so here before: the media
   bucket variable was absent from the service for a full release while every
   test passed. Read the deployed service's env, do not infer it from Terraform:
   `gcloud run services describe smoodie-api --format='value(spec.template.spec.containers[0].env)'`.
6. **Rule out a concurrent dependency failure** — see `dependency-outage.md`.

Proposal: a revert PR is the default, because there are no feature flags in this
system and therefore no ramp to propose. If the change is a migration, a revert
of the code does **not** revert the schema; say so explicitly and propose the
downgrade separately. Migration downgrades have been wrong here before — one
shipped migration failed to drop its enum type, so rollback-then-reapply broke.

Provenance: (seed, unverified)
