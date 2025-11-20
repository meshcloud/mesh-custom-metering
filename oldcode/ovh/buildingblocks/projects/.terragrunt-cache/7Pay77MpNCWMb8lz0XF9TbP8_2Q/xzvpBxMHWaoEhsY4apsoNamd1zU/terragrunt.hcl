terraform {
  source = "./"
}

inputs = {
  ovh_account_id = "rj1642195-ovh"
  workspace_id   = "project"
  project_id     = "containerdays-prod2025"
  users = [
    {
      meshIdentifier = "identifier1"
      username       = "fnowarre@meshcloud.io"
      firstName      = "florian"
      lastName       = "nowarre"
      email          = "fnowarre@meshcloud.io"
      euid           = "fnowarre@meshcloud.io"
      roles          = ["admin"]
    },
    {
      meshIdentifier = "identifier2"
      username       = "ckraus@meshcloud.io"
      firstName      = "christina"
      lastName       = "kraus"
      email          = "ckraus@meshcloud.io"
      euid           = "ckraus@meshcloud.io"
      roles          = ["user"]
    }
  ]
}
