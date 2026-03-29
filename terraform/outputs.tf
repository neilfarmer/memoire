output "api_url" {
  description = "Base URL for all API endpoints (custom domain when configured, raw invoke URL otherwise)"
  value       = local.api_url
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = aws_cognito_user_pool.main.id
}

output "cognito_client_id" {
  description = "Cognito App Client ID (used in auth requests)"
  value       = aws_cognito_user_pool_client.main.id
}


output "tasks_table_name" {
  description = "DynamoDB tasks table name"
  value       = aws_dynamodb_table.tasks.name
}

output "frontend_url" {
  description = "Frontend URL (custom domain when configured, CloudFront domain otherwise)"
  value       = local.custom_domain_enabled ? "https://${local.frontend_domain}" : "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "frontend_domain" {
  description = "Custom frontend domain (empty when domain_provider = none)"
  value       = local.frontend_domain
}

output "api_domain" {
  description = "Custom API domain (empty when domain_provider = none)"
  value       = local.api_domain
}

output "frontend_bucket" {
  description = "S3 bucket name for the frontend"
  value       = aws_s3_bucket.frontend.id
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID (needed for cache invalidation)"
  value       = aws_cloudfront_distribution.frontend.id
}
