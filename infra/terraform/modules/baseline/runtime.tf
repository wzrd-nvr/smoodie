# Cloud SQL + Cloud Run: the deployed runtime for smoodie.
#
# The instance uses a public IP with NO authorized networks. That is not an open
# database: without an authorized network, the only way in is the Cloud SQL Auth
# proxy built into Cloud Run, which authenticates with IAM and encrypts in
# transit. Private IP would need VPC peering plus a connector for egress, which
# is real monthly cost and complexity this environment does not need yet.

resource "google_sql_database_instance" "main" {
  project             = var.project_id
  name                = "smoodie-${var.env}"
  region              = var.region
  database_version    = "POSTGRES_16"
  deletion_protection = var.sql_deletion_protection

  settings {
    tier = var.sql_tier
    # Shared-core tiers (db-f1-micro/db-g1-small) exist only on ENTERPRISE;
    # the API defaults new instances to ENTERPRISE_PLUS, which rejects them.
    edition           = "ENTERPRISE"
    availability_type = "ZONAL"
    disk_size         = 10
    disk_type         = "PD_SSD"
    disk_autoresize   = true

    ip_configuration {
      ipv4_enabled = true
      ssl_mode     = "ENCRYPTED_ONLY"
      # Deliberately no authorized_networks: proxy/IAM access only.
    }

    backup_configuration {
      enabled                        = true
      start_time                     = "09:00" # UTC, ~2-4am US
      point_in_time_recovery_enabled = true
      backup_retention_settings {
        retained_backups = 7
      }
    }

    maintenance_window {
      day  = 2 # Tuesday
      hour = 10
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_sql_database" "smoodie" {
  project  = var.project_id
  instance = google_sql_database_instance.main.name
  name     = "smoodie"
}

resource "random_password" "db_app_user" {
  length  = 32
  special = false # avoids URL-encoding pitfalls in the DSN
}

resource "google_sql_user" "app" {
  project  = var.project_id
  instance = google_sql_database_instance.main.name
  name     = "smoodie_app"
  password = random_password.db_app_user.result
}

# ------------------------------------------------------------------ secrets
resource "google_secret_manager_secret" "database_url" {
  project   = var.project_id
  secret_id = "smoodie-database-url"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

# asyncpg over the Cloud Run unix socket: host is the socket directory, so the
# DSN carries no hostname. Alembic and the app both read this one value.
resource "google_secret_manager_secret_version" "database_url" {
  secret = google_secret_manager_secret.database_url.id
  secret_data = format(
    "postgresql+asyncpg://%s:%s@/%s?host=/cloudsql/%s",
    google_sql_user.app.name,
    random_password.db_app_user.result,
    google_sql_database.smoodie.name,
    google_sql_database_instance.main.connection_name,
  )
}

resource "google_secret_manager_secret_iam_member" "api_database_url" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.database_url.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

# ---------------------------------------------------------------- Cloud Run
locals {
  # Terraform creates the services before any image exists. The deploy pipeline
  # pushes real images and updates them; ignore_changes keeps Terraform from
  # reverting a deploy on the next apply.
  placeholder_image = "us-docker.pkg.dev/cloudrun/container/hello"
}

resource "google_cloud_run_v2_service" "api" {
  project             = var.project_id
  name                = "smoodie-api"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.api.email
    scaling {
      min_instance_count = 0
      max_instance_count = 4
    }

    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.main.connection_name]
      }
    }

    containers {
      image = local.placeholder_image
      ports {
        container_port = 8080
      }

      env {
        name  = "SMOODIE_ENV"
        value = var.env
      }
      # firebase-admin verifies tokens against this project using ADC.
      env {
        name  = "SMOODIE_FIREBASE_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "SMOODIE_MEDIA_BUCKET"
        value = google_storage_bucket.media.name
      }
      env {
        name = "SMOODIE_DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_url.secret_id
            version = "latest"
          }
        }
      }

      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
      # GCP populates a service-level scaling block we never set; without this
      # every future plan shows a phantom in-place update.
      scaling,
    ]
  }

  depends_on = [
    google_secret_manager_secret_iam_member.api_database_url,
    google_secret_manager_secret_version.database_url,
  ]
}

resource "google_cloud_run_v2_service" "web" {
  project             = var.project_id
  name                = "smoodie-web"
  location            = var.region
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.web.email
    scaling {
      min_instance_count = 0
      max_instance_count = 4
    }

    containers {
      image = local.placeholder_image
      ports {
        container_port = 3000
      }

      env {
        name  = "NODE_ENV"
        value = "production"
      }
      # Loaders call the API server-to-server using this base URL.
      env {
        name  = "API_BASE_URL"
        value = google_cloud_run_v2_service.api.uri
      }
      # Firebase web client config. The API key is a project identifier rather
      # than a credential, but it is env-specific so it is injected, not committed.
      env {
        name  = "FIREBASE_API_KEY"
        value = data.google_firebase_web_app_config.web.api_key
      }
      env {
        name  = "FIREBASE_AUTH_DOMAIN"
        value = data.google_firebase_web_app_config.web.auth_domain
      }
      env {
        name  = "FIREBASE_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "FIREBASE_APP_ID"
        value = google_firebase_web_app.web.app_id
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
      # GCP populates a service-level scaling block we never set; without this
      # every future plan shows a phantom in-place update.
      scaling,
    ]
  }
}

# Public web app: the API enforces its own auth via Firebase session cookies.
resource "google_cloud_run_v2_service_iam_member" "api_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "web_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.web.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Deployer needs to read the DSN to run migrations as a Cloud Run job.
resource "google_secret_manager_secret_iam_member" "deployer_database_url" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.database_url.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.deployer.email}"
}

output "api_url" {
  value = google_cloud_run_v2_service.api.uri
}
output "web_url" {
  value = google_cloud_run_v2_service.web.uri
}
output "sql_connection_name" {
  value = google_sql_database_instance.main.connection_name
}
