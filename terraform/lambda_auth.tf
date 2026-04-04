# ── Auth proxy Lambda ─────────────────────────────────────────────────────────
#
# Exchanges Cognito PKCE auth codes for tokens and sets HttpOnly cookies.
# These routes are intentionally unauthenticated — the browser is not yet
# authenticated when it calls /auth/callback.

resource "aws_iam_role" "auth" {
  name               = "${local.name_prefix}-auth"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "auth_basic" {
  role       = aws_iam_role.auth.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "archive_file" "lambda_auth" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/auth"
  output_path = "${path.module}/../build/auth.zip"
}

resource "aws_lambda_function" "auth" {
  function_name    = "${local.name_prefix}-auth"
  runtime          = var.lambda_runtime
  handler          = "handler.lambda_handler"
  role             = aws_iam_role.auth.arn
  filename         = data.archive_file.lambda_auth.output_path
  source_code_hash = data.archive_file.lambda_auth.output_base64sha256
  timeout          = 15
  memory_size      = var.lambda_memory_mb

  environment {
    variables = {
      AUTH_DOMAIN       = local.auth_hosted_ui_url
      COGNITO_CLIENT_ID = local.auth_jwt_client_id
    }
  }
}

resource "aws_cloudwatch_log_group" "auth" {
  name              = "/aws/lambda/${aws_lambda_function.auth.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_permission" "auth_api" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auth.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.main.execution_arn}/*/*"
}

resource "aws_apigatewayv2_integration" "auth" {
  api_id                 = aws_apigatewayv2_api.main.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.auth.invoke_arn
  payload_format_version = "2.0"
}

locals {
  auth_routes = [
    "POST /auth/callback",
    "POST /auth/refresh",
    "POST /auth/logout",
  ]
}

# No authorizer — these routes are the entry point to authentication.
resource "aws_apigatewayv2_route" "auth" {
  for_each = toset(local.auth_routes)

  api_id    = aws_apigatewayv2_api.main.id
  route_key = each.value
  target    = "integrations/${aws_apigatewayv2_integration.auth.id}"
}
