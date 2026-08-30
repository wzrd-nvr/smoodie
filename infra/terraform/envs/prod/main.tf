terraform {
  required_version = ">= 1.9"
  backend "gcs" {
    bucket = "smoodie-prod-tfstate"
    prefix = "envs/prod"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

variable "project_id" {
  type    = string
  default = "smoodie-prod"
}
variable "region" {
  type    = string
  default = "us-central1"
}

module "baseline" {
  source     = "../../modules/baseline"
  project_id = var.project_id
  region     = var.region
  env        = "prod"
}

output "artifact_registry" { value = module.baseline.artifact_registry }
output "wif_provider" { value = module.baseline.wif_provider }
output "deployer_sa" { value = module.baseline.deployer_sa }
output "media_bucket" { value = module.baseline.media_bucket }
