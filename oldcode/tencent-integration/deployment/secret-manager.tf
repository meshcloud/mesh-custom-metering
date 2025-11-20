resource "google_secret_manager_secret" "tct_secret_key" {
  secret_id = "${var.ressource_prefix}-tctApiCreds"

  replication {
    user_managed {
      replicas {
        location = var.gcp_region
      }
    }
  }
}

resource "google_secret_manager_secret" "meshstack_api_secret" {
  secret_id = "${var.ressource_prefix}-meshApiCreds"

  replication {
    user_managed {
      replicas {
        location = var.gcp_region
      }
    }
  }
}

resource "google_secret_manager_secret" "meshstack_mail_secret" {
  secret_id = "${var.ressource_prefix}-meshMailCreds"

  replication {
    user_managed {
      replicas {
        location = var.gcp_region
      }
    }
  }
}