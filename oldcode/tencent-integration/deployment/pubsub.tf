resource "google_pubsub_topic" "inventory_topic" {
  name = "${var.ressource_prefix}-${var.pubsub_topic_inventory.name}"
}

resource "google_pubsub_topic" "tenants_topic" {
  name = "${var.ressource_prefix}-${var.pubsub_topic_tenants.name}"
}