# Single HTTP API shared across all features.
# Each feature Lambda registers its own routes in its own .tf file.

resource "aws_apigatewayv2_api" "main" {
  name          = "${local.name_prefix}-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_headers    = ["Content-Type"]
    allow_methods    = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_origins    = [local.frontend_origin]
    allow_credentials = true
    max_age          = 300
  }
}

resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id           = aws_apigatewayv2_api.main.id
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]
  name             = "jwt"

  jwt_configuration {
    audience = [local.auth_jwt_client_id]
    issuer   = local.auth_jwt_issuer_url
  }
}

# Lambda authorizer — validates both Cognito JWTs and Personal Access Tokens (PATs).
# All user-facing routes use this authorizer instead of the built-in JWT authorizer.
# Token management routes (/tokens/*) keep the JWT authorizer so that PATs cannot
# be used to create or revoke other PATs.

resource "aws_apigatewayv2_authorizer" "lambda" {
  api_id                            = aws_apigatewayv2_api.main.id
  authorizer_type                   = "REQUEST"
  authorizer_uri                    = aws_lambda_function.authorizer.invoke_arn
  # No identity_sources — the Lambda reads from Cookie (browser JWTs) or
  # Authorization header (PATs) itself, so API Gateway must always invoke it.
  name                              = "lambda-authorizer"
  authorizer_payload_format_version = "2.0"
  enable_simple_responses           = true
  authorizer_result_ttl_in_seconds  = 0  # No caching — revoked PATs must be rejected immediately
}

# Access logging is intentionally not configured: each Lambda logs its own
# requests via CloudWatch, and Lambda authorizer logs capture auth events
# with enough detail for incident response. API Gateway access logs would
# duplicate this at additional CloudWatch ingestion cost.
resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.main.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_burst_limit = 100
    throttling_rate_limit  = 50
  }
}
