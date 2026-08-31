# Firebase Auth (Identity Platform under the hood).
#
# MVP ships email/password only. Google sign-in needs an OAuth client id and
# secret, which cannot be minted without a one-time consent-screen setup in the
# console — it is tracked separately rather than blocking auth on a manual step.

resource "google_project_service" "auth_apis" {
  for_each = toset([
    "firebase.googleapis.com",
    "identitytoolkit.googleapis.com",
  ])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_firebase_project" "this" {
  provider   = google-beta
  project    = var.project_id
  depends_on = [google_project_service.auth_apis]
}

resource "google_firebase_web_app" "web" {
  provider        = google-beta
  project         = var.project_id
  display_name    = "smoodie ${var.env}"
  deletion_policy = "DELETE"
  depends_on      = [google_firebase_project.this]
}

data "google_firebase_web_app_config" "web" {
  provider   = google-beta
  project    = var.project_id
  web_app_id = google_firebase_web_app.web.app_id
}

resource "google_identity_platform_config" "auth" {
  provider = google-beta
  project  = var.project_id

  sign_in {
    allow_duplicate_emails = false
    email {
      enabled           = true
      password_required = true
    }
    # Declared explicitly rather than omitted: GCP populates these blocks itself,
    # so leaving them out produces a phantom diff on every plan. Stating them
    # also makes "phone auth is off" an intentional, reviewable fact.
    phone_number {
      enabled            = false
      test_phone_numbers = {}
    }
  }

  multi_tenant {
    allow_tenants = false
  }

  depends_on = [google_firebase_project.this]
}

# The web client config is not secret — the API key is a project identifier that
# only works against rules/allowlists — but it is env-specific, so it is surfaced
# as outputs and injected into the web service rather than committed.
output "firebase_api_key" {
  value     = data.google_firebase_web_app_config.web.api_key
  sensitive = true
}
output "firebase_auth_domain" {
  value = data.google_firebase_web_app_config.web.auth_domain
}
output "firebase_app_id" {
  value = google_firebase_web_app.web.app_id
}
output "firebase_project_id" {
  value = var.project_id
}
