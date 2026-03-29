terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.38.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }

  # Uncomment and configure to use remote state:
  # backend "s3" {
  #   bucket = "your-terraform-state-bucket"
  #   key    = "hearth/terraform.tfstate"
  #   region = "us-east-1"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# Always declared; only used when domain_provider = "cloudflare".
# When unused, api_token defaults to "unused" and no resources are created.
provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"

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
