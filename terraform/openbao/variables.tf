variable "openbao_address" {
  type    = string
  default = "https://openbao.int.andreybondarenko.com"
}

variable "openbao_ca_cert_file" {
  type    = string
  default = null
}

variable "openbao_tls_server_name" {
  type    = string
  default = null
}

variable "kubernetes_issuer" {
  type    = string
  default = "https://api.k8s.my.lan:6443"
}

variable "oidc_client_secret" {
  type      = string
  sensitive = true
  ephemeral = true
}
