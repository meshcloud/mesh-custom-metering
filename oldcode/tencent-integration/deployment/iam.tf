resource "google_service_account" "service_account_inventory" {
  account_id   = "${var.ressource_prefix}-${var.service_account_inventory.name}"
  display_name = "${var.ressource_prefix}-${var.service_account_inventory.name}"
  description  = var.service_account_inventory.description
}

resource "google_service_account" "service_account_sync_new" {
  account_id   = "${var.ressource_prefix}-${var.service_account_sync_new.name}"
  display_name = "${var.ressource_prefix}-${var.service_account_sync_new.name}"
  description  = var.service_account_sync_new.description
}

resource "google_service_account" "service_account_sync_del" {
  account_id   = "${var.ressource_prefix}-${var.service_account_sync_del.name}"
  display_name = "${var.ressource_prefix}-${var.service_account_sync_del.name}"
  description  = var.service_account_sync_del.description
}

resource "google_service_account" "service_account_cost" {
  account_id   = "${var.ressource_prefix}-${var.service_account_cost.name}"
  display_name = "${var.ressource_prefix}-${var.service_account_cost.name}"
  description  = var.service_account_cost.description
}

resource "google_service_account" "service_account_scheduler" {
  account_id   = "${var.ressource_prefix}-${var.service_account_scheduler.name}"
  display_name = "${var.ressource_prefix}-${var.service_account_scheduler.name}"
  description  = var.service_account_scheduler.description
}

# Grant permissions to read tencent api secret
resource "google_secret_manager_secret_iam_binding" "binding1" {
  project   = var.gcp_project_id
  secret_id = google_secret_manager_secret.tct_secret_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  members = [
    "serviceAccount:${google_service_account.service_account_inventory.email}",
    "serviceAccount:${google_service_account.service_account_cost.email}"
  ]
}

# Grant permissions to read meshstack api secret
resource "google_secret_manager_secret_iam_binding" "binding2" {
  project   = var.gcp_project_id
  secret_id = google_secret_manager_secret.meshstack_api_secret.secret_id
  role      = "roles/secretmanager.secretAccessor"
  members = [
    "serviceAccount:${google_service_account.service_account_inventory.email}",
    "serviceAccount:${google_service_account.service_account_sync_new.email}",
    "serviceAccount:${google_service_account.service_account_cost.email}"
  ]
}

# Grant permissions to read mail secret
resource "google_secret_manager_secret_iam_binding" "binding3" {
  project   = var.gcp_project_id
  secret_id = google_secret_manager_secret.meshstack_mail_secret.secret_id
  role      = "roles/secretmanager.secretAccessor"
  members = [
    "serviceAccount:${google_service_account.service_account_sync_del.email}"
  ]
}

# Grant permissions to publish inventory to pubsub topics
resource "google_pubsub_topic_iam_binding" "binding4" {
  project = var.gcp_project_id
  for_each = toset ([google_pubsub_topic.tenants_topic.name, google_pubsub_topic.inventory_topic.name])
  topic   = each.value
  role    = "roles/pubsub.publisher"
  members = [
    "serviceAccount:${google_service_account.service_account_inventory.email}"
  ]
}