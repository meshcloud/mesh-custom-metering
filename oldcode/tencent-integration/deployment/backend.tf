terraform {
  backend "gcs" {
    bucket  = "saas-integratio-merck-tenc-h9p-terraform-states" # Replace with your bucket name
    prefix  = "terraform/state"                 # Optional: path within the bucket
  }
}