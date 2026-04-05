# Verify key security controls are configured correctly.
# These tests catch regressions if someone removes a security setting
# that was added to satisfy a compliance check.

mock_provider "aws" {}
mock_provider "archive" {}
mock_provider "random" {}
mock_provider "cloudflare" {}

run "s3_frontend_has_sse" {
  command = plan

  assert {
    condition     = aws_s3_bucket_server_side_encryption_configuration.frontend.rule[0].apply_server_side_encryption_by_default[0].sse_algorithm == "AES256"
    error_message = "frontend bucket: SSE-S3 (AES256) must be configured"
  }
}

run "s3_frontend_blocks_public_access" {
  command = plan

  assert {
    condition     = aws_s3_bucket_public_access_block.frontend.block_public_acls == true
    error_message = "frontend bucket: block_public_acls must be true"
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.frontend.block_public_policy == true
    error_message = "frontend bucket: block_public_policy must be true"
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.frontend.ignore_public_acls == true
    error_message = "frontend bucket: ignore_public_acls must be true"
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.frontend.restrict_public_buckets == true
    error_message = "frontend bucket: restrict_public_buckets must be true"
  }
}

run "cloudfront_uses_oac_not_oai" {
  command = plan

  assert {
    condition     = aws_cloudfront_origin_access_control.frontend.signing_behavior == "always"
    error_message = "CloudFront origin: must use OAC with signing_behavior=always"
  }
  assert {
    condition     = aws_cloudfront_origin_access_control.frontend.signing_protocol == "sigv4"
    error_message = "CloudFront origin: must use sigv4 signing protocol"
  }
}

run "cloudfront_enforces_https" {
  command = plan

  assert {
    condition     = aws_cloudfront_distribution.frontend.default_cache_behavior[0].viewer_protocol_policy == "redirect-to-https"
    error_message = "CloudFront: viewer_protocol_policy must redirect HTTP to HTTPS"
  }
}

run "api_gateway_has_throttling" {
  command = plan

  assert {
    condition     = aws_apigatewayv2_stage.default.default_route_settings[0].throttling_rate_limit == 50
    error_message = "API Gateway stage: throttling_rate_limit must be set"
  }
  assert {
    condition     = aws_apigatewayv2_stage.default.default_route_settings[0].throttling_burst_limit == 100
    error_message = "API Gateway stage: throttling_burst_limit must be set"
  }
}
