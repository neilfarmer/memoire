variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}


variable "project_name" {
  description = "Project name used as a prefix for all resources"
  type        = string
  default     = "memoire"
}

variable "name_prefix" {
  description = "Override the computed name prefix ({project_name}-{environment}). Useful when you want a clean prod name like 'memoire' instead of 'memoire-prod'."
  type        = string
  default     = ""
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}


variable "domain_provider" {
  description = "DNS provider for custom domain. cloudflare uses the Cloudflare provider; aws uses Route 53; none disables custom domains."
  type        = string
  default     = "none"

  validation {
    condition     = contains(["cloudflare", "aws", "none"], var.domain_provider)
    error_message = "domain_provider must be cloudflare, aws, or none."
  }
}

variable "root_domain" {
  description = "Root domain name (e.g. example.com). Required when domain_provider is not none. The frontend will be reachable at {name_prefix}.{root_domain} and the API at api.{name_prefix}.{root_domain}."
  type        = string
  default     = ""
}


variable "route53_zone_id" {
  description = "Route 53 hosted zone ID for root_domain. Required when domain_provider = aws."
  type        = string
  default     = ""
}

variable "auth_provider" {
  description = "Authentication provider. cognito deploys and manages AWS Cognito. oidc uses an external OIDC provider — supply auth_oidc_issuer_url and auth_oidc_client_id."
  type        = string
  default     = "cognito"

  validation {
    condition     = contains(["cognito", "oidc"], var.auth_provider)
    error_message = "auth_provider must be cognito or oidc."
  }
}

variable "auth_oidc_issuer_url" {
  description = "OIDC issuer URL. Required when auth_provider = oidc (e.g. https://accounts.google.com)."
  type        = string
  default     = ""
}

variable "auth_oidc_client_id" {
  description = "JWT audience (client ID) from your OIDC provider. Required when auth_provider = oidc."
  type        = string
  default     = ""
}

variable "auth_oidc_hosted_ui_url" {
  description = "Base URL of the OAuth hosted UI (e.g. https://example.auth.us-east-1.amazoncognito.com). Required when auth_provider = oidc."
  type        = string
  default     = ""
}

variable "default_user_email" {
  description = "Email address for the initial user account created on first deploy. Leave empty to skip."
  type        = string
  default     = ""
}

variable "default_user_password" {
  description = "Password for the initial user account. Must meet the Cognito password policy (8+ chars, upper, lower, number)."
  type        = string
  default     = ""
  sensitive   = true
}

variable "alert_emails" {
  description = "Email addresses that receive budget alerts and ops notifications."
  type        = list(string)
  default     = []
}

variable "budget_thresholds_usd" {
  description = "Monthly spend thresholds in USD. An alert fires when actual spend exceeds each value."
  type        = list(number)
  default     = [10, 20, 30]
}

variable "lambda_timeout" {
  description = "Default Lambda function timeout in seconds."
  type        = number
  default     = 10
}

variable "lambda_memory_mb" {
  description = "Default Lambda function memory in MB."
  type        = number
  default     = 128
}

variable "lambda_runtime" {
  description = "Lambda runtime identifier."
  type        = string
  default     = "python3.12"
}

variable "lambda_max_concurrency" {
  description = "Reserved concurrent executions per Lambda. -1 means unreserved (uses account-wide pool)."
  type        = number
  default     = 5
}

variable "log_retention_days" {
  description = "CloudWatch log retention period in days for all Lambda log groups."
  type        = number
  default     = 14
}

variable "note_attachment_ia_days" {
  description = "Days before note attachments transition to S3 Infrequent Access storage."
  type        = number
  default     = 90
}

variable "note_attachment_glacier_days" {
  description = "Days before note attachments transition to S3 Glacier Instant Retrieval storage."
  type        = number
  default     = 365
}

variable "admin_user_ids" {
  description = "Comma-separated list of Cognito sub claims allowed to access /admin/stats. Leave empty to disable the endpoint for all users."
  type        = string
  default     = ""
}

variable "assistant_model_id" {
  description = "Bedrock model ID for the AI assistant. Use a cross-region inference profile ID (e.g. us.amazon.nova-lite-v1:0)."
  type        = string
  default     = "us.amazon.nova-lite-v1:0"
}

variable "assistant_system_prompt" {
  description = "System prompt for the AI assistant. Overrides the default prompt baked into the Lambda code."
  type        = string
  default     = ""
}

