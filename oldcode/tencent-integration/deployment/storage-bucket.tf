# Create bucket where the sources code for cloud functions will be imported
resource "google_storage_bucket" "bucket" {
  name                        = "${var.gcp_project_id}-gcf-source" # Every bucket name must be globally unique
  location                    = var.gcp_region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
}


# Archive and bucket objects for inventory cloud function
data "archive_file" "inventory_source_files_zip" {
  type        = "zip"
  output_path = "/tmp/${var.cloud_function_inventory.source_zip}"
  source_dir  = var.cloud_function_inventory.source_folder
}

# Create a hash of the zip file for detecting changes
resource "random_id" "source_hash_inventory" {
  keepers = {
    # This value changes when any of the files in the function directory change
    source_hash = data.archive_file.inventory_source_files_zip.output_base64sha256
  }
  byte_length = 8
}

resource "google_storage_bucket_object" "inventory_source_files" {
  name   = "function-${var.cloud_function_inventory.name}-${random_id.source_hash_inventory.hex}.zip"
  bucket = google_storage_bucket.bucket.name
  source = data.archive_file.inventory_source_files_zip.output_path
}


# Archive and bucket objects for synchronization cloud function
data "archive_file" "sync_new_source_file_zip" {
  type        = "zip"
  output_path = "/tmp/${var.cloud_function_sync_new.source_zip}"
  source_dir  = var.cloud_function_sync_new.source_folder
}

# Create a hash of the zip file for detecting changes
resource "random_id" "source_hash_sync_new" {
  keepers = {
    # This value changes when any of the files in the function directory change
    source_hash = data.archive_file.sync_new_source_file_zip.output_base64sha256
  }
  byte_length = 8
}

resource "google_storage_bucket_object" "sync_new_source_file" {
  name   = "function-${var.cloud_function_sync_new.name}-${random_id.source_hash_sync_new.hex}.zip"
  bucket = google_storage_bucket.bucket.name
  source = data.archive_file.sync_new_source_file_zip.output_path
}

# Archive and bucket objects for synchronization cloud function
data "archive_file" "sync_del_source_file_zip" {
  type        = "zip"
  output_path = "/tmp/${var.cloud_function_sync_del.source_zip}"
  source_dir  = var.cloud_function_sync_del.source_folder
}

# Create a hash of the zip file for detecting changes
resource "random_id" "source_hash_sync_del" {
  keepers = {
    # This value changes when any of the files in the function directory change
    source_hash = data.archive_file.sync_del_source_file_zip.output_base64sha256
  }
  byte_length = 8
}

resource "google_storage_bucket_object" "sync_del_source_file" {
  name   = "function-${var.cloud_function_sync_del.name}-${random_id.source_hash_sync_del.hex}.zip"
  bucket = google_storage_bucket.bucket.name
  source = data.archive_file.sync_del_source_file_zip.output_path
}

# Archive and bucket objects for cost export cloud function
data "archive_file" "cost_source_file_zip" {
  type        = "zip"
  output_path = "/tmp/${var.cloud_function_cloud_cost.source_zip}"
  source_dir  = var.cloud_function_cloud_cost.source_folder
}

# Create a hash of the zip file for detecting changes
resource "random_id" "source_hash_cost" {
  keepers = {
    # This value changes when any of the files in the function directory change
    source_hash = data.archive_file.cost_source_file_zip.output_base64sha256
  }
  byte_length = 8
}

resource "google_storage_bucket_object" "cost_source_file" {
  name   = "function-${var.cloud_function_cloud_cost.name}-${random_id.source_hash_cost.hex}.zip"
  bucket = google_storage_bucket.bucket.name
  source = data.archive_file.cost_source_file_zip.output_path
}