resource "aws_cognito_user_pool" "main" {
  count = var.auth_provider == "cognito" ? 1 : 0
  name  = "${local.name_prefix}-users"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  password_policy {
    minimum_length                   = 8
    require_uppercase                = true
    require_lowercase                = true
    require_numbers                  = true
    require_symbols                  = false
    temporary_password_validity_days = 7
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  schema {
    name                = "email"
    attribute_data_type = "String"
    required            = true
    mutable             = true

    string_attribute_constraints {
      min_length = 5
      max_length = 254
    }
  }
}

resource "aws_cognito_user_pool_client" "main" {
  count        = var.auth_provider == "cognito" ? 1 : 0
  name         = "${local.name_prefix}-client"
  user_pool_id = aws_cognito_user_pool.main[0].id

  # No client secret — suitable for SPAs and CLI tools
  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_SRP_AUTH",
  ]

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }

  access_token_validity  = 4
  id_token_validity      = 4
  refresh_token_validity = 30

  supported_identity_providers = ["COGNITO"]

  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  allowed_oauth_flows_user_pool_client = true

  # Must match window.location.origin + "/" used in the PKCE flow and logout redirect.
  callback_urls = ["${local.frontend_origin}/"]
  logout_urls   = ["${local.frontend_origin}/"]
}

resource "aws_cognito_user_pool_domain" "main" {
  count        = var.auth_provider == "cognito" ? 1 : 0
  domain       = "${local.name_prefix}-auth"
  user_pool_id = aws_cognito_user_pool.main[0].id
}

resource "aws_cognito_user" "default" {
  count        = var.auth_provider == "cognito" && var.default_user_email != "" ? 1 : 0
  user_pool_id = aws_cognito_user_pool.main[0].id
  username     = var.default_user_email
  password     = var.default_user_password

  attributes = {
    email          = var.default_user_email
    email_verified = "true"
  }

  message_action = "SUPPRESS"

  lifecycle {
    ignore_changes = [password]
  }
}
