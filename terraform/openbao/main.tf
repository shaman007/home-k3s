locals {
  eso_roles = jsondecode(file("${path.module}/eso-roles.json"))
}

resource "vault_mount" "kv" {
  path    = "kv"
  type    = "kv"
  options = { version = "2" }
  lifecycle {
    prevent_destroy = true
  }
}

resource "vault_auth_backend" "kubernetes" {
  type = "kubernetes"
  path = "kubernetes"
  lifecycle {
    prevent_destroy = true
  }
}

resource "vault_kubernetes_auth_backend_config" "kubernetes" {
  backend                = vault_auth_backend.kubernetes.path
  kubernetes_host        = "https://kubernetes.default.svc:443"
  issuer                 = var.kubernetes_issuer
  disable_iss_validation = false
  disable_local_ca_jwt   = false
  # The server reads its projected, automatically rotated reviewer JWT and CA.
  # No reviewer JWT is copied into configuration or Terraform state.
}

resource "vault_policy" "eso" {
  for_each = local.eso_roles
  name     = each.key
  policy = join("\n", [for path in each.value.paths :
    "path ${jsonencode("kv/data/${path}")} { capabilities = [\"read\"] }"
  ])
}

resource "vault_kubernetes_auth_backend_role" "eso" {
  for_each                         = local.eso_roles
  backend                          = vault_auth_backend.kubernetes.path
  role_name                        = each.key
  bound_service_account_names      = each.value.service_accounts
  bound_service_account_namespaces = each.value.namespaces
  audience                         = "vault"
  token_policies                   = [vault_policy.eso[each.key].name]
  token_ttl                        = 3600
  token_max_ttl                    = 86400
}

resource "vault_policy" "admins" {
  name   = "admins"
  policy = "path \"*\" { capabilities = [\"create\", \"read\", \"update\", \"patch\", \"delete\", \"list\", \"sudo\"] }"
}

resource "vault_policy" "desktop" {
  name   = "desktop-shaman007"
  policy = file("${path.module}/policies/desktop.hcl")
}

resource "vault_policy" "aiy_voice_api" {
  name   = "aiy-voice-api"
  policy = file("${path.module}/policies/aiy-voice-api.hcl")
}

resource "vault_kubernetes_auth_backend_role" "aiy_voice_api" {
  backend                          = vault_auth_backend.kubernetes.path
  role_name                        = "aiy-voice-api"
  bound_service_account_names      = ["vault-auth"]
  bound_service_account_namespaces = ["aiy-voice"]
  audience                         = "vault"
  token_policies                   = [vault_policy.aiy_voice_api.name]
  token_ttl                        = 300
  token_max_ttl                    = 300
}

resource "vault_jwt_auth_backend" "oidc" {
  type                          = "oidc"
  path                          = "oidc"
  oidc_discovery_url            = "https://sso.andreybondarenko.com/realms/master"
  oidc_client_id                = "openbao"
  oidc_client_secret_wo         = var.oidc_client_secret
  oidc_client_secret_wo_version = 1
  default_role                  = "default"
  lifecycle {
    prevent_destroy = true
  }
}

locals {
  oidc_roles = {
    desktop-shaman007 = {
      policies  = [vault_policy.desktop.name]
      ttl       = 3600
      max_ttl   = 28800
      claims    = { preferred_username = "shaman007" }
      redirects = ["http://localhost:8250/oidc/callback", "http://127.0.0.1:8250/oidc/callback"]
    }
    workstation-admin = {
      policies  = [vault_policy.admins.name]
      ttl       = 900
      max_ttl   = 3600
      claims    = { preferred_username = "shaman007" }
      redirects = ["http://localhost:8250/oidc/callback", "http://127.0.0.1:8250/oidc/callback"]
    }
    default = {
      policies = ["default"]
      ttl      = 3600
      max_ttl  = 28800
      claims   = {}
      redirects = [
        "https://openbao.int.andreybondarenko.com/oidc/oidc/callback",
        "https://openbao.int.andreybondarenko.com/ui/vault/auth/oidc/oidc/callback",
        "http://localhost:8250/oidc/callback", "http://127.0.0.1:8250/oidc/callback"
      ]
    }
  }
}

resource "vault_jwt_auth_backend_role" "oidc" {
  for_each              = local.oidc_roles
  backend               = vault_jwt_auth_backend.oidc.path
  role_name             = each.key
  role_type             = "oidc"
  user_claim            = "sub"
  groups_claim          = each.key == "default" ? "groups" : null
  oidc_scopes           = ["profile", "email"]
  bound_claims          = each.value.claims
  allowed_redirect_uris = each.value.redirects
  token_policies        = each.value.policies
  token_ttl             = each.value.ttl
  token_max_ttl         = each.value.max_ttl
}

resource "vault_identity_group" "admins" {
  name     = "keycloak-admins"
  type     = "external"
  policies = [vault_policy.admins.name]
}

resource "vault_identity_group_alias" "admins" {
  name           = "admins"
  mount_accessor = vault_jwt_auth_backend.oidc.accessor
  canonical_id   = vault_identity_group.admins.id
}
