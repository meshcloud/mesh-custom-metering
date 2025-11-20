resource "google_cloud_scheduler_job" "job" {
  name        = "${var.ressource_prefix}-${var.scheduler_cronjob.name}"
  description = var.scheduler_cronjob.description
  schedule    = var.scheduler_cronjob.schedule

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = google_cloudfunctions2_function.inventory_function.url
    body        = base64encode("{\"msg\":\"hello\"}")
    headers = {
      "Content-Type" = "application/json"
    }
    oidc_token {
      service_account_email = google_service_account.service_account_scheduler.email
    }
  }
}