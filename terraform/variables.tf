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

variable "cloudflare_api_token" {
  description = "Cloudflare API token. Required when domain_provider = cloudflare."
  type        = string
  default     = "unused"
  sensitive   = true
}

variable "route53_zone_id" {
  description = "Route 53 hosted zone ID for root_domain. Required when domain_provider = aws."
  type        = string
  default     = ""
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
