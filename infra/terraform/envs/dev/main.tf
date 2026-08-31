terraform {
  required_version = ">= 1.9"
  backend "gcs" {
    bucket = "smoodie-dev-tfstate"
    prefix = "envs/dev"
  }
}

# user_project_override + billing_project: some APIs (identitytoolkit) reject
# user ADC without an explicit quota project. Setting it here keeps the fix in
# the config instead of relying on per-machine gcloud state.
provider "google" {
  project               = var.project_id
  region                = var.region
  user_project_override = true
  billing_project       = var.project_id
}

provider "google-beta" {
  project               = var.project_id
  region                = var.region
  user_project_override = true
  billing_project       = var.project_id
}

variable "project_id" {
  type    = string
  default = "smoodie-dev"
}
variable "region" {
  type    = string
  default = "us-central1"
}

module "baseline" {
  source     = "../../modules/baseline"
  project_id = var.project_id
  region     = var.region
  env        = "dev"
}

output "artifact_registry" { value = module.baseline.artifact_registry }
output "api_url" { value = module.baseline.api_url }
output "web_url" { value = module.baseline.web_url }
output "sql_connection_name" { value = module.baseline.sql_connection_name }
output "firebase_project_id" { value = module.baseline.firebase_project_id }
output "firebase_auth_domain" { value = module.baseline.firebase_auth_domain }
output "firebase_app_id" { value = module.baseline.firebase_app_id }
output "firebase_api_key" {
  value     = module.baseline.firebase_api_key
  sensitive = true
}
output "wif_provider" { value = module.baseline.wif_provider }
output "deployer_sa" { value = module.baseline.deployer_sa }
output "media_bucket" { value = module.baseline.media_bucket }
