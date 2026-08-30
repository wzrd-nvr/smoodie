# smoodie infrastructure

Terraform for `smoodie-dev` and `smoodie-prod` (us-central1). The `baseline` module
provisions: enabled APIs, Artifact Registry, media bucket, Pub/Sub topic +
BigQuery dataset/table + BigQuery subscription (the event pipeline landing zone),
runtime service accounts, and Workload Identity Federation for GitHub Actions.
Cloud Run services + Cloud SQL arrive with issue
"[infra] Dev env Cloud Run + Cloud SQL, first deploy".

## One-time human steps (before first apply)

These need an owner with billing access — Terraform can't bootstrap them:

```sh
gcloud auth login && gcloud auth application-default login

# 1. Create the projects and link billing
gcloud projects create smoodie-dev
gcloud projects create smoodie-prod
gcloud billing projects link smoodie-dev  --billing-account=BILLING_ACCOUNT_ID
gcloud billing projects link smoodie-prod --billing-account=BILLING_ACCOUNT_ID

# 2. Create state buckets (per env)
gcloud storage buckets create gs://smoodie-dev-tfstate  --project smoodie-dev  --location us-central1 --uniform-bucket-level-access
gcloud storage buckets create gs://smoodie-prod-tfstate --project smoodie-prod --location us-central1 --uniform-bucket-level-access
```

Then uncomment the `backend "gcs"` block in each env's `main.tf`.

## Apply

```sh
cd infra/terraform/envs/dev
terraform init
terraform plan    # review!
terraform apply
```

After apply, wire GitHub Actions deploys by setting repo variables from the outputs:

```sh
gh variable set GCP_WIF_PROVIDER --body "$(terraform output -raw wif_provider)"
gh variable set GCP_DEPLOYER_SA  --body "$(terraform output -raw deployer_sa)"
```
