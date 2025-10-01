/**
 * GitHub Stats Collector - Terraform Configuration
 * 
 * This Terraform configuration deploys the GitHub Stats Collector
 * as a Cloud Function with Cloud Scheduler for hourly execution.
 */

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Variables
variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "us-central1"
}

variable "github_token" {
  description = "GitHub Personal Access Token"
  type        = string
  sensitive   = true
}

variable "github_org" {
  description = "GitHub Organization Name"
  type        = string
  default     = "askscio"
}

variable "bigquery_dataset_id" {
  description = "BigQuery Dataset ID"
  type        = string
  default     = "github_stats"
}

variable "gcs_bucket_name" {
  description = "GCS Bucket Name for data persistence"
  type        = string
  default     = "github-stats-data"
}

variable "function_name" {
  description = "Cloud Function Name"
  type        = string
  default     = "github-stats-collector"
}

variable "schedule" {
  description = "Cron schedule for Cloud Scheduler (default: every hour)"
  type        = string
  default     = "0 * * * *"
}

variable "time_zone" {
  description = "Time zone for Cloud Scheduler"
  type        = string
  default     = "America/Los_Angeles"
}

# Enable required APIs
resource "google_project_service" "cloudfunctions" {
  service            = "cloudfunctions.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudscheduler" {
  service            = "cloudscheduler.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloudbuild" {
  service            = "cloudbuild.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "bigquery" {
  service            = "bigquery.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "storage" {
  service            = "storage-api.googleapis.com"
  disable_on_destroy = false
}

# GCS bucket for Cloud Function source code
resource "google_storage_bucket" "function_source" {
  name     = "${var.project_id}-function-source"
  location = var.region
  
  uniform_bucket_level_access = true
  
  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }
}

# GCS bucket for GitHub data persistence
resource "google_storage_bucket" "github_data" {
  name     = var.gcs_bucket_name
  location = var.region
  
  uniform_bucket_level_access = true
  
  lifecycle_rule {
    condition {
      age = 365  # Keep data for 1 year
    }
    action {
      type          = "SetStorageClass"
      storage_class = "ARCHIVE"
    }
  }
}

# Create a zip file of the function source
data "archive_file" "function_zip" {
  type        = "zip"
  output_path = "${path.module}/function.zip"
  
  source_dir = "${path.module}/../../"
  
  excludes = [
    ".git",
    ".gitignore",
    "deployment",
    "*.md",
    "*.log",
    ".env",
    ".env.example",
    "__pycache__",
    "*.pyc",
    ".venv",
    "venv",
    "Dockerfile",
    "docker-compose.yml"
  ]
}

# Upload function source to GCS
resource "google_storage_bucket_object" "function_source_zip" {
  name   = "github-stats-collector-${data.archive_file.function_zip.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.function_zip.output_path
}

# Service account for Cloud Function
resource "google_service_account" "function_sa" {
  account_id   = "github-stats-collector"
  display_name = "GitHub Stats Collector Service Account"
  description  = "Service account for GitHub Stats Collector Cloud Function"
}

# Grant necessary permissions to service account
resource "google_project_iam_member" "function_bigquery_admin" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.function_sa.email}"
}

resource "google_project_iam_member" "function_bigquery_job" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.function_sa.email}"
}

resource "google_storage_bucket_iam_member" "function_storage_admin" {
  bucket = google_storage_bucket.github_data.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.function_sa.email}"
}

# Cloud Function (Gen 2)
resource "google_cloudfunctions2_function" "github_stats_collector" {
  name        = var.function_name
  location    = var.region
  description = "Collects GitHub statistics hourly and publishes to BigQuery"
  
  build_config {
    runtime     = "python311"
    entry_point = "collect_github_stats"
    
    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.function_source_zip.name
      }
    }
  }
  
  service_config {
    max_instance_count = 1
    min_instance_count = 0
    available_memory   = "512Mi"
    timeout_seconds    = 540
    
    environment_variables = {
      GITHUB_TOKEN        = var.github_token
      GITHUB_ORG          = var.github_org
      BIGQUERY_PROJECT_ID = var.project_id
      BIGQUERY_DATASET_ID = var.bigquery_dataset_id
      GCS_BUCKET_NAME     = var.gcs_bucket_name
      PERSIST_TO_GCS      = "true"
    }
    
    service_account_email = google_service_account.function_sa.email
  }
  
  depends_on = [
    google_project_service.cloudfunctions,
    google_project_service.cloudbuild,
  ]
}

# Make the function publicly accessible (optional - remove if you want private)
resource "google_cloudfunctions2_function_iam_member" "invoker" {
  project        = google_cloudfunctions2_function.github_stats_collector.project
  location       = google_cloudfunctions2_function.github_stats_collector.location
  cloud_function = google_cloudfunctions2_function.github_stats_collector.name
  role           = "roles/cloudfunctions.invoker"
  member         = "allUsers"
}

# Cloud Scheduler job
resource "google_cloud_scheduler_job" "github_stats_hourly" {
  name             = "github-stats-hourly"
  description      = "Triggers GitHub stats collection every hour"
  schedule         = var.schedule
  time_zone        = var.time_zone
  attempt_deadline = "540s"
  region           = var.region
  
  retry_config {
    retry_count = 3
    min_backoff_duration = "5s"
    max_backoff_duration = "1h"
  }
  
  http_target {
    http_method = "GET"
    uri         = google_cloudfunctions2_function.github_stats_collector.service_config[0].uri
    
    oidc_token {
      service_account_email = google_service_account.function_sa.email
    }
  }
  
  depends_on = [
    google_project_service.cloudscheduler,
    google_cloudfunctions2_function.github_stats_collector,
  ]
}

# Outputs
output "function_url" {
  description = "URL of the deployed Cloud Function"
  value       = google_cloudfunctions2_function.github_stats_collector.service_config[0].uri
}

output "function_name" {
  description = "Name of the Cloud Function"
  value       = google_cloudfunctions2_function.github_stats_collector.name
}

output "scheduler_name" {
  description = "Name of the Cloud Scheduler job"
  value       = google_cloud_scheduler_job.github_stats_hourly.name
}

output "service_account_email" {
  description = "Service account email for the function"
  value       = google_service_account.function_sa.email
}

output "data_bucket" {
  description = "GCS bucket for GitHub data persistence"
  value       = google_storage_bucket.github_data.name
}
