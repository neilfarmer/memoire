terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.38.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "2.7.1"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "4.52.7"
    }
    random = {
      source  = "hashicorp/random"
      version = "3.8.1"
    }
  }

  # Uncomment and configure to use remote state:
  # backend "s3" {
  #   bucket = "your-terraform-state-bucket"
  #   key    = "hearth/terraform.tfstate"
  #   region = "us-east-1"
  # }
}


locals {
  name_prefix = var.name_prefix != "" ? var.name_prefix : "${var.project_name}-${var.environment}"

  # ── Custom domain ─────────────────────────────────────────────────────────────
  # Set domain_provider = "cloudflare" or "aws" and provide root_domain to enable.
  # When enabled, the frontend is at {name_prefix}.{root_domain} and the API is at
  # api.{name_prefix}.{root_domain}.

  custom_domain_enabled = var.domain_provider != "none" && var.root_domain != ""
  cloudflare_enabled    = var.domain_provider == "cloudflare" && local.custom_domain_enabled
  route53_enabled       = var.domain_provider == "aws" && local.custom_domain_enabled

  frontend_domain = var.root_domain != "" ? "${local.name_prefix}.${var.root_domain}" : ""
  api_domain      = var.root_domain != "" ? "api.${local.name_prefix}.${var.root_domain}" : ""

  # api_url used in config.js — custom domain when enabled, raw invoke URL otherwise.
  api_url = local.custom_domain_enabled ? "https://${local.api_domain}" : trimprefix(aws_apigatewayv2_stage.default.invoke_url, "/")

  # frontend_origin used for CORS allow_origins and cookie validation.
  # Must be the exact origin (scheme + host, no trailing slash) of the frontend.
  frontend_origin = local.custom_domain_enabled ? "https://${local.frontend_domain}" : "https://${aws_cloudfront_distribution.frontend.domain_name}"

  # ── Auth ──────────────────────────────────────────────────────────────────────
  # When auth_provider = cognito, derive JWT config from managed Cognito resources.
  # When auth_provider = oidc, use the caller-supplied auth_oidc_* variables.
  auth_jwt_issuer_url = var.auth_provider == "cognito" ? "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.main[0].id}" : var.auth_oidc_issuer_url
  auth_jwt_client_id  = var.auth_provider == "cognito" ? aws_cognito_user_pool_client.main[0].id : var.auth_oidc_client_id
  auth_hosted_ui_url  = var.auth_provider == "cognito" ? "https://${aws_cognito_user_pool_domain.main[0].domain}.auth.${var.aws_region}.amazoncognito.com" : var.auth_oidc_hosted_ui_url

}

# ── Lambda layer (shared utilities) ──────────────────────────────────────────

data "archive_file" "lambda_layer" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/layer"
  output_path = "${path.module}/../build/layer.zip"
}

# ── Per-feature Lambda zips ───────────────────────────────────────────────────

data "archive_file" "lambda_tasks" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/tasks"
  output_path = "${path.module}/../build/tasks.zip"
}

data "archive_file" "lambda_settings" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/settings"
  output_path = "${path.module}/../build/settings.zip"
}

data "archive_file" "lambda_watcher" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/watcher"
  output_path = "${path.module}/../build/watcher.zip"
}

data "archive_file" "lambda_habits" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/habits"
  output_path = "${path.module}/../build/habits.zip"
}

data "archive_file" "lambda_journal" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/journal"
  output_path = "${path.module}/../build/journal.zip"
}

data "archive_file" "lambda_notes" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/notes"
  output_path = "${path.module}/../build/notes.zip"
}

data "archive_file" "lambda_home" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/home"
  output_path = "${path.module}/../build/home.zip"
}

data "archive_file" "lambda_export" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/export"
  output_path = "${path.module}/../build/export.zip"
}

data "archive_file" "lambda_health" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/health"
  output_path = "${path.module}/../build/health.zip"
}

data "archive_file" "lambda_nutrition" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/nutrition"
  output_path = "${path.module}/../build/nutrition.zip"
}

data "archive_file" "lambda_goals" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/goals"
  output_path = "${path.module}/../build/goals.zip"
}

data "archive_file" "lambda_feeds" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/feeds"
  output_path = "${path.module}/../build/feeds.zip"
}

data "archive_file" "lambda_favorites" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/favorites"
  output_path = "${path.module}/../build/favorites.zip"
}

data "archive_file" "lambda_authorizer" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/authorizer"
  output_path = "${path.module}/../build/authorizer.zip"
}

data "archive_file" "lambda_tokens" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/tokens"
  output_path = "${path.module}/../build/tokens.zip"
}

data "archive_file" "lambda_assistant" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/assistant"
  output_path = "${path.module}/../build/assistant.zip"
}

data "archive_file" "lambda_diagrams" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/diagrams"
  output_path = "${path.module}/../build/diagrams.zip"
}

data "archive_file" "lambda_finances" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/finances"
  output_path = "${path.module}/../build/finances.zip"
}

data "archive_file" "lambda_bookmarks" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/bookmarks"
  output_path = "${path.module}/../build/bookmarks.zip"
}

data "archive_file" "lambda_links" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/links"
  output_path = "${path.module}/../build/links.zip"
}
