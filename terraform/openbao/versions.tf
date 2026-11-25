terraform {
  backend "local" {}
  required_version = ">= 1.11.0"
  required_providers {
    vault = {
      source  = "hashicorp/vault"
      version = "5.14.0"
    }
  }
}

provider "vault" {
  address          = var.openbao_address
  skip_child_token = true
  ca_cert_file     = var.openbao_ca_cert_file
  tls_server_name  = var.openbao_tls_server_name
}
