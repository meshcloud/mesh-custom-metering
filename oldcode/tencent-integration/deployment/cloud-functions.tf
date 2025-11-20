resource "google_cloudfunctions2_function" "inventory_function" {
  name        = "${var.ressource_prefix}-${var.cloud_function_inventory.name}"
  location    = var.gcp_region
  project     = var.gcp_project_id
  description = var.cloud_function_inventory.description

  build_config {
    runtime     = var.cloud_function_inventory.runtime
    entry_point = var.cloud_function_inventory.entry_point
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.inventory_source_files.name
      }
    }
  }

  service_config {
    ingress_settings = "ALLOW_INTERNAL_ONLY"
    max_instance_count    = var.cloud_function_inventory.max_instance_count
    min_instance_count    = var.cloud_function_inventory.min_instance_count
    available_memory      = var.cloud_function_inventory.available_memory
    timeout_seconds       = 60
    service_account_email = google_service_account.service_account_inventory.email
    environment_variables = {
        INVENTORY_TOPIC : google_pubsub_topic.inventory_topic.name,
        TENANTS_TOPIC : google_pubsub_topic.tenants_topic.name,

        GCP_PROJECT_ID: var.gcp_project_id,
        
        PLATFORM_ID: var.platform_id,
        WORKSPACE_ID: var.workspace_id,

        MESH_API_HOST: var.mesh_api_host,
        MESH_API_USER : var.mesh_api_user,
        GCP_SECRET_ID_MESHSECRET : google_secret_manager_secret.meshstack_api_secret.secret_id, # the meshscloud api secret is stored in the Secret Manager

        TCT_SECRET_ID : var.tencent_secret_id,
        GCP_SECRET_ID_TCTSECRET : google_secret_manager_secret.tct_secret_key.secret_id, # the tencent secret key is stored in the Secret Manager
      }
  }
}

resource "google_cloudfunctions2_function" "sync_function_new" {
  name        = "${var.ressource_prefix}-${var.cloud_function_sync_new.name}"
  location    = var.gcp_region
  project     = var.gcp_project_id
  description = var.cloud_function_sync_new.description

  build_config {
    runtime     = var.cloud_function_sync_new.runtime
    entry_point = var.cloud_function_sync_new.entry_point
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.sync_new_source_file.name
      }
    }
  }

  service_config {
    max_instance_count    = var.cloud_function_sync_new.max_instance_count
    min_instance_count    = var.cloud_function_sync_new.min_instance_count
    available_memory      = var.cloud_function_sync_new.available_memory
    timeout_seconds       = 60
    service_account_email = google_service_account.service_account_sync_new.email
    environment_variables = {
        GCP_PROJECT_ID: var.gcp_project_id,

        PLATFORM_ID: var.platform_id,
        WORKSPACE_ID: var.workspace_id,
        PAYMENT_ID: var.payment_id

        MESH_API_HOST: var.mesh_api_host,
        MESH_API_USER : var.mesh_api_user,
        GCP_SECRET_ID_MESHSECRET : google_secret_manager_secret.meshstack_api_secret.secret_id, # the meshscloud api secret is stored in the Secret Manager
    }
  }

  event_trigger {
    trigger_region = var.gcp_region
    pubsub_topic   = google_pubsub_topic.inventory_topic.id
    event_type     = "google.cloud.pubsub.topic.v1.messagePublished"
    retry_policy   = "RETRY_POLICY_DO_NOT_RETRY"
  }
}


resource "google_cloudfunctions2_function" "sync_function_del" {
  name        = "${var.ressource_prefix}-${var.cloud_function_sync_del.name}"
  location    = var.gcp_region
  project     = var.gcp_project_id
  description = var.cloud_function_sync_del.description

  build_config {
    runtime     = var.cloud_function_sync_del.runtime
    entry_point = var.cloud_function_sync_del.entry_point
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.sync_del_source_file.name
      }
    }
  }

  service_config {
    max_instance_count    = var.cloud_function_sync_del.max_instance_count
    min_instance_count    = var.cloud_function_sync_del.min_instance_count
    available_memory      = var.cloud_function_sync_del.available_memory
    timeout_seconds       = 60
    service_account_email = google_service_account.service_account_sync_del.email
    environment_variables = {
        GCP_PROJECT_ID: var.gcp_project_id,
        WORKSPACE_ID: var.workspace_id,
        SENDER_MAIL: var.sender_mail,
        RECIPIENT_MAIL: var.recipient_mail,
        GCP_SECRET_ID_MESHSECRET : google_secret_manager_secret.meshstack_mail_secret.secret_id, # the meshscloud mail secret is stored in the Secret Manager
    }
  }

  event_trigger {
    trigger_region = var.gcp_region
    pubsub_topic   = google_pubsub_topic.inventory_topic.id
    event_type     = "google.cloud.pubsub.topic.v1.messagePublished"
    retry_policy   = "RETRY_POLICY_DO_NOT_RETRY"
  }
}


resource "google_cloudfunctions2_function" "cost_function" {
  name        = "${var.ressource_prefix}-${var.cloud_function_cloud_cost.name}"
  location    = var.gcp_region
  project     = var.gcp_project_id
  description = var.cloud_function_cloud_cost.description

  build_config {
    runtime     = var.cloud_function_cloud_cost.runtime
    entry_point = var.cloud_function_cloud_cost.entry_point
    source {
      storage_source {
        bucket = google_storage_bucket.bucket.name
        object = google_storage_bucket_object.cost_source_file.name
      }
    }
  }

  service_config {
    max_instance_count    = var.cloud_function_cloud_cost.max_instance_count
    min_instance_count    = var.cloud_function_cloud_cost.min_instance_count
    available_memory      = var.cloud_function_cloud_cost.available_memory
    timeout_seconds       = 300
    service_account_email = google_service_account.service_account_cost.email
    environment_variables = {
        GCP_PROJECT_ID: var.gcp_project_id,

        PLATFORM_ID: var.platform_id,
        WORKSPACE_ID: var.workspace_id,
        PAYMENT_ID: var.payment_id

        MESH_COST_API_HOST: var.mesh_cost_api_host,
        MESH_API_USER : var.mesh_api_user,
        GCP_SECRET_ID_MESHSECRET : google_secret_manager_secret.meshstack_api_secret.secret_id, # the meshscloud api secret is stored in the Secret Manager

        TCT_SECRET_ID : var.tencent_secret_id,
        GCP_SECRET_ID_TCTSECRET : google_secret_manager_secret.tct_secret_key.secret_id, # the tencent secret key is stored in the Secret Manager 
    }
  }

  event_trigger {
    trigger_region = var.gcp_region
    pubsub_topic   = google_pubsub_topic.tenants_topic.id
    event_type     = "google.cloud.pubsub.topic.v1.messagePublished"
    retry_policy   = "RETRY_POLICY_DO_NOT_RETRY"
  }
}