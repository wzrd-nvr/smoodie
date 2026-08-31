terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

variable "project_id" { type = string }
variable "region" { type = string }
variable "env" { type = string } # "dev" | "prod"
variable "github_repo" {
  type    = string
  default = "wzrd-nvr/smoodie"
}
variable "deploy_ref" {
  type    = string
  default = "refs/heads/main" # only this ref may impersonate the deployer SA
}
variable "media_cors_origins" {
  type = list(string)
  # Dev origins by default; prod env overrides with the real app domains.
  default = ["http://localhost:5173", "http://localhost:3000"]
}
variable "sql_tier" {
  type = string
  # Shared-core is ample for pre-launch dev traffic (~$9/mo). Prod moves to a
  # dedicated tier in M5; the instance can be resized without recreation.
  default = "db-f1-micro"
}
variable "sql_deletion_protection" {
  type    = bool
  default = true
}
variable "bigquery_deletion_protection" {
  type = bool
  # Safe by default: the events table is the ML training corpus. Schema changes
  # need a two-step apply — set this false, apply, then apply the schema change.
  default = true
}

locals {
  # Note: cloudresourcemanager, serviceusage and iam must be enabled out of band
  # before the first apply — with user_project_override the provider needs them
  # just to read state. They are listed here so they stay enabled, not to
  # bootstrap them. See infra/terraform/README.md.
  apis = [
    "cloudresourcemanager.googleapis.com",
    "serviceusage.googleapis.com",
    "iam.googleapis.com",
    "run.googleapis.com",
    "cloudbuild.googleapis.com",
    "sqladmin.googleapis.com",
    "artifactregistry.googleapis.com",
    "pubsub.googleapis.com",
    "bigquery.googleapis.com",
    "secretmanager.googleapis.com",
    "iamcredentials.googleapis.com",
    "compute.googleapis.com",
    "servicenetworking.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each           = toset(local.apis)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# ---------------------------------------------------------------- registry
resource "google_artifact_registry_repository" "docker" {
  project       = var.project_id
  location      = var.region
  repository_id = "smoodie"
  format        = "DOCKER"
  depends_on    = [google_project_service.apis]
}

# ---------------------------------------------------------------- media
resource "google_storage_bucket" "media" {
  project                     = var.project_id
  name                        = "smoodie-${var.env}-media"
  location                    = var.region
  uniform_bucket_level_access = true
  cors {
    origin          = var.media_cors_origins
    method          = ["GET", "PUT"]
    response_header = ["Content-Type"]
    max_age_seconds = 3600
  }
}

# ---------------------------------------------------------------- events
resource "google_pubsub_topic" "events" {
  project    = var.project_id
  name       = "smoodie-events"
  depends_on = [google_project_service.apis]
}

resource "google_bigquery_dataset" "analytics" {
  project    = var.project_id
  dataset_id = "smoodie_analytics"
  location   = "US"
  depends_on = [google_project_service.apis]
}

resource "google_bigquery_table" "events" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.analytics.dataset_id
  table_id            = "events"
  deletion_protection = var.bigquery_deletion_protection

  time_partitioning {
    type  = "DAY"
    field = "occurred_at"
  }
  clustering = ["event_type"]

  schema = jsonencode([
    { name = "event_id", type = "STRING", mode = "REQUIRED" },
    { name = "event_type", type = "STRING", mode = "REQUIRED" },
    { name = "schema_version", type = "INT64", mode = "REQUIRED" },
    { name = "actor_id", type = "STRING", mode = "NULLABLE" },
    { name = "entity_type", type = "STRING", mode = "NULLABLE" },
    { name = "entity_id", type = "STRING", mode = "NULLABLE" },
    { name = "occurred_at", type = "TIMESTAMP", mode = "REQUIRED" },
    # STRING, not JSON: a Pub/Sub BigQuery subscription silently drops every
    # message whose target column is JSON-typed. Payload lands as JSON text and
    # the per-event views wrap it in PARSE_JSON.
    { name = "payload", type = "STRING", mode = "NULLABLE" },
  ])
}

resource "google_pubsub_subscription" "events_to_bq" {
  project = var.project_id
  name    = "smoodie-events-bq"
  topic   = google_pubsub_topic.events.id

  bigquery_config {
    table            = "${var.project_id}.${google_bigquery_dataset.analytics.dataset_id}.${google_bigquery_table.events.table_id}"
    use_table_schema = true
  }
  depends_on = [google_bigquery_table_iam_member.pubsub_writer]
}

data "google_project" "this" {
  project_id = var.project_id
}

# Table-scoped (least privilege), with the lifecycle tied to the table itself:
# a table-scoped binding is destroyed along with the table on any schema change,
# and without replace_triggered_by Terraform would not recreate it — leaving the
# subscription failing writes silently, with no error and no dead letter.
resource "google_bigquery_table_iam_member" "pubsub_writer" {
  project    = var.project_id
  dataset_id = google_bigquery_dataset.analytics.dataset_id
  table_id   = google_bigquery_table.events.table_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-pubsub.iam.gserviceaccount.com"

  lifecycle {
    replace_triggered_by = [google_bigquery_table.events]
  }
}

# ------------------------------------------------------- runtime accounts
resource "google_service_account" "api" {
  project      = var.project_id
  account_id   = "smoodie-api"
  display_name = "smoodie API runtime"
}

resource "google_service_account" "web" {
  project      = var.project_id
  account_id   = "smoodie-web"
  display_name = "smoodie web runtime"
}

resource "google_project_iam_member" "api_roles" {
  for_each = toset([
    "roles/cloudsql.client",
    "roles/pubsub.publisher",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.api.email}"
}

# objectUser: create/read/delete objects without ACL or bucket administration.
resource "google_storage_bucket_iam_member" "api_media" {
  bucket = google_storage_bucket.media.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.api.email}"
}

# --------------------------------------------- GitHub Actions via WIF
resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.repo_ref"   = "assertion.repository + \"@\" + assertion.ref"
  }
  attribute_condition = "assertion.repository == \"${var.github_repo}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "deployer" {
  project      = var.project_id
  account_id   = "github-deployer"
  display_name = "GitHub Actions deployer"
}

# Only workflows on the deploy ref (main) may impersonate the deployer —
# PRs and other branches authenticate but get no principalSet match.
resource "google_service_account_iam_member" "deployer_wif" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repo_ref/${var.github_repo}@${var.deploy_ref}"
}

resource "google_project_iam_member" "deployer_roles" {
  for_each = toset([
    "roles/run.developer",
    "roles/artifactregistry.writer",
    "roles/cloudsql.client",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

# actAs scoped to the two runtime SAs only — never project-wide serviceAccountUser,
# which would let the deployer impersonate every SA in the project.
resource "google_service_account_iam_member" "deployer_act_as" {
  for_each = {
    api = google_service_account.api.name
    web = google_service_account.web.name
  }
  service_account_id = each.value
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

# ----------------------------------------------------------------- outputs
output "artifact_registry" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker.repository_id}"
}
output "wif_provider" {
  value = google_iam_workload_identity_pool_provider.github.name
}
output "deployer_sa" {
  value = google_service_account.deployer.email
}
output "api_sa" {
  value = google_service_account.api.email
}
output "media_bucket" {
  value = google_storage_bucket.media.name
}
