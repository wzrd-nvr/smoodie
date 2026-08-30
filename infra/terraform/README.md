# smoodie infrastructure

Terraform for `smoodie-dev` and `smoodie-prod` (us-central1). The `baseline` module
provisions: enabled APIs, Artifact Registry, media bucket, Pub/Sub topic +
BigQuery dataset/table + BigQuery subscription (the event pipeline landing zone),
runtime service accounts, and Workload Identity Federation for GitHub Actions.
Cloud Run services + Cloud SQL arrive with issue
"[infra] Dev env Cloud Run + Cloud SQL, first deploy".

## Status

Both environments are **provisioned and verified** (2026-08-30):

| | smoodie-dev | smoodie-prod |
|---|---|---|
| Project number | 939870663311 | 305368155388 |
| Artifact Registry | `us-central1-docker.pkg.dev/smoodie-dev/smoodie` | `us-central1-docker.pkg.dev/smoodie-prod/smoodie` |
| Events pipeline | verified end-to-end | verified end-to-end |

GitHub repo variables `GCP_{DEV,PROD}_{WIF_PROVIDER,DEPLOYER_SA,ARTIFACT_REGISTRY}`
are set from the Terraform outputs. Cloud Run and Cloud SQL are not provisioned
yet — they arrive with issue #6.

## Gotchas learned the hard way

- **`payload` is STRING, not JSON.** A Pub/Sub BigQuery subscription silently
  drops every message whose target column is JSON-typed — no error, no dead
  letter, the message just sits in the backlog retrying. Payload lands as JSON
  text; wrap it in `PARSE_JSON()` in the per-event views.
- **The Pub/Sub writer grant is dataset-scoped.** Table-scoped IAM is destroyed
  along with the table on any schema change, silently breaking ingestion.
- **Changing the events table schema is a two-step apply**: Terraform refuses to
  destroy a table while `deletion_protection` is true, and it won't clear the
  flag and replace the table in the same run. Apply the flag change alone first.
- `bigquery_deletion_protection` defaults to **false** pre-launch. Flip it to
  true in M5, before real data lands.

## Rebuilding from scratch

These need an owner with billing access — Terraform can't bootstrap them:

```sh
gcloud auth login && gcloud auth application-default login

# 1. Create the projects and link billing
gcloud projects create smoodie-dev  --name="smoodie dev"
gcloud projects create smoodie-prod --name="smoodie prod"
gcloud billing projects link smoodie-dev  --billing-account=BILLING_ACCOUNT_ID
gcloud billing projects link smoodie-prod --billing-account=BILLING_ACCOUNT_ID

# 2. Create state buckets (per env)
gcloud storage buckets create gs://smoodie-dev-tfstate  --project smoodie-dev  --location us-central1 --uniform-bucket-level-access
gcloud storage buckets create gs://smoodie-prod-tfstate --project smoodie-prod --location us-central1 --uniform-bucket-level-access
```

## Apply

```sh
cd infra/terraform/envs/dev
terraform init
terraform plan -out=tf.plan   # review!
terraform apply tf.plan
```

Re-wire deploy credentials after an apply that changes the WIF pool or SAs:

```sh
gh variable set GCP_DEV_WIF_PROVIDER --body "$(terraform output -raw wif_provider)"
gh variable set GCP_DEV_DEPLOYER_SA  --body "$(terraform output -raw deployer_sa)"
gh variable set GCP_DEV_ARTIFACT_REGISTRY --body "$(terraform output -raw artifact_registry)"
```

## Verifying the events pipeline

```sh
gcloud pubsub topics publish smoodie-events --project smoodie-dev \
  --message '{"event_id":"...","event_type":"smoke","schema_version":1,"occurred_at":"2026-01-01T00:00:00Z","payload":"{\"k\":\"v\"}"}'

# ~30-60s later
bq query --project_id=smoodie-dev --use_legacy_sql=false \
  'SELECT event_type, JSON_VALUE(PARSE_JSON(payload), "$.k") FROM `smoodie-dev.smoodie_analytics.events`'
```

An empty result with an ACTIVE subscription means writes are failing — check the
gotchas above rather than assuming delivery lag.
