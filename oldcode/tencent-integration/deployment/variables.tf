variable "gcp_region" {
  type    = string
  default = "europe-west3"
}

variable "ressource_prefix" {
  type    = string
  default = "mesh-tct"
}

variable "pubsub_topic_inventory" {
  type = map(string)
  default = {
    name : "inventory-topic"
  }
}

variable "pubsub_topic_tenants" {
  type = map(string)
  default = {
    name : "tenants-topic"
  }
}

variable "scheduler_cronjob" {
  type = map(string)
  default = {
    name : "inventory-cron-job",
    schedule : "00 10 * * *"
    description : "Schedule the synchronization from Tencent cloud meshStack"
  }
}

variable "service_account_inventory" {
  type = map(string)
  default = {
    name : "sacc-inventory"
    description : "Service account for Cloud function creating inventory of tenants and accounts"
  }
}

variable "service_account_sync_new" {
  type = map(string)
  default = {
    name        = "sacc-sync-new"
    description = "Service account for Cloud function managing new Tencent accounts"
  }
}

variable "service_account_sync_del" {
  type = map(string)
  default = {
    name        = "sacc-sync-del"
    description = "Service account for Cloud function managing deleted Tencent accounts"
  }
}

variable "service_account_cost" {
  type = map(string)
  default = {
    name        = "sacc-cost"
    description = "Service account for Cloud function collecting Tencent costs and updating usage reports"
  }
}

variable "service_account_scheduler" {
  type = map(string)
  default = {
    name        = "sacc-sched"
    description = "Service account for Scheduler to invoke the inventory function"
  }
}

variable "gcp_project_id" {
  type = string
}

variable "platform_id" {
  type = string
}

variable "workspace_id" {
  type = string
}

variable "payment_id" {
  type = string
}

variable "mesh_api_host" {
  type = string
}

variable "mesh_cost_api_host" {
  type = string
}

variable "mesh_api_user" {
  type = string
}

variable "tencent_secret_id" {
  type = string
}

variable "sender_mail" {
  description = "The sender mail address"
  type = string
}

variable "recipient_mail" {
  description = "A list of coma separated email addresses for notifications."
  type = string
}

variable "cloud_function_inventory" {
  type = map(any)
  default = {
    name               = "createInventory"
    description        = "The cloud function creates a list of existing meshsStack tenants and Tencent accounts"
    max_instance_count = 1
    min_instance_count = 0
    available_memory   = "256M"
    runtime            = "python312"
    entry_point        = "main"
    source_zip         = "createInventory.zip"
    source_folder      = "../python/createInventory"
  }
}

variable "cloud_function_sync_new" {
  type = map(any)
  default = {
    name               = "syncNewMeshStackTenants"
    description        = "The cloud function manages new Tencent accounts"
    max_instance_count = 1
    min_instance_count = 0
    available_memory   = "256M"
    runtime            = "python312"
    entry_point        = "main"
    source_zip         = "syncNewMeshStackTenants.zip"
    source_folder      = "../python/syncNewMeshStackTenants"
  }
}

variable "cloud_function_sync_del" {
  type = map(any)
  default = {
    name               = "syncDeletedMeshStackTenants"
    description        = "The cloud function manages deleted Tencent accounts"
    max_instance_count = 1
    min_instance_count = 0
    available_memory   = "256M"
    runtime            = "python312"
    entry_point        = "main"
    source_zip         = "syncDeletedMeshStackTenants.zip"
    source_folder      = "../python/syncDeletedMeshStackTenants"
  }
}

variable "cloud_function_cloud_cost" {
  type = map(any)
  default = {
    name               = "collectCost"
    description        = "The cloud function retrieves the cost for Tencent service and import in meshStack as usage reports"
    max_instance_count = 1
    min_instance_count = 0
    available_memory   = "512M"
    runtime            = "python312"
    entry_point        = "main"
    source_zip         = "collectCost.zip"
    source_folder      = "../python/collectCost"
  }
}